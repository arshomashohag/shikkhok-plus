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

**Signup spends its own send budget** [C-05]. It used to spend sign-in's,
and any fresh number triggers a signup SMS, so one unauthenticated
caller could empty sign-in's budget and nobody received a sign-in code
until the window reset. :attr:`SendBudget.SIGNUP` bounds signup's SMS
separately, and every send a signup triggers -- for a new number or an
existing one -- spends it, so sign-in's budget is spent only on texting
numbers that already have an account. That is the reservation: the
accounts that exist can always be reached until THEIR traffic, not a
stranger's, exhausts it.

**Every per-IP cascade also counts the caller's /48** [C-05]. A /64 is
one subscriber, but one caller holding a /56 has 256 of them, and each
was a fresh bucket. The /48 scope bounds that spread at a higher limit
than the /64 scope, because many real subscribers of one carrier can
share a /48.

**A failed verify is counted, wider than one code** [C-20]. The only
verify-side limit used to be five attempts per code, so a caller could
guess at every number it could request codes for. Failures now count
against the caller's /64 and /48 and against a global hourly ceiling,
which alerts; a verify arriving while any of them is full is refused
before its code is checked. And a number whose codes keep being guessed
to death is cooled off: once :data:`DEAD_CODES_PER_NUMBER_DAILY` codes
have died at the attempt ceiling today, no further code is issued for
it, for a known and an unknown number alike.

**A failed password alerts globally but never refuses globally**
[SEC-1]. Password failures used to fill the same global hourly ceiling
as failed codes, and that ceiling refuses every verify in the product
once full. A password guesser spread across a few prefixes, or a busy
evening of real typos, therefore stopped every sign-in for the rest of
the hour. The outage-over-a-guessing-run trade-off was made for
six-digit codes, which have no per-identifier ceiling to fall back on;
passwords do. So a failed password counts against the identifier, the
caller's /64 and /48 (all three refuse), and against its own global
scope, which alerts when it fills and refuses nothing.

