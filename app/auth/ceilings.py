"""The four counters, checked narrowest first.

**Order is the control.** Each scope is checked and incremented only if it
passes, in narrowest-to-widest order, so a refusal at the per-number
hourly ceiling never touches the global daily one.

An earlier design checked global first, and **the rule argued against
itself**: its prose said the sub-ceilings exist so an attacker burning one
number's allowance does not exhaust everyone else's, while its logic
checked the global counter first. That order lets one attacker consume the
global daily budget before their own per-number limit trips -- they are
stopped eventually, but only after spending every legitimate teacher's
allowance for the day.

That is recorded here rather than only in the design, because
**global-first still looks like defence in depth**. It reads as "check the
big one first", which is exactly backwards.

**Order and accounting are one decision, not two.** A narrowest-first
check that still increments the global counter on a refused request has
the same defect in a quieter form, so the increment is part of the same
statement as the check.

**The counters live in the datastore** [BR2.1]. A per-process dictionary
is the obvious implementation, passes every naive test, and silently stops
working the moment there are two workers -- which Phase 1 has, because one
Lightsail host runs several Uvicorn workers. That presents as "the limit
works in testing", which is the worst way for a budget control to fail.
"""

from __future__ import annotations

import datetime as dt
import enum
import logging
import os
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.errors import ConflictError

__all__ = [
    "GLOBAL_DAILY",
    "PER_IP_HOURLY",
    "PER_NUMBER_DAILY",
    "PER_NUMBER_HOURLY",
    "SIGNUP_PER_IP_HOURLY",
    "SIGNUP_PER_NUMBER_DAILY",
    "CeilingBreach",
    "CeilingChecker",
    "ScopeKind",
    "fire_ceiling_alert",
]

_log = logging.getLogger(__name__)

#: A 4th code for one number inside an hour is refused [BR2.2].
PER_NUMBER_HOURLY: Final = 3

#: A 6th inside a day is refused [BR2.2].
PER_NUMBER_DAILY: Final = 5

#: An 11th from one IP prefix inside an hour is refused [BR2.2].
PER_IP_HOURLY: Final = 10

#: The global daily ceiling. **A value, not a decision**: the production
#: number derives from BulkSMSBD's per-SMS rate against the USD 50/month
#: budget and is set at deployment. The mechanism is what this Bolt
#: builds and tests, at a test-configured threshold.
GLOBAL_DAILY: Final = int(os.environ.get("SHIKKHOKPLUS_GLOBAL_DAILY_SMS", "500"))

#: The sentinel the global scope counts against.
GLOBAL_SCOPE_VALUE: Final = "global"

#: A 4th signup attempt on one number inside a day is refused [BR2.1].
#: Lower than the OTP path's daily allowance, because a person signs up
#: for a number ONCE: repeated attempts on one number are a typo or an
#: attack, never ordinary use.
SIGNUP_PER_NUMBER_DAILY: Final = 3

#: An 11th signup from one IP prefix inside an hour is refused [BR2.1].
#: Matched to the OTP path's per-IP allowance rather than chosen
#: independently: both bound the same shared-NAT population, and a
#: tighter signup limit would lock out a school's wifi before it
#: slowed anyone down.
SIGNUP_PER_IP_HOURLY: Final = 10

_HOUR = dt.timedelta(hours=1)
_DAY = dt.timedelta(days=1)

#: Atomic upsert-and-increment. The count is compared **after** the
#: increment, so two workers racing on one window cannot both read a
#: stale value and both pass at the limit [NFR10.2].
_UPSERT = sa.text(
    """
    INSERT INTO rate_limit_counter
        (id, scope_kind, scope_value, window_start, count)
    VALUES (gen_random_uuid(), :kind, :value, :window, 1)
    ON CONFLICT (scope_kind, scope_value, window_start)
    DO UPDATE SET count = rate_limit_counter.count + 1
    RETURNING count
    """
)


class ScopeKind(enum.Enum):
    """The counter scopes, each cascade in narrowest-to-widest order.

    The declaration order **is** the evaluation order, so a cascade
    cannot drift from the rule by someone reordering a dictionary.

    **The signup members are separate counters, not extra conditions
    on the OTP ones** [BR2.1, NFR12.3]. Signup and OTP have OPPOSITE
    disclosure properties by design -- the OTP response is
    byte-identical whether or not a number is known, while the
    already-added lookup discloses that a seat exists because that is
    its purpose -- and conflating their controls is how one inherits
    the other's assumptions. A signup refusal never consumes an OTP
    allowance, and the reverse.

    They count against distinct ``scope_kind`` values, so the shared
    ``rate_limit_counter`` table holds two independent cascades without
    either reading the other's rows.
    """

    NUMBER_HOURLY = "number_hour"
    NUMBER_DAILY = "number_day"
    IP_HOURLY = "ip_hour"
    GLOBAL_DAILY = "global_day"
    # Abbreviated to fit `rate_limit_counter.scope_kind`, which is
    # `String(16)`. `signup_number_day` is seventeen characters and
    # PostgreSQL refuses it outright -- loudly, at the first signup,
    # which is the right failure. Widening the column would be a
    # migration against a table two cascades write concurrently, to buy
    # one character of readability.
    SIGNUP_NUMBER_DAILY = "su_number_day"
    SIGNUP_IP_HOURLY = "su_ip_hour"


