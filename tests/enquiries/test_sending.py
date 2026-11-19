"""The guardian's side of a join request: describe, send and read their own.

**Written before the implementation.** The contact rule (Review Focus 1), the
one-open-request race (Review Focus 3) and the guardian's own-row scoping are
authorization predicates: a wrong answer leaks a number or shows a family
another family's request.

The world is arranged through the table-owner session; every call under test
runs through the restricted application role.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import threading
import uuid
from dataclasses import fields
from typing import Final

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.auth.ceilings import HUB_ENQUIRY_ACCOUNT_DAILY, CeilingBreach, ScopeKind
from app.errors import ConflictError, TaxonomyError, ValidationError
from app.errors.handler import to_response
from app.governance.commands import WINDOWS
from app.hub.enquiries import sending
from app.notifications.inbox import HUB_ENQUIRY_ANSWERED, HUB_ENQUIRY_RECEIVED
from tests.enquiries.support import close, enquirable_owner, guardian

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: A morning in Dhaka; every send in a test that does not care uses it.
NOW = dt.datetime(2026, 11, 19, 4, 0, tzinfo=dt.UTC)


def _send(
    session: Session,
    account: uuid.UUID,
    slug: str,
    *,
    batch_id: uuid.UUID | None = None,
    student_name: str = "Nadia Rahman",
    class_level: str = "class_8",
    message: str | None = None,
    share_contact: bool = True,
    now: dt.datetime = NOW,
) -> sending.MyEnquiry:
    return sending.send(
        session,
        account,
        slug,
        student_name=student_name,
        class_level=class_level,
        message=message,
        batch_id=batch_id,
        share_contact=share_contact,
        now=now,
    )


def _count(session: Session, sql: str, **values: object) -> int:
    session.rollback()
    return int(session.execute(sa.text(sql), values).scalar_one())


def _spent(session: Session, account: uuid.UUID) -> int:
    """Read an account's join-request counter, summed over every day.

    :param session: An arranging session
    :param account: The sending account
    :return: The total counted
    """
    return _count(
        session,
        "SELECT coalesce(sum(count), 0) FROM rate_limit_counter "
        "WHERE scope_kind = 'hub_enquiry_day' AND scope_value = :a",
        a=str(account),
    )


def _enquiries(session: Session) -> int:
    return _count(session, "SELECT count(*) FROM listing_enquiry")


REFUSED = [
    pytest.param("message", "Nadia", "০১৭১২৩৪৫৬৭৮", id="bangla-digits-in-message"),
    pytest.param("student_name", "017 1234 5678", None, id="spaced-number-in-name"),
    pytest.param("message", "Nadia", "wa.me/8801712345678", id="whatsapp-link"),
    pytest.param("message", "Nadia", "see www.rahim-tutor.example", id="www-address"),
    pytest.param("message", "Nadia", "call +880 1712-345678", id="country-code"),
    pytest.param("student_name", "Nadia facebook.com/nadia", None, id="url-in-name"),
]

PASSING = [
    pytest.param("Nadia", "Class 8, wants Physics and Maths", id="ordinary"),
    pytest.param("Nadia", "can come after 4.30 pm", id="decimal-time"),
    pytest.param("Nadia", "Fees 1500 or 2000 taka, 2025 SSC", id="numbers"),
]


@pytest.mark.parametrize(("field", "name", "message"), REFUSED)
def test_contact_in_text_refused_both_ways(
    owner_session: Session,
    restricted_session: Session,
    field: str,
    name: str,
    message: str | None,
) -> None:
    """Review Focus 1: the number travels only through the consent box.

    A guardian who leaves "share" unticked cannot type the number instead;
    the refusal stores nothing and counts nothing.
    """
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)

    with pytest.raises(ValidationError) as refused:
        _send(
            restricted_session,
            caller,
            world.owner_slug,
            student_name=name,
            message=message,
            share_contact=False,
        )

    assert refused.value.code == "ENQUIRY_CONTAINS_CONTACT"
    assert refused.value.message_key == "hub.enquiry.contains_contact"
    assert refused.value.details == {"field": field}
    assert to_response(refused.value).status_code == 400
    assert _enquiries(owner_session) == 0
    assert _spent(owner_session, caller) == 0
    assert _count(owner_session, "SELECT count(*) FROM notification") == 0


@pytest.mark.parametrize(("name", "message"), PASSING)
def test_contact_in_text_refused_both_ways_passes_ordinary_text(
    owner_session: Session, restricted_session: Session, name: str, message: str
) -> None:
    """The other half of Review Focus 1: ordinary text is not a contact."""
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)

    sent = _send(
        restricted_session, caller, world.owner_slug, student_name=name, message=message
    )

    assert sent.message == message
    assert _enquiries(owner_session) == 1


def test_send_stores_typed_fields_and_notifies_every_manager(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session, centre=True)
    caller = guardian(owner_session)
    # 19:30 UTC is 01:30 the next day in Dhaka.
    late = dt.datetime(2026, 11, 19, 19, 30, tzinfo=dt.UTC)

    sent = _send(
        restricted_session,
        caller,
        world.owner_slug,
        batch_id=world.batch_id,
        student_name="  Nadia Rahman  ",
        class_level="ssc",
        message="  Wants Physics  ",
        share_contact=False,
        now=late,
    )

    row = owner_session.execute(
        sa.text("SELECT * FROM listing_enquiry WHERE id = :e"), {"e": sent.id}
    ).one()
    assert row.owner_id == world.lens.owner_id
    assert row.batch_id == world.batch_id
    assert row.enquirer_account_id == caller
    assert (row.student_name, row.class_level, row.message) == (
        "Nadia Rahman",
        "ssc",
        "Wants Physics",
    )
    assert row.share_contact is False
    assert (row.status, row.outcome, row.closed_at) == ("open", None, None)
    assert row.created_at == late
    assert sent == sending.MyEnquiry(
        id=row.id,
        owner_public_name="Udoy Coaching",
        batch_title=world.batch_title,
        student_name="Nadia Rahman",
        class_level="ssc",
        message="Wants Physics",
        share_contact=False,
        status="open",
        outcome=None,
        sent_on=dt.date(2026, 11, 20),
        owner_contact_phone=None,
    )
    items = owner_session.execute(
        sa.text(
            "SELECT account_id, kind, batch_name, preview, source_id, enrollment_id "
            "FROM notification ORDER BY account_id"
        )
    ).all()
    assert [i.account_id for i in items] == world.manager_ids
    assert len(world.manager_ids) == 2
    for item in items:
        assert item.kind == HUB_ENQUIRY_RECEIVED == "hub_enquiry_received"
        assert item.batch_name == world.batch_title
        assert item.preview is None
        assert item.source_id == row.id
        assert item.enrollment_id is None


def test_send_without_a_batch_names_the_owner(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)

    sent = _send(restricted_session, guardian(owner_session), world.owner_slug)

    assert sent.batch_title is None
    assert sent.owner_public_name == "Rahim Sir"
    names = owner_session.execute(
        sa.text("SELECT batch_name FROM notification WHERE source_id = :e"),
        {"e": sent.id},
    ).scalars()
    assert list(names) == ["Rahim Sir"]


def test_concurrent_sends_make_one_open_enquiry(
    owner_session: Session, restricted_engine: Engine
) -> None:
    """Review Focus 3: two devices send the first request at once."""
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    factory = sessionmaker(bind=restricted_engine, expire_on_commit=False)
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def submit() -> None:
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                outcomes.append(_send(session, caller, world.owner_slug))
            except Exception as error:  # noqa: BLE001 -- asserted below
                outcomes.append(error)

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(outcomes) == 2
    sent = [o for o in outcomes if isinstance(o, sending.MyEnquiry)]
    refused = [o for o in outcomes if isinstance(o, TaxonomyError)]
    assert len(sent) == 1, outcomes
    assert len(refused) == 1, outcomes
    assert isinstance(refused[0], ConflictError)
    assert (refused[0].code, refused[0].message_key, refused[0].status) == (
        "ENQUIRY_ALREADY_OPEN",
        "hub.enquiry.already_open",
        409,
    )
    assert (
        _count(
            owner_session,
            "SELECT count(*) FROM listing_enquiry WHERE status = 'open' "
            "AND enquirer_account_id = :a",
            a=caller,
        )
        == 1
    )
    assert _spent(owner_session, caller) == 1
    assert (
        _count(owner_session, "SELECT count(*) FROM notification")
        == len(world.manager_ids)
        == 1
    )


def test_second_send_while_open_is_already_open(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    _send(restricted_session, caller, world.owner_slug)

    with pytest.raises(ConflictError) as refused:
        _send(restricted_session, caller, world.owner_slug, batch_id=world.batch_id)

    assert refused.value.code == "ENQUIRY_ALREADY_OPEN"
    assert _enquiries(owner_session) == 1
    assert _spent(owner_session, caller) == 1


def test_send_after_close_opens_a_new_one(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    first = _send(restricted_session, caller, world.owner_slug)
    close(owner_session, first.id, "not_now")

    second = _send(restricted_session, caller, world.owner_slug)

    assert second.id != first.id
    assert second.status == "open"
    assert _enquiries(owner_session) == 2
    assert _spent(owner_session, caller) == 2


def test_sixth_send_in_a_day_hits_ceiling(
    owner_session: Session, restricted_session: Session
) -> None:
    owners = [enquirable_owner(owner_session) for _ in range(6)]
    caller = guardian(owner_session)
    for world in owners[:5]:
        _send(restricted_session, caller, world.owner_slug)

    with pytest.raises(CeilingBreach) as refused:
        _send(restricted_session, caller, owners[5].owner_slug)

    assert HUB_ENQUIRY_ACCOUNT_DAILY == 5
    assert ScopeKind.HUB_ENQUIRY_DAILY.value == "hub_enquiry_day"
    assert (refused.value.code, refused.value.message_key, refused.value.status) == (
        "HUB_ENQUIRY_CEILING",
        "hub.enquiry.ceiling",
        409,
    )
    assert _enquiries(owner_session) == 5
    assert _spent(owner_session, caller) == HUB_ENQUIRY_ACCOUNT_DAILY
    assert _count(owner_session, "SELECT count(*) FROM notification") == 5

    tomorrow = _send(
        restricted_session, caller, owners[5].owner_slug, now=NOW + dt.timedelta(days=1)
    )
    assert tomorrow.status == "open"


def test_refused_send_consumes_nothing(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    shut = enquirable_owner(owner_session, accepts=False)
    caller = guardian(owner_session)
    _send(restricted_session, caller, world.owner_slug)

    for refused_send in (
        lambda: _send(restricted_session, caller, world.owner_slug),
        lambda: _send(restricted_session, caller, shut.owner_slug),
        lambda: _send(
            restricted_session, caller, shut.owner_slug, message="01712345678"
        ),
        lambda: _send(restricted_session, caller, "no-such-owner"),
    ):
        with pytest.raises(TaxonomyError):
            refused_send()

    assert _spent(owner_session, caller) == 1
    assert _enquiries(owner_session) == 1


def test_describe_names_target_and_contact_kind(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    by_phone = guardian(owner_session)
    by_email = guardian(owner_session, phone=None, email="mother@example.com")

    phone_view = sending.describe(
        restricted_session, by_phone, world.owner_slug, world.batch_id
    )
    email_view = sending.describe(restricted_session, by_email, world.owner_slug, None)

    assert phone_view == sending.EnquiryTarget(
        owner_public_name="Rahim Sir",
        batch_title=world.batch_title,
        contact_kind="phone",
        already_open=False,
    )
    assert email_view == sending.EnquiryTarget(
        owner_public_name="Rahim Sir",
        batch_title=None,
        contact_kind="email",
        already_open=False,
    )

    _send(restricted_session, by_phone, world.owner_slug)

    assert sending.describe(
        restricted_session, by_phone, world.owner_slug, None
    ).already_open
    assert not sending.describe(
        restricted_session, by_email, world.owner_slug, None
    ).already_open


def test_mine_lists_only_own_rows(
    owner_session: Session, restricted_session: Session
) -> None:
    """The guardian's own-row scoping: two guardians, two owners."""
    first_owner = enquirable_owner(owner_session)
    second_owner = enquirable_owner(owner_session, centre=True)
    mine_account = guardian(owner_session)
    theirs = guardian(owner_session, phone="01812345678")
    earlier = _send(restricted_session, mine_account, first_owner.owner_slug)
    later = _send(
        restricted_session,
        mine_account,
        second_owner.owner_slug,
        now=NOW + dt.timedelta(hours=1),
    )
    for world in (first_owner, second_owner):
        _send(
            restricted_session,
            theirs,
            world.owner_slug,
            student_name="Someone Else",
        )

    listed = sending.mine(restricted_session, mine_account)

    assert [e.id for e in listed] == [later.id, earlier.id]
    assert {e.student_name for e in listed} == {"Nadia Rahman"}
    assert (
        sending.mine(restricted_session, guardian(owner_session, phone="01912345678"))
        == []
    )
    names = {f.name for f in fields(sending.MyEnquiry)}
    assert not names & {"enquirer_account_id", "account_id", "owner_id"}