**The already-added lookup is its own cascade** [SEC-4]. It used to
spend signup's per-number allowance, so three anonymous lookups of a
victim's number stopped that number signing up for a day -- the student
or guardian a teacher had just enrolled, in the middle of acceptance.
The lookup now counts per /64, per /48 and against a separate, higher
per-number allowance, and spends nothing signup needs.
"""

from __future__ import annotations

import datetime as dt
import enum
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.errors import ConflictError

__all__ = [
    "CENTRES_PER_ACCOUNT_DAILY",
    "DEAD_CODES_PER_NUMBER_DAILY",
    "DEL_GLOBAL_DAILY",
    "DEL_PER_IP_HOURLY",
    "DEL_PER_NUMBER_DAILY",
    "DEL_PER_NUMBER_HOURLY",
    "GLOBAL_DAILY",
    "LOOKUP_GLOBAL_HOURLY",
    "LOOKUP_PER_COARSE_IP_HOURLY",
    "LOOKUP_PER_IP_HOURLY",
    "LOOKUP_PER_NUMBER_DAILY",
    "PASSWORD_FAILURES_GLOBAL_HOURLY",
    "PER_COARSE_IP_HOURLY",
    "PER_IP_HOURLY",
    "PER_NUMBER_DAILY",
    "PER_NUMBER_HOURLY",
    "SIGNUP_GLOBAL_DAILY",
    "SIGNUP_PER_COARSE_IP_HOURLY",
    "SIGNUP_PER_IP_HOURLY",
    "SIGNUP_PER_NUMBER_DAILY",
    "VERIFY_FAILURES_GLOBAL_HOURLY",
    "VERIFY_FAILURES_PER_COARSE_IP_HOURLY",
    "VERIFY_FAILURES_PER_IP_HOURLY",
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

#: Already-added lookups of one number in a day, beyond which the next
#: is refused [SEC-4]. Higher than signup's allowance, because the
#: signup form looks the number up as it renders and a person retrying a
#: failed send renders it again; low enough that the lookup is no
#: cheaper a way to watch one number than any other.
LOOKUP_PER_NUMBER_DAILY: Final = 20

#: Already-added lookups from one /64 (IPv4: /24) in an hour [SEC-4].
#: Above signup's per-IP allowance for the same re-render reason, and
#: still what bounds enumerating which numbers hold a seat.
LOOKUP_PER_IP_HOURLY: Final = 30

#: Already-added lookups from one /48 in an hour [SEC-4], higher than
#: the /64 limit for the carrier-sharing reason the other /48 scopes
#: give.
LOOKUP_PER_COARSE_IP_HOURLY: Final = 100

#: Already-added lookups served across the whole product inside an hour,
#: at which the operator is alerted [SEC-4]. **Alert only, never a
#: refusal**, on the password-failure scope's reasoning: the per-number,
#: /64 and /48 ceilings bound one caller, and a product-wide refusal
#: would let anyone break every signup form by looking numbers up. What
#: the per-caller ceilings cannot see is an enumeration spread across
#: more prefixes than they bound, and this is what notices one. **A
#: value, not a decision**, configured at deployment.
LOOKUP_GLOBAL_HOURLY: Final = int(
    os.environ.get("SHIKKHOKPLUS_GLOBAL_HOURLY_LOOKUPS", "1000")
)

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

#: Signup's own daily SMS budget [C-05], configured like the sign-in
#: one: **a value, not a decision**, set at deployment from the SMS rate
#: against the monthly budget. Separate so a stranger signing up numbers
#: cannot spend what existing accounts need to sign in.
SIGNUP_GLOBAL_DAILY: Final = int(
    os.environ.get("SHIKKHOKPLUS_GLOBAL_DAILY_SIGNUP_SMS", "100")
)

#: Emailed codes across the whole product in a day [0032]. Its own
#: budget, not a share of an SMS one: an email costs a hundredth of an
#: SMS, so spending SMS budgets on it would starve sign-in for nothing,
#: while an unbounded email path would let anyone use the signup form to
#: mail strangers -- which is what gets a sending domain's reputation
#: burned and its SES account paused.
EMAIL_GLOBAL_DAILY: Final = int(
    os.environ.get("SHIKKHOKPLUS_GLOBAL_DAILY_EMAIL", "1000")
)

#: Failed password sign-ins for one phone number or email address in an
#: hour, beyond which that identifier's password sign-in is refused until
#: the window turns [0032]. Counted for an unknown identifier exactly as
#: for a known one, so the refusal says nothing about who exists.
#: Generous enough that a person mistyping is never stopped; a guesser
#: gets ten tries an hour per identifier, and the code flow stays open
#: to the real owner throughout.
PASSWORD_FAILURES_PER_IDENTIFIER_HOURLY: Final = 10

#: Failed password sign-ins across the whole product inside an hour, at
#: which the operator is alerted [SEC-1]. **Alert only, never a
#: refusal**: the per-identifier, /64 and /48 ceilings bound a guesser,
#: and a global refusal here would let anyone turn a few hundred wrong
#: passwords into an outage of every sign-in. **A value, not a
#: decision**, configured at deployment.
PASSWORD_FAILURES_GLOBAL_HOURLY: Final = int(
    os.environ.get("SHIKKHOKPLUS_GLOBAL_HOURLY_PASSWORD_FAILURES", "300")
)

#: Sign-in requests from one /48 inside an hour, beyond which the next is
#: refused [C-05]. Higher than the /64 limit: the /48 bounds one caller
#: spread across many /64s, and many real subscribers of one carrier can
#: sit in one /48.
PER_COARSE_IP_HOURLY: Final = 50

#: Signup's /48 limit, matched to sign-in's on the per-IP reasoning.
SIGNUP_PER_COARSE_IP_HOURLY: Final = 50

#: Failed verifies from one /64 (or IPv4 /24) inside an hour, at which
#: further verifies from it are refused [C-20]. A person mistyping a
#: code fails a few times; four numbers' worth of dead codes is not
#: ordinary use.
VERIFY_FAILURES_PER_IP_HOURLY: Final = 20

#: Failed verifies from one /48 inside an hour [C-20], higher than the
#: /64 limit for the carrier-sharing reason above.
VERIFY_FAILURES_PER_COARSE_IP_HOURLY: Final = 60

#: Failed verifies across the whole product inside an hour [C-20]. **A
#: value, not a decision**, configured at deployment. Reaching it alerts
#: and refuses every verify for the rest of the hour: an outage, chosen
#: over a guessing run spread across more prefixes than the per-IP
#: limits can see.
VERIFY_FAILURES_GLOBAL_HOURLY: Final = int(
    os.environ.get("SHIKKHOKPLUS_GLOBAL_HOURLY_VERIFY_FAILURES", "300")
)

#: Codes for one number that may die at the attempt ceiling in a day
#: before no further code is issued for it [C-20].
DEAD_CODES_PER_NUMBER_DAILY: Final = 2

#: Centres one account may open in a day [L-06]. Opening one is a
#: deliberate, rare act; a loop opening many is not.
CENTRES_PER_ACCOUNT_DAILY: Final = 3

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
    # The 2026-11-07 security pass [C-05, C-20, L-06], each its own
    # counter on the reasoning above, every name inside `String(16)`.
    IP48_HOURLY = "ip48_hour"
    SIGNUP_IP48_HOURLY = "su_ip48_hour"
    SIGNUP_GLOBAL_DAILY = "su_global_day"
    VERIFY_FAIL_IP_HOURLY = "vf_ip_hour"
    VERIFY_FAIL_IP48_HOURLY = "vf_ip48_hour"
    VERIFY_FAIL_GLOBAL_HOURLY = "vf_global_hour"
    DEAD_CODE_NUMBER_DAILY = "dead_number_day"
    CENTRE_ACCOUNT_DAILY = "centre_acct_day"
    # Email and passwords [0032], inside `String(16)` like the rest.
    EMAIL_GLOBAL_DAILY = "em_global_day"
    PASSWORD_FAIL_ID_HOURLY = "pw_fail_id_hour"  # noqa: S105 -- a name, not a password
    # The already-added lookup's own cascade [SEC-4], never signup's.
    LOOKUP_NUMBER_DAILY = "lk_number_day"
    LOOKUP_IP_HOURLY = "lk_ip_hour"
    LOOKUP_IP48_HOURLY = "lk_ip48_hour"
    # Alert-only [SEC-1]: counted and alerted on, never checked.
    PASSWORD_FAIL_GLOBAL_HOURLY = "pwf_global_hour"  # noqa: S105 -- a name
    LOOKUP_GLOBAL_HOURLY = "lk_global_hour"


#: The scopes whose breach reaches a human. Declared beside the enum
#: rather than tested inline, so adding a fifth cascade is a decision
#: about this set rather than a condition someone extends in passing.
#: Every member is a whole-product scope; no per-number or per-IP scope
#: belongs here, for the reason :func:`fire_ceiling_alert` gives.
_ALERTING_SCOPES: Final = frozenset(
    {
        ScopeKind.GLOBAL_DAILY,
        ScopeKind.DEL_GLOBAL_DAILY,
        ScopeKind.SIGNUP_GLOBAL_DAILY,
        ScopeKind.VERIFY_FAIL_GLOBAL_HOURLY,
        ScopeKind.EMAIL_GLOBAL_DAILY,
        ScopeKind.PASSWORD_FAIL_GLOBAL_HOURLY,
        ScopeKind.LOOKUP_GLOBAL_HOURLY,
    }
)

#: The verify-failure scopes, whose refusal is a VERIFY refusal.
_VERIFY_SCOPES: Final = frozenset(
    {
        ScopeKind.VERIFY_FAIL_IP_HOURLY,
        ScopeKind.VERIFY_FAIL_IP48_HOURLY,
        ScopeKind.VERIFY_FAIL_GLOBAL_HOURLY,
    }
)


class SendBudget(enum.Enum):
    """The three daily SMS budgets, each consumed only by a real send.

    The value is the scope the budget counts against. **Separate budgets,
    not one shared**: deletion's sub-ceiling exists so an unauthenticated
    caller on the public deletion page cannot spend what sign-in needs
    [NFR14.102], and signup's for the same reason on the signup page
    [C-05].
    """

    SIGN_IN = ScopeKind.GLOBAL_DAILY
    DELETION = ScopeKind.DEL_GLOBAL_DAILY
    SIGNUP = ScopeKind.SIGNUP_GLOBAL_DAILY
    #: Every emailed code, whatever it is for [0032].
    EMAIL = ScopeKind.EMAIL_GLOBAL_DAILY


#: Each send budget's daily limit. A mapping, so a fourth budget is a
#: KeyError at its first send rather than a silent reuse of another's.
_BUDGET_LIMITS: Final[dict[SendBudget, int]] = {
    SendBudget.SIGN_IN: GLOBAL_DAILY,
    SendBudget.DELETION: DEL_GLOBAL_DAILY,
    SendBudget.SIGNUP: SIGNUP_GLOBAL_DAILY,
    SendBudget.EMAIL: EMAIL_GLOBAL_DAILY,
}


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
        {
            ScopeKind.SIGNUP_NUMBER_DAILY,
            ScopeKind.SIGNUP_IP_HOURLY,
            ScopeKind.SIGNUP_IP48_HOURLY,
            # The lookup runs on the signup form, so its refusal reads
            # in signup's words [SEC-4].
            ScopeKind.LOOKUP_NUMBER_DAILY,
            ScopeKind.LOOKUP_IP_HOURLY,
            ScopeKind.LOOKUP_IP48_HOURLY,
        }
    )

    def __init__(self, scope: ScopeKind, *, during_signup: bool = False) -> None:
        """Refuse without disclosing why.

        Each branch writes its key as a literal at a ``message_key=``
        site, rather than selecting one in an expression. That is for
        the key SCANNER, which matches that literal form across the
        whole backend: a key assembled in a conditional expression is
        invisible to it, so the published list silently stops covering
        it and the app renders a generic fallback that looks like a
        working error message.

        ``during_signup`` exists for the one scope two cascades read: the
        dead-code cool-off is per NUMBER, and a signup it refuses must say
        so in signup's words.

        :param scope: The scope that refused
        :param during_signup: The refusal is on the signup path
        """
        if scope in self._SIGNUP_SCOPES or during_signup:
            super().__init__(
                code="TEMPORARILY_UNAVAILABLE",
                message_key="signup.temporarily_unavailable",
            )
        elif scope in _VERIFY_SCOPES:
            super().__init__(
                code="TEMPORARILY_UNAVAILABLE",
                message_key="auth.verify.temporarily_unavailable",
            )
        elif scope is ScopeKind.PASSWORD_FAIL_ID_HOURLY:
            super().__init__(
                code="TEMPORARILY_UNAVAILABLE",
                message_key="auth.password.too_many_attempts",
            )
        elif scope is ScopeKind.CENTRE_ACCOUNT_DAILY:
            super().__init__(
                code="TEMPORARILY_UNAVAILABLE",
                message_key="centre.temporarily_unavailable",
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
    the few things that reach a human, the members of
    ``_ALERTING_SCOPES``. The per-number and per-IP
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
        *,
        coarse_prefix: str | None = None,
    ) -> None:
        """Consume one sign-in request's per-number and per-IP budget.

        Called **before** ``otp.issue``, for every number, known or not:
        these scopes bound a caller, and an unknown number must be
        bounded identically or the refusal becomes the oracle. The
        global send budget is NOT consumed here -- see
        :meth:`consume_send` [PA-SEC-2].

        A number in its dead-code cool-off [C-20] is refused first,
        consuming nothing.

        :param number: The phone number this send is for
        :param ip_prefix: The caller's IP prefix
        :param now: The moment to count against, or None for the clock
        :param coarse_prefix: The caller's /48 (IPv4: its /24), counted as
            a further scope when given [C-05]
        :return: None
        :raises CeilingBreach: A ceiling refused this send
        """
        self._refuse_cooled_off(number, now, during_signup=False)
        self._consume(self._scopes(number, ip_prefix, coarse_prefix), now)

    def check_and_consume_signup(
        self,
        number: str,
        ip_prefix: str,
        now: dt.datetime | None = None,
        *,
        coarse_prefix: str | None = None,
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

        Signup issues a code too, so a number in its dead-code cool-off
        is refused here as well [C-20].

        :param number: The number being signed up
        :param ip_prefix: The caller's IP prefix
        :param now: The moment to count against, or None for the clock
        :param coarse_prefix: The caller's /48, counted when given [C-05]
        :return: None
        :raises CeilingBreach: A ceiling refused this signup
        """
        self._refuse_cooled_off(number, now, during_signup=True)
        self._consume(self._signup_scopes(number, ip_prefix, coarse_prefix), now)

    def check_and_consume_lookup(
        self,
        number: str,
        ip_prefix: str,
        coarse_prefix: str,
        now: dt.datetime | None = None,
    ) -> None:
        """Consume one already-added lookup, refusing at the narrowest breach.

        **A cascade of its own, never signup's** [SEC-4]: the lookup is
        anonymous and repeatable, so sharing signup's per-number
        allowance let anyone stop a number from signing up by looking it
        up three times. Same ``_consume``, so the same narrowest-first
        order and release-on-refusal accounting.

        Called for every number, recorded or not, before anything is
        read: the refusal must not depend on whether a seat exists.

        A lookup the cascade lets through is then counted product-wide,
        alert-only: it alerts on the lookup that fills the hour's scope,
        once, and never refuses [SEC-4]. Served lookups are what
        disclose, so they are what is counted; a refused one is already
        bounded by the scope that refused it.

        :param number: The number looked up
        :param ip_prefix: The caller's /64 (IPv4: /24)
        :param coarse_prefix: The caller's /48 (IPv4: /24)
        :param now: The moment to count against, or None for the clock
        :return: None
        :raises CeilingBreach: A lookup ceiling refused this request
        """
        self._consume(
            [
                (
                    _Scope(
                        ScopeKind.LOOKUP_NUMBER_DAILY, LOOKUP_PER_NUMBER_DAILY, _DAY
                    ),
                    number,
                ),
                (
                    _Scope(ScopeKind.LOOKUP_IP_HOURLY, LOOKUP_PER_IP_HOURLY, _HOUR),
                    ip_prefix,
                ),
                (
                    _Scope(
                        ScopeKind.LOOKUP_IP48_HOURLY,
                        LOOKUP_PER_COARSE_IP_HOURLY,
                        _HOUR,
                    ),
                    coarse_prefix,
                ),
            ],
            now,
        )
        alerting = _Scope(ScopeKind.LOOKUP_GLOBAL_HOURLY, LOOKUP_GLOBAL_HOURLY, _HOUR)
        moment = now or dt.datetime.now(tz=dt.UTC)
        if self._increment(alerting, GLOBAL_SCOPE_VALUE, moment) == alerting.limit:
            fire_ceiling_alert(alerting.kind.value)

    def check_verify_allowed(
        self,
        ip_prefix: str,
        coarse_prefix: str,
        now: dt.datetime | None = None,
    ) -> None:
        """Refuse a verify while any failed-verify ceiling is full [C-20].

        **Read, never incremented**: only a FAILED verify counts, and it
        is counted by :meth:`record_verify_failure` once the code has
        been checked. A refusal here checks no code, writes no attempt
        and consumes nothing, so the person's own code still works from
        another network.

        :param ip_prefix: The caller's /64 (IPv4: /24)
        :param coarse_prefix: The caller's /48 (IPv4: /24)
        :param now: The moment to count against, or None for the clock
        :return: None
        :raises CeilingBreach: A failed-verify ceiling is full
        """
        moment = now or dt.datetime.now(tz=dt.UTC)
        for scope, value in self._verify_scopes(ip_prefix, coarse_prefix):
            if self._peek(scope, value, moment) >= scope.limit:
                raise CeilingBreach(scope.kind)

    def record_verify_failure(
        self,
        ip_prefix: str,
        coarse_prefix: str,
        now: dt.datetime | None = None,
    ) -> None:
        """Count one failed verify against the caller and the product.

        The global scope alerts on the failure that fills it, once per
        window, rather than on every refusal after.

        :param ip_prefix: The caller's /64 (IPv4: /24)
        :param coarse_prefix: The caller's /48 (IPv4: /24)
        :param now: The moment to count against, or None for the clock
        :return: None
        """
        moment = now or dt.datetime.now(tz=dt.UTC)
        for scope, value in self._verify_scopes(ip_prefix, coarse_prefix):
            count = self._increment(scope, value, moment)
            if scope.kind in _ALERTING_SCOPES and count == scope.limit:
                fire_ceiling_alert(scope.kind.value)

    def record_dead_code(self, number: str, now: dt.datetime | None = None) -> None:
        """Count one code that died at its attempt ceiling [C-20].

        Counted for a known and an unknown number alike: both keep code
        rows and both run the same verify path [BR2.7].

        :param number: The number whose code died
        :param now: The moment to count against, or None for the clock
        :return: None
        """
        moment = now or dt.datetime.now(tz=dt.UTC)
        self._increment(self._dead_code_scope(), number, moment)

    def check_password_allowed(
        self,
        rate_key: str,
        ip_prefix: str,
        coarse_prefix: str,
        now: dt.datetime | None = None,
    ) -> None:
        """Refuse a password sign-in while a failure ceiling is full [0032].

        The per-prefix failed-verify ceilings are shared with codes:
        guessing a password and guessing a code are the same activity,
        and one attacker should not get two allowances by alternating.
        The per-identifier ceiling is the password path's own.

        **The global failed-verify ceiling is not read here** [SEC-1].
        It is the codes' outage switch; a password has the
        per-identifier ceiling instead, and a full global count of
        anybody's failures must not refuse this person's sign-in.

        Read, never incremented, like :meth:`check_verify_allowed`.

        :param rate_key: The identifier's counter key
        :param ip_prefix: The caller's /64 (IPv4: /24)
        :param coarse_prefix: The caller's /48 (IPv4: /24)
        :param now: The moment to count against, or None for the clock
        :return: None
        :raises CeilingBreach: A failure ceiling is full
        """
        moment = now or dt.datetime.now(tz=dt.UTC)
        scope = self._password_scope()
        if self._peek(scope, rate_key, moment) >= scope.limit:
            raise CeilingBreach(scope.kind)
        for prefix_scope, value in self._prefix_verify_scopes(ip_prefix, coarse_prefix):
            if self._peek(prefix_scope, value, moment) >= prefix_scope.limit:
                raise CeilingBreach(prefix_scope.kind)

    def record_password_failure(
        self,
        rate_key: str,
        ip_prefix: str,
        coarse_prefix: str,
        now: dt.datetime | None = None,
    ) -> None:
        """Count one failed password against the identifier and the caller.

        The caller's /64 and /48 failed-verify counters are shared with
        codes. The product-wide count is the password path's own,
        alert-only scope, so it never fills the codes' global ceiling
        [SEC-1].

        :param rate_key: The identifier's counter key
        :param ip_prefix: The caller's /64 (IPv4: /24)
        :param coarse_prefix: The caller's /48 (IPv4: /24)
        :param now: The moment to count against, or None for the clock
        :return: None
        """
        moment = now or dt.datetime.now(tz=dt.UTC)
        self._increment(self._password_scope(), rate_key, moment)
        for scope, value in self._prefix_verify_scopes(ip_prefix, coarse_prefix):
            self._increment(scope, value, moment)
        alerting = _Scope(
            ScopeKind.PASSWORD_FAIL_GLOBAL_HOURLY,
            PASSWORD_FAILURES_GLOBAL_HOURLY,
            _HOUR,
        )
        if self._increment(alerting, GLOBAL_SCOPE_VALUE, moment) == alerting.limit:
            fire_ceiling_alert(alerting.kind.value)

    def check_and_consume_centre(
        self, account_id: uuid.UUID, now: dt.datetime | None = None
    ) -> None:
        """Consume one centre opening from the account's daily allowance.

        :param account_id: The authenticated account opening a centre
        :param now: The moment to count against, or None for the clock
        :return: None
        :raises CeilingBreach: The account has opened its allowance today
            [L-06]
        """
        scope = _Scope(ScopeKind.CENTRE_ACCOUNT_DAILY, CENTRES_PER_ACCOUNT_DAILY, _DAY)
        self._consume([(scope, str(account_id))], now)

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

        A number in its dead-code cool-off [C-20, SEC-6] is refused
        first, consuming nothing, exactly as sign-in and signup refuse
        it: the deletion route records its dead codes against the same
        per-number scope, and a cool-off that is counted here but never
        read here would let a guesser who exhausted sign-in's codes keep
        going on the route that destroys data. The refusal is the
        deletion cascade's own contentless one, identical for a known
        and an unknown number [BR2.7].

        :param number: The number a deletion code is being sent to
        :param ip_prefix: The caller's IP prefix
        :param now: The moment to count against, or None for the clock
        :return: None
        :raises CeilingBreach: A ceiling refused this send, or the number
            is in its dead-code cool-off
        """
        self._refuse_cooled_off(number, now, during_signup=False)
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
        limit = _BUDGET_LIMITS[budget]
        self._consume([(_Scope(budget.value, limit, _DAY), GLOBAL_SCOPE_VALUE)], now)

    def _refuse_cooled_off(
        self, number: str, now: dt.datetime | None, *, during_signup: bool
    ) -> None:
        """Refuse a new code for a number whose codes keep dying [C-20].

        :param number: The number a code is being requested for
        :param now: The moment to count against, or None for the clock
        :param during_signup: Whether the refusal is on the signup path
        :return: None
        :raises CeilingBreach: The number is in its cool-off
        """
        moment = now or dt.datetime.now(tz=dt.UTC)
        scope = self._dead_code_scope()
        if self._peek(scope, number, moment) >= scope.limit:
            raise CeilingBreach(scope.kind, during_signup=during_signup)

    def _peek(self, scope: _Scope, value: str, moment: dt.datetime) -> int:
        """Read one scope's count in the current window without changing it.

        :param scope: The scope to read
        :param value: Its scope value
        :param moment: The moment whose window is read
        :return: The count, or zero when no row exists yet
        """
        count = self.session.execute(
            sa.text(
                "SELECT count FROM rate_limit_counter WHERE scope_kind = :kind "
                "AND scope_value = :value AND window_start = :window"
            ),
            {
                "kind": scope.kind.value,
                "value": value,
                "window": _window_start(moment, scope.window),
            },
        ).scalar_one_or_none()
        return int(count or 0)

    def _increment(self, scope: _Scope, value: str, moment: dt.datetime) -> int:
        """Add one to a scope's counter with no limit check, and commit.

        :param scope: The scope to count against
        :param value: Its scope value
        :param moment: The moment whose window is counted
        :return: The count after the increment
        """
        count: int = self.session.execute(
            _UPSERT,
            {
                "kind": scope.kind.value,
                "value": value,
                "window": _window_start(moment, scope.window),
            },
        ).scalar_one()
        self.session.commit()
        return count

    @staticmethod
    def _dead_code_scope() -> _Scope:
        """Return the per-number dead-code scope [C-20].

        :return: The scope
        """
        return _Scope(
            ScopeKind.DEAD_CODE_NUMBER_DAILY, DEAD_CODES_PER_NUMBER_DAILY, _DAY
        )

    @staticmethod
    def _password_scope() -> _Scope:
        """Return the per-identifier failed-password scope [0032].

        :return: The scope
        """
        return _Scope(
            ScopeKind.PASSWORD_FAIL_ID_HOURLY,
            PASSWORD_FAILURES_PER_IDENTIFIER_HOURLY,
            _HOUR,
        )

    @classmethod
    def _verify_scopes(
        cls, ip_prefix: str, coarse_prefix: str
    ) -> list[tuple[_Scope, str]]:
        """Build the failed-verify scopes, narrowest first [C-20].

        :param ip_prefix: The caller's /64 (IPv4: /24)
        :param coarse_prefix: The caller's /48 (IPv4: /24)
        :return: Each scope paired with the value it counts against
        """
        return [
            *cls._prefix_verify_scopes(ip_prefix, coarse_prefix),
            (
                _Scope(
                    ScopeKind.VERIFY_FAIL_GLOBAL_HOURLY,
                    VERIFY_FAILURES_GLOBAL_HOURLY,
                    _HOUR,
                ),
                GLOBAL_SCOPE_VALUE,
            ),
        ]

    @staticmethod
    def _prefix_verify_scopes(
        ip_prefix: str, coarse_prefix: str
    ) -> list[tuple[_Scope, str]]:
        """Build the per-caller failed-verify scopes, narrowest first.

        Shared by codes and passwords; the product-wide scope is not
        [SEC-1].

        :param ip_prefix: The caller's /64 (IPv4: /24)
        :param coarse_prefix: The caller's /48 (IPv4: /24)
        :return: Each scope paired with the value it counts against
        """
        return [
            (
                _Scope(
                    ScopeKind.VERIFY_FAIL_IP_HOURLY,
                    VERIFY_FAILURES_PER_IP_HOURLY,
                    _HOUR,
                ),
                ip_prefix,
            ),
            (
                _Scope(
                    ScopeKind.VERIFY_FAIL_IP48_HOURLY,
                    VERIFY_FAILURES_PER_COARSE_IP_HOURLY,
                    _HOUR,
                ),
                coarse_prefix,
            ),
        ]

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
    def _scopes(
        number: str, ip_prefix: str, coarse_prefix: str | None = None
    ) -> list[tuple[_Scope, str]]:
        """Build the cascade, narrowest first.

        :param number: The phone number
        :param ip_prefix: The caller's IP prefix
        :param coarse_prefix: The caller's /48, or None to omit that scope
        :return: Each scope paired with the value it counts against
        """
        cascade = [
            (_Scope(ScopeKind.NUMBER_HOURLY, PER_NUMBER_HOURLY, _HOUR), number),
            (_Scope(ScopeKind.NUMBER_DAILY, PER_NUMBER_DAILY, _DAY), number),
            (_Scope(ScopeKind.IP_HOURLY, PER_IP_HOURLY, _HOUR), ip_prefix),
        ]
        if coarse_prefix is not None:
            cascade.append(
                (
                    _Scope(ScopeKind.IP48_HOURLY, PER_COARSE_IP_HOURLY, _HOUR),
                    coarse_prefix,
                )
            )
        return cascade

    @staticmethod
    def _signup_scopes(
        number: str, ip_prefix: str, coarse_prefix: str | None = None
    ) -> list[tuple[_Scope, str]]:
        """Build the signup cascade, narrowest first.

        **Narrowest first, like its sibling, and for the reason the
        module docstring records**: global-first lets one attacker
        exhaust every legitimate user's allowance before their own
        limit trips, and it *still looks like* defence in depth --
        which is exactly why a second cascade is where that mistake
        would return [NFR12.4].

        **No global scope on the request path, and that is a decision.**
        Signup's cost to the project is the SMS it triggers, and that
        send spends signup's OWN daily send budget,
        :attr:`SendBudget.SIGNUP`, at send time [C-05]. A request-path
        global counter would bound the same spend twice at two
        thresholds, so the tighter one would silently become the real
        limit and the looser one would read as a control while governing
        nothing.

        :param number: The number being signed up
        :param ip_prefix: The caller's IP prefix
        :param coarse_prefix: The caller's /48, or None to omit that scope
        :return: Each scope paired with the value it counts against
        """
        cascade = [
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
        if coarse_prefix is not None:
            cascade.append(
                (
                    _Scope(
                        ScopeKind.SIGNUP_IP48_HOURLY,
                        SIGNUP_PER_COARSE_IP_HOURLY,
                        _HOUR,
                    ),
                    coarse_prefix,
                )
            )
        return cascade

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