@dataclass(frozen=True, slots=True)
class _Scope:
    """One scope's identity, limit and window.

    :ivar kind: Which scope this is
    :ivar limit: The count at which a further send is refused
    :ivar window: How long this scope's counter accumulates for
    """

    kind: ScopeKind
    limit: int
    window: dt.timedelta


class CeilingBreach(ConflictError):
    """A ceiling refused this send.

    A :class:`~app.errors.ConflictError` and never a
    :class:`~app.errors.TransientError`: **retrying into a cost ceiling is
    exactly wrong**, and a 429 carries a retry-after convention that
    invites it [BR2.2].

    The message does not reveal the limit, and never implies the number is
    invalid: revealing the limit tells an attacker how to pace a drain,
    and "invalid number" tells a legitimate teacher their account is
    broken while telling an attacker which numbers exist [BR2.6].

    **The message key follows the cascade, the code does not.** Both
    cascades answer the same contentless ``TEMPORARILY_UNAVAILABLE``,
    so a client switching on the code treats them identically; what
    differs is the string the person reads, because a signup refusal
    shown on the signup screen saying "we could not send your code"
    describes a step that never happened. Neither key names the limit
    or implies the number is invalid [BR2.6].

    :ivar scope: Which ceiling refused, for the operator's logs only
    """

    #: The scopes whose refusal is a SIGNUP refusal rather than a send
    #: refusal. Derived from the scope rather than passed by the caller,
    #: so a future call site cannot pair a cascade with the wrong text.
    _SIGNUP_SCOPES: Final = frozenset(
        {ScopeKind.SIGNUP_NUMBER_DAILY, ScopeKind.SIGNUP_IP_HOURLY}
    )

    def __init__(self, scope: ScopeKind) -> None:
        """Refuse without disclosing why.

        Each branch writes its key as a literal at a ``message_key=``
        site, rather than selecting one in an expression. That is for
        the key SCANNER, which matches that literal form across the
        whole backend: a key assembled in a conditional expression is
        invisible to it, so the published list silently stops covering
        it and the app renders a generic fallback that looks like a
        working error message.

        :param scope: The scope that refused
        """
        if scope in self._SIGNUP_SCOPES:
            super().__init__(
                code="TEMPORARILY_UNAVAILABLE",
                message_key="signup.temporarily_unavailable",
            )
        else:
            super().__init__(
                code="TEMPORARILY_UNAVAILABLE",
                message_key="auth.otp.temporarily_unavailable",
            )
        self.scope = scope


def fire_ceiling_alert(scope: str) -> None:
    """Alert the operator that the global ceiling tripped.

    Money, and also the signal for an active attack -- so it is one of
    the six things that reach a human. The per-number and per-IP
    sub-ceilings deliberately do **not** alert: they fire constantly once
    the product has users, which trains the operator to ignore this one
    sitting in the same channel.

    :param scope: The scope that tripped
    :return: None
    """
    _log.critical("sms ceiling breached", extra={"scope": scope})


def _window_start(now: dt.datetime, window: dt.timedelta) -> dt.datetime:
    """Truncate a timestamp to the start of its window.

    :param now: The moment being counted
    :param window: The window length
    :return: The window's start
    """
    if window == _DAY:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    return now.replace(minute=0, second=0, microsecond=0)