#: The most requests a guardian can hold while the daily purge runs: the
#: ceiling's daily count over every calendar day the purge's window can
#: touch. Computed here from the purge's own window, independently of
#: :data:`sending.MINE_LIMIT` [H5 final review M7].
RETENTION_BOUND: Final = HUB_ENQUIRY_ACCOUNT_DAILY * (
    WINDOWS["listing_enquiry"].keep_for.days + 2
)


def _seed_closed(
    owner_session: Session, owner_id: uuid.UUID, caller: uuid.UUID, count: int
) -> None:
    """Store ``count`` answered requests, a minute apart, ``Child 0`` oldest.

    :param owner_session: The table-owner session
    :param owner_id: The owner they were sent to
    :param caller: The guardian who sent them
    :param count: How many
    :return: None
    """
    owner_session.execute(
        sa.text(
            "INSERT INTO listing_enquiry (owner_id, enquirer_account_id, "
            "student_name, class_level, share_contact, status, outcome, "
            "created_at, closed_at) "
            "SELECT :o, :a, 'Child ' || n, 'class_8', false, 'closed', "
            "'not_now', :t + n * interval '1 minute', "
            ":t + n * interval '1 minute' "
            "FROM generate_series(0, :c - 1) AS n"
        ),
        {"o": owner_id, "a": caller, "t": NOW, "c": count},
    )
    owner_session.commit()


