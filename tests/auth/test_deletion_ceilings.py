"""Deletion's ceilings are its own counters, not the sign-in ones.

**The single most important sentence about this file**: a test asserting
only that the deletion route refuses at its limit **passes against the
defect it exists to catch**. If deletion reused ``ScopeKind.NUMBER_*``,
draining it would also refuse -- correctly, from the attacker's view --
and a refusal-only test is green while a victim is locked out of signing
in [NFR14.100].

**The assertion that distinguishes the two implementations is that
SIGN-IN STILL WORKS.** Two of the tests below are written that way and
they are the two that matter; the threshold tests are ordinary.

Test-first under the ordering predicate: the four limits are knowable
from the requirement without the code, and a wrong answer exhausts a
victim's sign-in allowance from an unauthenticated public route, which
is an authorization error.

``DEL_GLOBAL_DAILY`` is the **load-bearing** control, which is the
opposite of how a reader would rank the four [DESIGN-6]. ``ip_prefix_of``
reduces IPv4 to a /24, so an attacker spanning prefixes never meets the
per-IP limit; and an IPv6 address contains no ``.``, so each IPv6 caller
gets its own whole-address counter. Neither is fixed here -- it is a
shared primitive with three built dependents and this is the last unit
before release -- so the global sub-ceiling is what actually binds.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.auth.ceilings import (
    DEL_GLOBAL_DAILY,
    DEL_PER_IP_HOURLY,
    DEL_PER_NUMBER_DAILY,
    DEL_PER_NUMBER_HOURLY,
    PER_NUMBER_DAILY,
    CeilingBreach,
    CeilingChecker,
    ScopeKind,
)

NUMBER: Final = "+8801744444444"
OTHER_NUMBER: Final = "+8801755555555"
IP_PREFIX: Final = "198.51.100"


@pytest.fixture
def checker(restricted_session: Session) -> CeilingChecker:
    """Build a checker bound to the restricted session.

    :param restricted_session: The non-superuser session
    :return: The checker under test
    """
    return CeilingChecker(restricted_session)


def _drain_deletion(
    checker: CeilingChecker,
    count: int,
    *,
    number: str = NUMBER,
    ip_prefix: str = IP_PREFIX,
    now: dt.datetime | None = None,
) -> None:
    """Consume ``count`` deletion-code budgets.

    :param checker: The checker under test
    :param count: How many to consume
    :param number: The number to count against
    :param ip_prefix: The prefix to count against
    :param now: The moment to count against, or None for the clock
    :return: None
    """
    for _ in range(count):
        checker.check_and_consume_deletion(number=number, ip_prefix=ip_prefix, now=now)


def _count(session: Session, kind: ScopeKind, value: str) -> int:
    """Read one scope's current counter total.

    :param session: The session to read through
    :param kind: The scope kind
    :param value: The scope value
    :return: The summed count across windows
    """
    total = session.execute(
        sa.text(
            "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
            "WHERE scope_kind = :kind AND scope_value = :value"
        ),
        {"kind": kind.value, "value": value},
    ).scalar_one()
    return int(total)


# ---------------------------------------------------------------------------
# THE TWO TESTS THAT MATTER. [NFR14.100, NFR14.102]
#
# Both assert that something still WORKS. Against a shared-counter
# implementation, each of these FAILS and every threshold test below
# still passes.
# ---------------------------------------------------------------------------


def test_exhausting_the_deletion_number_scope_leaves_sign_in_working(
    checker: CeilingChecker,
) -> None:
    """Drain ``del_number_day``; a sign-in code must still issue.

    The attack this closes: an unauthenticated caller spends a victim's
    deletion allowance from the public route, and if the counters were
    shared the victim could no longer sign in.

    :param checker: The checker under test
    :return: None
    """
    # Spread over distinct hours, so the HOURLY scope does not refuse
    # at the fourth call and leave the daily one undrained. A test that
    # let the hourly scope refuse here would be asserting the wrong
    # ceiling while reading as though it asserted this one.
    base = dt.datetime(2026, 11, 1, 1, 0, tzinfo=dt.UTC)
    for hour in range(DEL_PER_NUMBER_DAILY):
        _drain_deletion(checker, 1, now=base + dt.timedelta(hours=hour))

    exhausted = base + dt.timedelta(hours=DEL_PER_NUMBER_DAILY)
    with pytest.raises(CeilingBreach) as refused:
        checker.check_and_consume_deletion(
            number=NUMBER, ip_prefix=IP_PREFIX, now=exhausted
        )
    assert refused.value.scope is ScopeKind.DEL_NUMBER_DAILY

    # The whole point. If this raises, deletion is counting against
    # sign-in's allowance and a victim has been locked out.
    checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX, now=exhausted)


def test_draining_the_deletion_global_scope_leaves_sign_in_working(
    checker: CeilingChecker,
) -> None:
    """Drain ``del_global_day``; sign-in's global budget is untouched.

    NFR14.102's sub-ceiling exists precisely so one consumer cannot
    exhaust another's. Signup's no-global decision deliberately does not
    transfer: signup's cost passes through the OTP global ceiling
    immediately afterwards, while deletion's hazard is that it spends
    **the same budget sign-in needs**.

    :param checker: The checker under test
    :return: None
    """
    # A DIFFERENT number AND a different prefix per call, so neither
    # narrower scope refuses first -- the global one is under test, and
    # a narrower refusal would mask it while the test still went green
    # on `pytest.raises`.
    for index in range(DEL_GLOBAL_DAILY):
        _drain_deletion(
            checker,
            1,
            number=f"+88017000{index:05d}",
            ip_prefix=f"198.51.{index}",
        )

    with pytest.raises(CeilingBreach) as refused:
        checker.check_and_consume_deletion(
            number="+8801790000000", ip_prefix="198.51.250"
        )
    assert refused.value.scope is ScopeKind.DEL_GLOBAL_DAILY

    checker.check_and_consume(number=OTHER_NUMBER, ip_prefix=IP_PREFIX)


# ---------------------------------------------------------------------------
# The four thresholds.
# ---------------------------------------------------------------------------


def test_the_hourly_number_scope_refuses_past_its_limit(
    checker: CeilingChecker,
) -> None:
    """The fourth deletion code for one number inside an hour refuses.

    :param checker: The checker under test
    :return: None
    """
    _drain_deletion(checker, DEL_PER_NUMBER_HOURLY)

    with pytest.raises(CeilingBreach) as refused:
        checker.check_and_consume_deletion(number=NUMBER, ip_prefix=IP_PREFIX)

    assert refused.value.scope is ScopeKind.DEL_NUMBER_HOURLY


def test_the_daily_number_scope_refuses_past_its_limit(
    checker: CeilingChecker,
) -> None:
    """The sixth inside a day refuses, across separate hours.

    Spread over distinct hours deliberately: inside one hour the hourly
    scope refuses first, and a test that let it would be asserting the
    wrong ceiling while reading as if it asserted this one.

    :param checker: The checker under test
    :return: None
    """
    base = dt.datetime(2026, 11, 2, 1, 0, tzinfo=dt.UTC)
    for hour in range(DEL_PER_NUMBER_DAILY):
        _drain_deletion(checker, 1, now=base + dt.timedelta(hours=hour))

    with pytest.raises(CeilingBreach) as refused:
        checker.check_and_consume_deletion(
            number=NUMBER,
            ip_prefix=IP_PREFIX,
            now=base + dt.timedelta(hours=DEL_PER_NUMBER_DAILY),
        )

    assert refused.value.scope is ScopeKind.DEL_NUMBER_DAILY


def test_the_hourly_ip_scope_refuses_past_its_limit(
    checker: CeilingChecker,
) -> None:
    """The eleventh from one prefix inside an hour refuses.

    Each call uses a different number so the per-number scopes do not
    refuse first.

    :param checker: The checker under test
    :return: None
    """
    for index in range(DEL_PER_IP_HOURLY):
        _drain_deletion(checker, 1, number=f"+88018000{index:05d}")

    with pytest.raises(CeilingBreach) as refused:
        checker.check_and_consume_deletion(number="+8801890000000", ip_prefix=IP_PREFIX)

    assert refused.value.scope is ScopeKind.DEL_IP_HOURLY


def test_the_global_scope_refuses_past_its_limit(
    checker: CeilingChecker,
) -> None:
    """The fifty-first in a day refuses, with the narrower scopes clear.

    Each call uses a distinct number AND a distinct prefix, so neither
    narrower scope can be the one that refuses.

    :param checker: The checker under test
    :return: None
    """
    for index in range(DEL_GLOBAL_DAILY):
        _drain_deletion(
            checker,
            1,
            number=f"+88019000{index:05d}",
            ip_prefix=f"203.0.{index}",
        )

    with pytest.raises(CeilingBreach) as refused:
        checker.check_and_consume_deletion(
            number="+8801990000000", ip_prefix="203.0.250"
        )

    assert refused.value.scope is ScopeKind.DEL_GLOBAL_DAILY


# ---------------------------------------------------------------------------
# The accounting, inherited from `_consume` and asserted anyway.
# ---------------------------------------------------------------------------


def test_a_refusal_consumes_nothing(
    checker: CeilingChecker, restricted_session: Session
) -> None:
    """The refusing scope's own increment is released.

    Narrowest-first with release-on-refusal is the control, and D6
    writes no new ``_consume``, so it cannot get this wrong -- which is
    the argument for a third cascade over a bespoke limiter. Asserted
    regardless, because "it cannot get this wrong" is a claim.

    :param checker: The checker under test
    :param restricted_session: The non-superuser session
    :return: None
    """
    _drain_deletion(checker, DEL_PER_NUMBER_HOURLY)
    before = _count(restricted_session, ScopeKind.DEL_NUMBER_HOURLY, NUMBER)

    with pytest.raises(CeilingBreach):
        checker.check_and_consume_deletion(number=NUMBER, ip_prefix=IP_PREFIX)

    after = _count(restricted_session, ScopeKind.DEL_NUMBER_HOURLY, NUMBER)
    assert after == before


def test_a_deletion_refusal_does_not_consume_the_wider_scopes(
    checker: CeilingChecker, restricted_session: Session
) -> None:
    """A refusal at the narrowest scope never touches the global one.

    Checking global-first still *looks* like defence in depth, which is
    exactly why a third cascade is where that mistake would return.

    :param checker: The checker under test
    :param restricted_session: The non-superuser session
    :return: None
    """
    _drain_deletion(checker, DEL_PER_NUMBER_HOURLY)
    before = _count(restricted_session, ScopeKind.DEL_GLOBAL_DAILY, "global")

    with pytest.raises(CeilingBreach):
        checker.check_and_consume_deletion(number=NUMBER, ip_prefix=IP_PREFIX)

    after = _count(restricted_session, ScopeKind.DEL_GLOBAL_DAILY, "global")
    assert after == before


def test_a_sign_in_refusal_does_not_consume_the_deletion_allowance(
    checker: CeilingChecker, restricted_session: Session
) -> None:
    """The reverse direction, which the sign-in tests cannot assert.

    A deletion request refused because the caller already drained their
    SIGN-IN allowance would be the shared-counter defect pointing the
    other way, and it would be just as wrong.

    :param checker: The checker under test
    :param restricted_session: The non-superuser session
    :return: None
    """
    base = dt.datetime(2026, 11, 3, 1, 0, tzinfo=dt.UTC)
    for hour in range(PER_NUMBER_DAILY):
        checker.check_and_consume(
            number=NUMBER,
            ip_prefix=IP_PREFIX,
            now=base + dt.timedelta(hours=hour),
        )

    with pytest.raises(CeilingBreach):
        checker.check_and_consume(
            number=NUMBER,
            ip_prefix=IP_PREFIX,
            now=base + dt.timedelta(hours=PER_NUMBER_DAILY),
        )

    checker.check_and_consume_deletion(
        number=NUMBER,
        ip_prefix=IP_PREFIX,
        now=base + dt.timedelta(hours=PER_NUMBER_DAILY),
    )


# ---------------------------------------------------------------------------
# The alert, and the column.
# ---------------------------------------------------------------------------


def test_the_alert_fires_on_the_global_scope(
    checker: CeilingChecker, caplog: pytest.LogCaptureFixture
) -> None:
    """``del_global_day`` is the one scope whose breach has no innocent
    explanation.

    Sign-in's global ceiling tripping might be a busy day. Fifty
    deletion codes in a day is an attack.

    :param checker: The checker under test
    :param caplog: The log capture fixture
    :return: None
    """
    for index in range(DEL_GLOBAL_DAILY):
        _drain_deletion(
            checker,
            1,
            number=f"+88016000{index:05d}",
            ip_prefix=f"192.0.{index}",
        )

    with caplog.at_level("CRITICAL", logger="app.auth.ceilings"):
        with pytest.raises(CeilingBreach):
            checker.check_and_consume_deletion(
                number="+8801690000000", ip_prefix="192.0.250"
            )

    assert [record.scope for record in caplog.records] == [
        ScopeKind.DEL_GLOBAL_DAILY.value
    ]


def test_the_alert_does_not_fire_on_the_narrower_scopes(
    checker: CeilingChecker, caplog: pytest.LogCaptureFixture
) -> None:
    """Per-number and per-IP breaches stay silent.

    They fire constantly once the product has users, which trains the
    operator to ignore the one alert that matters sitting in the same
    channel.

    :param checker: The checker under test
    :param caplog: The log capture fixture
    :return: None
    """
    _drain_deletion(checker, DEL_PER_NUMBER_HOURLY)

    with caplog.at_level("CRITICAL", logger="app.auth.ceilings"):
        with pytest.raises(CeilingBreach):
            checker.check_and_consume_deletion(number=NUMBER, ip_prefix=IP_PREFIX)

    assert caplog.records == []


@pytest.mark.parametrize(
    "scope",
    [
        ScopeKind.DEL_NUMBER_HOURLY,
        ScopeKind.DEL_NUMBER_DAILY,
        ScopeKind.DEL_IP_HOURLY,
        ScopeKind.DEL_GLOBAL_DAILY,
    ],
)
def test_each_scope_value_fits_the_column(scope: ScopeKind) -> None:
    """``rate_limit_counter.scope_kind`` is ``String(16)``.

    The obvious prefixes do not fit -- ``deletion_number_day`` is 19 and
    ``delete_number_day`` is 17 -- and PostgreSQL refuses such a value
    outright, loudly, at the first deletion request. The ``del_`` prefix
    is the design and this asserts the arithmetic rather than trusting
    a comment.

    :param scope: The scope under test
    :return: None
    """
    assert len(scope.value) <= 16, scope.value


def test_the_deletion_counters_are_written_under_their_own_kinds(
    checker: CeilingChecker, restricted_session: Session
) -> None:
    """A successful deletion check writes four ``del_*`` rows and no more.

    This is the structural half of the shared-counter assertion: the
    behavioural tests above would also pass against an implementation
    that wrote the right rows and ALSO incremented sign-in's, so the
    sign-in scopes are asserted untouched.

    :param checker: The checker under test
    :param restricted_session: The non-superuser session
    :return: None
    """
    _drain_deletion(checker, 1)

    kinds = (
        restricted_session.execute(
            sa.text("SELECT DISTINCT scope_kind FROM rate_limit_counter")
        )
        .scalars()
        .all()
    )

    assert sorted(kinds) == sorted(
        {
            ScopeKind.DEL_NUMBER_HOURLY.value,
            ScopeKind.DEL_NUMBER_DAILY.value,
            ScopeKind.DEL_IP_HOURLY.value,
            ScopeKind.DEL_GLOBAL_DAILY.value,
        }
    )


def test_the_deletion_counters_carry_the_existing_retention_class() -> None:
    """``rate_limit_counter`` already carries a finite window.

    The four new scopes need **no new retention entry**: they are rows
    in a table whose class is already ``HOURS_48``, which is longer than
    every ceiling window it serves -- so a counter is never deleted
    while it is still being enforced against [DESIGN-7].

    A new counter kind whose rows were never purged would accumulate one
    row per number per day indefinitely, and nothing in the ceiling path
    would notice.

    :return: None
    """
    from app.governance.dispositions import RETENTION, RetentionClass

    assert RETENTION["rate_limit_counter"] is RetentionClass.HOURS_48
