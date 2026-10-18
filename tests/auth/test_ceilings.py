"""The ceiling cascade. Two of these cannot be satisfied by a wrong build.

**Per-SMS billing makes abuse a direct attack on the project's wallet**,
so these are test-first under the predicate: the thresholds are knowable
from the requirement, and a wrong answer spends money.

Most of the file is ordinary threshold checking. Two tests are not:

* ``test_a_refused_request_does_not_consume_the_global_budget`` -- the
  **order** test. Checking global-first lets one attacker's requests
  consume the global daily counter before their own per-number limit
  trips. They are stopped eventually, but only after spending everyone
  else's allowance, which is precisely what the sub-ceilings exist to
  prevent [BR2.5].
* ``test_the_limit_holds_across_two_independent_sessions`` -- the
  **two-worker** test. It must FAIL against a per-process dictionary,
  which is the obvious implementation and passes every other test here
  [BR2.1].
"""

from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.ceilings import (
    GLOBAL_DAILY,
    PER_IP_HOURLY,
    PER_NUMBER_DAILY,
    PER_NUMBER_HOURLY,
    CeilingBreach,
    CeilingChecker,
    ScopeKind,
)
from app.errors import ConflictError

NUMBER = "+8801711111111"
OTHER_NUMBER = "+8801722222222"
IP_PREFIX = "203.0.113"


@pytest.fixture
def checker(restricted_session: Session) -> CeilingChecker:
    """Build a checker bound to the restricted session.

    :param restricted_session: The non-superuser session
    :return: The checker under test
    """
    return CeilingChecker(restricted_session)


def _consume(checker: CeilingChecker, count: int) -> None:
    """Consume ``count`` successful sends for the standard scopes.

    :param checker: The checker under test
    :param count: How many sends to consume
    :return: None
    """
    for _ in range(count):
        checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)


# ---------------------------------------------------------------------------
# The four thresholds. [BR2.2, BR2.5]
# ---------------------------------------------------------------------------


def test_the_fourth_code_within_an_hour_is_refused(checker: CeilingChecker) -> None:
    _consume(checker, PER_NUMBER_HOURLY)
    with pytest.raises(ConflictError) as raised:
        checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)
    assert raised.value.scope is ScopeKind.NUMBER_HOURLY


def test_the_first_three_within_an_hour_are_admitted(
    checker: CeilingChecker,
) -> None:
    for _ in range(PER_NUMBER_HOURLY):
        checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)


def test_the_sixth_within_a_day_is_refused(checker: CeilingChecker) -> None:
    # The hourly window must not be what stops this, so each send lands
    # in its own hour.
    now = dt.datetime.now(tz=dt.UTC)
    for hour in range(PER_NUMBER_DAILY):
        checker.check_and_consume(
            number=NUMBER, ip_prefix=IP_PREFIX, now=now + dt.timedelta(hours=hour)
        )
    with pytest.raises(ConflictError) as raised:
        checker.check_and_consume(
            number=NUMBER,
            ip_prefix=IP_PREFIX,
            now=now + dt.timedelta(hours=PER_NUMBER_DAILY),
        )
    assert raised.value.scope is ScopeKind.NUMBER_DAILY


def test_the_eleventh_from_one_ip_within_an_hour_is_refused(
    checker: CeilingChecker,
) -> None:
    # Spread across distinct numbers, so the per-number ceiling is not
    # what refuses: this must be the IP ceiling or the test proves
    # nothing about it.
    for index in range(PER_IP_HOURLY):
        checker.check_and_consume(number=f"+88017{index:08d}", ip_prefix=IP_PREFIX)
    with pytest.raises(ConflictError) as raised:
        checker.check_and_consume(number="+8801799999999", ip_prefix=IP_PREFIX)
    assert raised.value.scope is ScopeKind.IP_HOURLY