class CeilingChecker:
    """Check and consume the four ceilings for one send.

    :ivar session: The session the counters are read and written through
    """

    def __init__(self, session: Session) -> None:
        """Bind the checker to a session.

        :param session: The session to count through
        """
        self.session = session

    def check_and_consume(
        self,
        number: str,
        ip_prefix: str,
        now: dt.datetime | None = None,
    ) -> None:
        """Consume one send's budget, refusing at the narrowest breach.

        Called **before** the gateway call, never after: checking
        afterwards spends the money the limit exists to protect [BR2.2].

        :param number: The phone number this send is for
        :param ip_prefix: The caller's IP prefix
        :param now: The moment to count against, or None for the clock
        :return: None
        :raises CeilingBreach: A ceiling refused this send
        """
        self._consume(self._scopes(number, ip_prefix), now)

    def check_and_consume_signup(
        self,
        number: str,
        ip_prefix: str,
        now: dt.datetime | None = None,
    ) -> None:
        """Consume one signup's budget, refusing at the narrowest breach.

        **A second cascade over the same mechanism, never extra
        conditions on the first** [BR2.1, NFR12.3]. It shares the
        narrowest-first order, the release-on-refusal accounting and
        the datastore-backed counters, and shares no counter ROW: its
        scopes are distinct ``ScopeKind`` members, so a signup refusal
        never consumes an OTP allowance and the reverse.

        Called **before** the account is created, for the same reason
        the OTP cascade is called before the gateway: a ceiling checked
        afterwards has already spent what it exists to protect.

        :param number: The number being signed up
        :param ip_prefix: The caller's IP prefix
        :param now: The moment to count against, or None for the clock
        :return: None
        :raises CeilingBreach: A ceiling refused this signup
        """
        self._consume(self._signup_scopes(number, ip_prefix), now)

    def _consume(
        self,
        cascade: list[tuple[_Scope, str]],
        now: dt.datetime | None = None,
    ) -> None:
        """Walk one cascade, refusing and releasing at the first breach.

        **One implementation for both cascades, deliberately.** The
        order-and-accounting rule is the control, and a second copy of
        it is how the two stop agreeing -- with the copy that drifts
        being whichever one is read less often.

        :param cascade: The scopes to consume, narrowest first
        :param now: The moment to count against, or None for the clock
        :return: None
        :raises CeilingBreach: A scope refused
        """
        moment = now or dt.datetime.now(tz=dt.UTC)

        for scope, value in cascade:
            window = _window_start(moment, scope.window)
            count = self.session.execute(
                _UPSERT,
                {
                    "kind": scope.kind.value,
                    "value": value,
                    "window": window,
                },
            ).scalar_one()
            self.session.commit()

            if count > scope.limit:
                # Undo THIS scope's increment, so a refusal consumes
                # nothing at all -- including the scope that refused.
                self._release(scope, value, window)
                if scope.kind is ScopeKind.GLOBAL_DAILY:
                    fire_ceiling_alert(scope.kind.value)
                raise CeilingBreach(scope.kind)

    def _release(self, scope: _Scope, value: str, window: dt.datetime) -> None:
        """Undo one increment after its own check refused.

        :param scope: The refusing scope
        :param value: Its scope value
        :param window: Its window start
        :return: None
        """
        self.session.execute(
            sa.text(
                "UPDATE rate_limit_counter SET count = count - 1 "
                "WHERE scope_kind = :kind AND scope_value = :value "
                "AND window_start = :window"
            ),
            {"kind": scope.kind.value, "value": value, "window": window},
        )
        self.session.commit()

    @staticmethod
    def _scopes(number: str, ip_prefix: str) -> list[tuple[_Scope, str]]:
        """Build the cascade, narrowest first.

        :param number: The phone number
        :param ip_prefix: The caller's IP prefix
        :return: Each scope paired with the value it counts against
        """
        return [
            (_Scope(ScopeKind.NUMBER_HOURLY, PER_NUMBER_HOURLY, _HOUR), number),
            (_Scope(ScopeKind.NUMBER_DAILY, PER_NUMBER_DAILY, _DAY), number),
            (_Scope(ScopeKind.IP_HOURLY, PER_IP_HOURLY, _HOUR), ip_prefix),
            (
                _Scope(ScopeKind.GLOBAL_DAILY, GLOBAL_DAILY, _DAY),
                GLOBAL_SCOPE_VALUE,
            ),
        ]

    @staticmethod
    def _signup_scopes(number: str, ip_prefix: str) -> list[tuple[_Scope, str]]:
        """Build the signup cascade, narrowest first.

        **Narrowest first, like its sibling, and for the reason the
        module docstring records**: global-first lets one attacker
        exhaust every legitimate user's allowance before their own
        limit trips, and it *still looks like* defence in depth --
        which is exactly why a second cascade is where that mistake
        would return [NFR12.4].

        **No global scope here, and that is a decision.** Signup's cost
        to the project is the OTP it triggers, and that send passes
        through the OTP cascade's own global daily ceiling immediately
        afterwards. A second global counter would bound the same spend
        twice at two thresholds, so the tighter one would silently
        become the real limit and the looser one would read as a
        control while governing nothing.

        :param number: The number being signed up
        :param ip_prefix: The caller's IP prefix
        :return: Each scope paired with the value it counts against
        """
        return [
            (
                _Scope(
                    ScopeKind.SIGNUP_NUMBER_DAILY,
                    SIGNUP_PER_NUMBER_DAILY,
                    _DAY,
                ),
                number,
            ),
            (
                _Scope(
                    ScopeKind.SIGNUP_IP_HOURLY,
                    SIGNUP_PER_IP_HOURLY,
                    _HOUR,
                ),
                ip_prefix,
            ),
        ]