def test_mine_limit_is_the_retention_bound() -> None:
    # "You can withdraw a request at any time" needs every stored request
    # listed, so the cap is the most a guardian can hold, derived from the
    # ceiling and the purge's window rather than restated.
    assert sending.MINE_LIMIT == RETENTION_BOUND


def test_mine_lists_the_oldest_request_at_the_retention_bound(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    _seed_closed(owner_session, world.lens.owner_id, caller, RETENTION_BOUND)

    listed = sending.mine(restricted_session, caller)

    assert len(listed) == RETENTION_BOUND
    assert listed[0].student_name == f"Child {RETENTION_BOUND - 1}"
    assert listed[-1].student_name == "Child 0"


def test_mine_returns_the_newest_first_up_to_the_limit(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    _seed_closed(owner_session, world.lens.owner_id, caller, sending.MINE_LIMIT + 1)

    listed = sending.mine(restricted_session, caller)

    assert len(listed) == sending.MINE_LIMIT
    assert listed[0].student_name == f"Child {sending.MINE_LIMIT}"
    assert listed[-1].student_name == "Child 1"


def test_call_us_shows_published_number_and_hides_it_after_unpublish(
    owner_session: Session, restricted_session: Session
) -> None:
    world = enquirable_owner(owner_session)
    other = enquirable_owner(owner_session)
    for owner_id in (world.lens.owner_id, other.lens.owner_id):
        owner_session.execute(
            sa.text(
                "UPDATE owner_listing SET public_contact_phone = '+8801911223344' "
                "WHERE owner_id = :o"
            ),
            {"o": owner_id},
        )
    owner_session.commit()
    caller = guardian(owner_session)
    call_us = _send(restricted_session, caller, world.owner_slug)
    not_now = _send(restricted_session, caller, other.owner_slug)
    close(owner_session, call_us.id, "call_us")
    close(owner_session, not_now.id, "not_now")

    shown = {e.id: e for e in sending.mine(restricted_session, caller)}

    assert shown[call_us.id].outcome == "call_us"
    assert shown[call_us.id].owner_contact_phone == "+8801911223344"
    assert shown[not_now.id].owner_contact_phone is None

    owner_session.execute(
        sa.text("UPDATE owner_listing SET status = 'hidden' WHERE owner_id = :o"),
        {"o": world.lens.owner_id},
    )
    owner_session.commit()

    hidden = {e.id: e for e in sending.mine(restricted_session, caller)}
    assert hidden[call_us.id].owner_contact_phone is None
    assert hidden[call_us.id].owner_public_name == "Rahim Sir"


def test_mine_keeps_a_request_whose_listing_is_gone(
    owner_session: Session, restricted_session: Session
) -> None:
    """The guardian's list joins the listing LEFT, so it can always withdraw.

    ``mine`` is the only list a guardian withdraws from. A request whose
    owner listing no longer exists must still appear there, with no owner
    name, or it could not be withdrawn, and "withdrawal is total" would be
    false. An inner join would drop it silently.
    """
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)
    sent = _send(restricted_session, caller, world.owner_slug)
    owner_session.execute(
        sa.text("DELETE FROM owner_listing WHERE owner_id = :o"),
        {"o": world.lens.owner_id},
    )
    owner_session.commit()

    (listed,) = sending.mine(restricted_session, caller)

    assert listed.id == sent.id
    assert listed.owner_public_name is None
    assert listed.owner_contact_phone is None
    sending.withdraw(restricted_session, caller, sent.id)
    assert sending.mine(restricted_session, caller) == []


def test_inbox_kinds_are_new_and_not_legacy() -> None:
    from app.notifications.inbox import LEGACY_KINDS

    assert HUB_ENQUIRY_RECEIVED == "hub_enquiry_received"
    assert HUB_ENQUIRY_ANSWERED == "hub_enquiry_answered"
    assert not {HUB_ENQUIRY_RECEIVED, HUB_ENQUIRY_ANSWERED} & LEGACY_KINDS


NEW_KEYS = (
    "hub.enquiry.target_not_found",
    "hub.enquiry.already_open",
    "hub.enquiry.ceiling",
    "hub.enquiry.contains_contact",
    "hub.enquiry.not_found",
    "hub.enquiry.already_closed",
    "hub.enquiry.outcome_invalid",
)


@pytest.mark.parametrize("key", NEW_KEYS)
def test_message_key_published(key: str) -> None:
    resource = key.replace(".", "_")
    published = json.loads((ROOT / "message-keys.json").read_text())["keys"]
    assert key in published
    for bundle in ("values", "values-bn"):
        xml = (ROOT / "android/src/main/res" / bundle / "strings.xml").read_text()
        assert f'name="{resource}"' in xml
    kotlin = (
        ROOT
        / "android/src/main/kotlin/com/shikkhokplus/app/feature/auth/MessageKeys.kt"
    ).read_text()
    assert f'"{key}" to R.string.{resource}' in kotlin
    for language in ("en", "bn"):
        generated = json.loads(
            (ROOT / f"web/src/i18n/generated/strings.{language}.json").read_text()
        )
        assert resource in generated
    keys = json.loads((ROOT / "web/src/i18n/generated/message-keys.json").read_text())
    assert keys[key] == resource


def test_contact_refusal_copy_is_the_ruled_wording() -> None:
    """F10: a guardian has no public phone field; the copy says what to do.

    Reworded in T9 for the two share options and for an email-only
    account: the guardian chooses Share, and shares a contact, not
    necessarily a number.
    """
    xml = (ROOT / "android/src/main/res/values/strings.xml").read_text()
    assert (
        '<string name="hub_enquiry_contains_contact">Remove phone numbers and web '
        "addresses. To give the teacher your contact, choose Share.</string>"
    ) in xml


@pytest.mark.parametrize(
    ("name", "message", "field"),
    [
        pytest.param("   ", None, "student_name", id="blank-name"),
        pytest.param("N" * 81, None, "student_name", id="long-name"),
        pytest.param("Nadia", "m" * 301, "message", id="long-message"),
    ],
)
def test_lengths_out_of_range_are_refused(
    owner_session: Session,
    restricted_session: Session,
    name: str,
    message: str | None,
    field: str,
) -> None:
    """Call 10: 1 to 80 for the name and 1 to 300 for the message, stripped."""
    world = enquirable_owner(owner_session)
    caller = guardian(owner_session)

    with pytest.raises(ValidationError) as refused:
        _send(
            restricted_session,
            caller,
            world.owner_slug,
            student_name=name,
            message=message,
        )

    assert refused.value.code == "REQUEST_INVALID"
    assert refused.value.details == {"fields": field}
    assert _enquiries(owner_session) == 0
    assert _spent(owner_session, caller) == 0


def test_lengths_at_the_limits_are_stored_and_a_blank_message_is_none(
    owner_session: Session, restricted_session: Session
) -> None:
    first = enquirable_owner(owner_session)
    second = enquirable_owner(owner_session)
    caller = guardian(owner_session)

    longest = _send(
        restricted_session,
        caller,
        first.owner_slug,
        student_name=" " + "N" * 80 + " ",
        message="m" * 300,
    )
    blank = _send(restricted_session, caller, second.owner_slug, message="   ")

    assert (len(longest.student_name), len(longest.message or "")) == (80, 300)
    assert blank.message is None