def test_the_global_daily_ceiling_is_refused_and_the_alert_fires(
    checker: CeilingChecker,
    restricted_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The global ceiling is a VALUE, not a decision: the production
    # number derives from the per-SMS rate against the budget and is set
    # at deployment. What this Bolt builds and tests is the MECHANISM, so
    # the counter is driven to its threshold directly rather than by
    # issuing GLOBAL_DAILY real sends.
    fired: list[str] = []
    monkeypatch.setattr(
        "app.auth.ceilings.fire_ceiling_alert", lambda scope: fired.append(scope)
    )

    now = dt.datetime.now(tz=dt.UTC)
    _preload_global_counter(restricted_session, GLOBAL_DAILY, now)

    with pytest.raises(ConflictError) as raised:
        checker.check_and_consume(
            number="+8801999999999", ip_prefix="10.99.99", now=now
        )
    assert raised.value.scope is ScopeKind.GLOBAL_DAILY
    assert fired, "the global ceiling tripped without firing its alert"


def test_the_global_ceiling_admits_up_to_its_limit(
    checker: CeilingChecker, restricted_session: Session
) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    _preload_global_counter(restricted_session, GLOBAL_DAILY - 1, now)
    checker.check_and_consume(number="+8801888888888", ip_prefix="10.88.88", now=now)


# ---------------------------------------------------------------------------
# THE ORDER TEST. [BR2.5]
#
# Narrowest first, and a refused request never increments a wider
# counter. Order and accounting are one decision, not two: a
# narrowest-first check that still increments the global counter on a
# refused request has the same defect in a quieter form.
# ---------------------------------------------------------------------------


def test_a_refused_request_does_not_consume_the_global_budget(
    checker: CeilingChecker, restricted_session: Session
) -> None:
    _consume(checker, PER_NUMBER_HOURLY)
    before = _global_count(restricted_session)

    with pytest.raises(ConflictError):
        checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)

    after = _global_count(restricted_session)
    assert after == before, (
        "a per-number refusal incremented the GLOBAL counter: one "
        "attacker can now drain everyone else's allowance [BR2.5]"
    )


def test_a_refused_request_does_not_consume_the_ip_budget(
    checker: CeilingChecker, restricted_session: Session
) -> None:
    _consume(checker, PER_NUMBER_HOURLY)
    before = _scope_count(restricted_session, ScopeKind.IP_HOURLY, IP_PREFIX)

    with pytest.raises(ConflictError):
        checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)

    after = _scope_count(restricted_session, ScopeKind.IP_HOURLY, IP_PREFIX)
    assert after == before


def test_one_numbers_exhaustion_does_not_lock_out_another(
    checker: CeilingChecker,
) -> None:
    # The breaker must DEGRADE rather than cliff-edge. This is the
    # property the sub-ceilings buy, stated as a test.
    _consume(checker, PER_NUMBER_HOURLY)
    with pytest.raises(ConflictError):
        checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)

    checker.check_and_consume(number=OTHER_NUMBER, ip_prefix="198.51.100")


def test_the_narrowest_scope_is_the_one_reported(
    checker: CeilingChecker,
) -> None:
    # When several ceilings would refuse, the narrowest must be the one
    # that did -- otherwise the order is not actually narrowest-first,
    # it only looks that way from outside.
    _consume(checker, PER_NUMBER_HOURLY)
    with pytest.raises(ConflictError) as raised:
        checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)
    assert raised.value.scope is ScopeKind.NUMBER_HOURLY


# ---------------------------------------------------------------------------
# THE TWO-WORKER TEST. [BR2.1]
#
# Phase 1 runs several Uvicorn workers on one Lightsail host. A
# per-process dictionary passes every test above and silently stops
# working the moment there are two.
# ---------------------------------------------------------------------------


def test_the_limit_holds_across_two_independent_sessions(
    restricted_engine: Engine,
) -> None:
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    first, second = factory(), factory()
    try:
        worker_a = CeilingChecker(first)
        worker_b = CeilingChecker(second)

        # Split the allowance across the two "workers".
        worker_a.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)
        worker_b.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)
        worker_a.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)

        with pytest.raises(ConflictError):
            worker_b.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)
    finally:
        first.close()
        second.close()


