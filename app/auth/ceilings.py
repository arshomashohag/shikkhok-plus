"""Three cascades over one implementation, each checked narrowest first.

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

**The two global scopes are a send budget, not a request limit**
[PA-SEC-2]. They used to sit at the end of the request-path cascades,
and the sign-in route answers every number identically -- known or
not, for the existence oracle's sake -- while only a known number is
ever texted. So every request for an *unknown* number spent one unit of
a budget that only real SMS cost, and anyone could exhaust the day's
sign-in budget with numbers nobody owns, locking every teacher out
without the project spending a taka. The per-number and per-IP scopes
stay on the request path, where they bound callers; the global scopes
are consumed by :meth:`CeilingChecker.consume_send` at the moment an
SMS is actually about to go out (see :mod:`app.auth.delivery`), which
is after the response has been written and only for a known number --
so the request path stays identical for both.
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
    "DEL_GLOBAL_DAILY",
    "DEL_PER_IP_HOURLY",
    "DEL_PER_NUMBER_DAILY",
    "DEL_PER_NUMBER_HOURLY",
    "GLOBAL_DAILY",
    "PER_IP_HOURLY",
    "PER_NUMBER_DAILY",
    "PER_NUMBER_HOURLY",
    "SIGNUP_PER_IP_HOURLY",
    "SIGNUP_PER_NUMBER_DAILY",
    "CeilingBreach",
    "CeilingChecker",
    "ScopeKind",
    "SendBudget",
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

#: A 4th deletion code for one number inside an hour is refused
#: [NFR14.100]. Matched to the OTP path's hourly allowance: a person
#: deleting their account asks for a code once, and a third retry is
#: already generous.
DEL_PER_NUMBER_HOURLY: Final = 3

#: A 6th inside a day is refused [NFR14.100].
DEL_PER_NUMBER_DAILY: Final = 5

#: An 11th from one IP prefix inside an hour is refused. **Depth rather
#: than the control** [DESIGN-6]: an attacker spanning /24s (or IPv6
#: /64s, see :mod:`app.auth.client_address`) never accumulates toward
#: it, so the global sub-ceiling below is what actually binds.
DEL_PER_IP_HOURLY: Final = 10

#: **The load-bearing control** [NFR14.102]. Fifty deletion codes in a
#: day across the whole product, as a sub-ceiling of the OTP path's
#: global budget rather than a share of it.
#:
#: **Signup's no-global decision deliberately does not transfer**, and
#: the difference is the attack. `_signup_scopes` has no global scope
#: because signup's one SMS is sent through
#: :func:`~app.auth.delivery.send_within_budget` against sign-in's
#: budget, so a second counter would bound the same spend twice.
#: Deletion's hazard is not that it spends twice -- it is that it spends
#: **the same budget sign-in needs**, which is the exact condition this
#: sub-ceiling exists for. A reader patterning off signup would omit
#: this scope and reopen the finding.
#:
#: Spent at send time through :class:`SendBudget`, not on the request
#: path [PA-SEC-2].
DEL_GLOBAL_DAILY: Final = int(
    os.environ.get("SHIKKHOKPLUS_GLOBAL_DAILY_DELETION_SMS", "50")
)

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
    # D6's cascade, on the signup members' reasoning: SEPARATE counters,
    # never extra conditions on the OTP ones [NFR14.100]. Sharing them
    # would mean an unauthenticated caller draining a victim's deletion
    # allowance ALSO locks that victim out of signing in -- and a test
    # asserting only that the deletion route refuses passes against
    # exactly that defect, because refusing is what both implementations
    # do.
    #
    # The `del_` prefix is deliberate and the lengths were computed
    # rather than eyeballed: the column is `String(16)`, and the obvious
    # prefixes do not fit -- `deletion_number_day` is 19 and
    # `delete_number_day` is 17. PostgreSQL refuses such a value
    # outright, as the signup comment above records it already did once.
    DEL_NUMBER_HOURLY = "del_number_hour"
    DEL_NUMBER_DAILY = "del_number_day"
    DEL_IP_HOURLY = "del_ip_hour"
    DEL_GLOBAL_DAILY = "del_global_day"


#: The scopes whose breach reaches a human. Declared beside the enum
#: rather than tested inline, so adding a fifth cascade is a decision
#: about this set rather than a condition someone extends in passing.
_ALERTING_SCOPES: Final = frozenset(
    {ScopeKind.GLOBAL_DAILY, ScopeKind.DEL_GLOBAL_DAILY}
)


class SendBudget(enum.Enum):
    """The two daily SMS budgets, each consumed only by a real send.

    The value is the scope the budget counts against. **Two budgets, not
    one shared**: deletion's sub-ceiling exists so an unauthenticated
    caller on the public deletion page cannot spend what sign-in needs
    [NFR14.102].
    """

    SIGN_IN = ScopeKind.GLOBAL_DAILY
    DELETION = ScopeKind.DEL_GLOBAL_DAILY


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
    """Check and consume the ceilings for one send, signup or deletion.

    **Three cascades over one ``_consume``**, never one cascade with
    extra conditions: each has its own ``ScopeKind`` members and
    therefore its own counter rows, so a refusal on one path never
    consumes another path's allowance.

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
        """Consume one sign-in request's per-number and per-IP budget.

        Called **before** ``otp.issue``, for every number, known or not:
        these scopes bound a caller, and an unknown number must be
        bounded identically or the refusal becomes the oracle. The
        global send budget is NOT consumed here -- see
        :meth:`consume_send` [PA-SEC-2].

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

    def check_and_consume_deletion(
        self,
        number: str,
        ip_prefix: str,
        now: dt.datetime | None = None,
    ) -> None:
        """Consume one deletion request's per-number and per-IP budget.

        **A THIRD cascade over the same ``_consume``, never extra
        conditions on the first two** [NFR14.100, NFR14.102]. It shares
        the narrowest-first order, the release-on-refusal accounting and
        the datastore-backed counters, and shares no counter ROW -- its
        scopes are distinct :class:`ScopeKind` members, so a deletion
        refusal never consumes a sign-in allowance and the reverse.

        That separation is the whole control. The public deletion route
        takes only a phone number, so a shared counter would let an
        unauthenticated caller spend a victim's sign-in allowance and
        lock them out of their own account -- while a test asserting
        only that the route refuses would be green throughout.

        Called on the request path for every number, known or not. The
        deletion send budget is consumed by :meth:`consume_send` at the
        moment a code is actually sent, for the reason
        :meth:`check_and_consume` gives [PA-SEC-2].

        :param number: The number a deletion code is being sent to
        :param ip_prefix: The caller's IP prefix
        :param now: The moment to count against, or None for the clock
        :return: None
        :raises CeilingBreach: A ceiling refused this send
        """
        self._consume(self._deletion_scopes(number, ip_prefix), now)

    def consume_send(
        self,
        budget: SendBudget,
        now: dt.datetime | None = None,
    ) -> None:
        """Consume one real SMS from a daily send budget.

        Called **immediately before** ``gateway.send`` and only when a
        send is actually about to happen, never on the request path:
        a request for an unknown number sends nothing, so it must cost
        nothing here [PA-SEC-2]. It is still checked *before* the
        gateway call, so the money is never spent first [BR2.2].

        Same ``_consume``, so the same atomic upsert, the same
        release-on-refusal and the same alert.

        :param budget: Which daily budget this send spends
        :param now: The moment to count against, or None for the clock
        :return: None
        :raises CeilingBreach: The budget for today is exhausted
        """
        limit = GLOBAL_DAILY if budget is SendBudget.SIGN_IN else DEL_GLOBAL_DAILY
        self._consume([(_Scope(budget.value, limit, _DAY), GLOBAL_SCOPE_VALUE)], now)

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
                # The two GLOBAL scopes alert; the per-number and per-IP
                # ones never do. They fire constantly once the product
                # has users, which trains the operator to ignore the one
                # that matters sitting in the same channel.
                #
                # `del_global_day` alerts for a sharper reason than its
                # sibling: sign-in's global ceiling tripping might be a
                # busy day, while fifty deletion codes in a day is the
                # one scope of the seven whose breach has no innocent
                # explanation.
                if scope.kind in _ALERTING_SCOPES:
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
        to the project is the OTP it triggers, and that send spends
        sign-in's daily send budget through
        :func:`~app.auth.delivery.send_within_budget`. A second global
        counter would bound the same spend twice at two thresholds, so
        the tighter one would silently become the real limit and the
        looser one would read as a control while governing nothing.

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

    @staticmethod
    def _deletion_scopes(number: str, ip_prefix: str) -> list[tuple[_Scope, str]]:
        """Build the deletion request cascade, narrowest first.

        Three request scopes, like sign-in's. Deletion's global
        sub-ceiling [NFR14.102] is :attr:`SendBudget.DELETION`, spent
        at send time by :meth:`consume_send` -- not here, where an
        unknown number would spend it [PA-SEC-2].

        :param number: The number a deletion code is being sent to
        :param ip_prefix: The caller's IP prefix
        :return: Each scope paired with the value it counts against
        """
        return [
            (
                _Scope(
                    ScopeKind.DEL_NUMBER_HOURLY,
                    DEL_PER_NUMBER_HOURLY,
                    _HOUR,
                ),
                number,
            ),
            (
                _Scope(
                    ScopeKind.DEL_NUMBER_DAILY,
                    DEL_PER_NUMBER_DAILY,
                    _DAY,
                ),
                number,
            ),
            (
                _Scope(ScopeKind.DEL_IP_HOURLY, DEL_PER_IP_HOURLY, _HOUR),
                ip_prefix,
            ),
        ]
