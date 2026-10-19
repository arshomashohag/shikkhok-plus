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
    """The four counter scopes, in narrowest-to-widest order.

    The declaration order **is** the evaluation order, so the cascade
    cannot drift from the rule by someone reordering a dictionary.
    """

    NUMBER_HOURLY = "number_hour"
    NUMBER_DAILY = "number_day"
    IP_HOURLY = "ip_hour"
    GLOBAL_DAILY = "global_day"


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

    :ivar scope: Which ceiling refused, for the operator's logs only
    """

    def __init__(self, scope: ScopeKind) -> None:
        """Refuse a send without disclosing why.

        :param scope: The scope that refused
        """
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
        moment = now or dt.datetime.now(tz=dt.UTC)

        for scope, value in self._scopes(number, ip_prefix):
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