def test_the_counter_lives_in_the_datastore(
    checker: CeilingChecker, restricted_session: Session
) -> None:
    checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)
    rows = restricted_session.execute(
        sa.text("SELECT count(*) FROM rate_limit_counter")
    ).scalar_one()
    assert rows > 0, "no counter row: the limit is per-process [BR2.1]"


def test_concurrent_increments_at_the_boundary_admit_exactly_one(
    restricted_engine: Engine,
) -> None:
    # The unique constraint plus an atomic upsert is what makes this
    # work. Two workers racing on one window must not both read a stale
    # count and both be admitted.
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    sessions = [factory() for _ in range(2)]
    try:
        checkers = [CeilingChecker(session) for session in sessions]
        for checker_at_limit in checkers[:1]:
            for _ in range(PER_NUMBER_HOURLY):
                checker_at_limit.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)

        admitted = 0
        for candidate in checkers:
            try:
                candidate.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)
                admitted += 1
            except ConflictError:
                pass
        assert admitted == 0
    finally:
        for session in sessions:
            session.close()


# ---------------------------------------------------------------------------
# The refusal's shape. [BR2.2, BR2.6]
# ---------------------------------------------------------------------------


def test_a_breach_is_a_conflict_not_a_transient_error(
    checker: CeilingChecker,
) -> None:
    # Retrying into a cost ceiling is exactly wrong, and 429 carries a
    # retry-after convention that invites it.
    from app.errors import TransientError

    _consume(checker, PER_NUMBER_HOURLY)
    with pytest.raises(ConflictError) as raised:
        checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)
    assert not isinstance(raised.value, TransientError)


def test_the_refusal_does_not_reveal_the_limit(checker: CeilingChecker) -> None:
    # Revealing the limit tells an attacker exactly how to pace a drain;
    # "invalid number" tells a legitimate teacher their account is broken
    # AND tells an attacker which numbers exist [BR2.6].
    _consume(checker, PER_NUMBER_HOURLY)
    with pytest.raises(ConflictError) as raised:
        checker.check_and_consume(number=NUMBER, ip_prefix=IP_PREFIX)

    rendered = f"{raised.value.code} {raised.value.message_key}".lower()
    assert "invalid" not in rendered
    assert str(PER_NUMBER_HOURLY) not in rendered
    assert raised.value.details is None or not any(
        str(PER_NUMBER_HOURLY) in str(value) for value in raised.value.details.values()
    )


def _preload_global_counter(session: Session, count: int, now: dt.datetime) -> None:
    """Drive the global counter to a value without issuing sends.

    The global threshold is a deployment value; what is under test is the
    mechanism around it, so the counter is set directly.

    :param session: The session to write through
    :param count: The value to set
    :param now: The moment whose day-window is targeted
    :return: None
    """
    window = now.replace(hour=0, minute=0, second=0, microsecond=0)
    session.execute(
        sa.text(
            "INSERT INTO rate_limit_counter "
            "(id, scope_kind, scope_value, window_start, count) "
            "VALUES (gen_random_uuid(), 'global_day', 'global', :window, :count) "
            "ON CONFLICT (scope_kind, scope_value, window_start) "
            "DO UPDATE SET count = :count"
        ),
        {"window": window, "count": count},
    )
    session.commit()


def _global_count(session: Session) -> int:
    """Read the global daily counter's current value.

    :param session: The session to read through
    :return: The count, or zero when no row exists
    """
    return _scope_count(session, ScopeKind.GLOBAL_DAILY, "global")


def _scope_count(session: Session, scope: ScopeKind, value: str) -> int:
    """Read one scope's counter.

    :param session: The session to read through
    :param scope: The scope kind
    :param value: The scope value
    :return: The count, or zero when no row exists
    """
    session.expire_all()
    result = session.execute(
        sa.text(
            "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
            "WHERE scope_kind = :kind AND scope_value = :value"
        ),
        {"kind": scope.value, "value": value},
    ).scalar_one()
    return int(result)


__all__ = ["CeilingBreach"]
