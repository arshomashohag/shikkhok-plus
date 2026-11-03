"""A teacher's payment methods, and the family's view of them [P1-P3].

**Every teacher query is scoped on ``PaymentMethod.owner_id``**, taken
from the lens and never from a parameter, so a caller cannot name
another owner's method. An id that is absent, retired or another
owner's is refused with the one shared ``NOT_AVAILABLE`` refusal.

**A method is retired, never deleted**, because past submissions keep a
copy of what they were paid to and the row stays resolvable.

**A family member reaches methods only through a seat they accepted**,
by way of the shared ``readable_enrollment`` check.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.accounts.phone import canonical_phone
from app.authz.lenses import GuardianLens, StudentLens, TeacherLens
from app.db.models import Batch, PaymentMethod
from app.errors import AuthorizationError, ValidationError
from app.errors.codes import NOT_AVAILABLE
from app.fees.claims import MOBILE_SERVICES
from app.teaching.roster import readable_enrollment

__all__ = [
    "FamilyMethods",
    "MethodDraft",
    "create_method",
    "list_methods",
    "methods_for_seat",
    "retire_method",
    "update_method",
]

_PROVIDER_MAX = 32
_ACCOUNT_NUMBER_MAX = 64
_NAME_MAX = 128
_NOTE_MAX = 200
_BANK_FIELDS = ("provider", "account_number", "account_name", "branch_name")


def _refuse() -> AuthorizationError:
    """Build the shared refusal for an absent or unowned method.

    :return: The refusal
    """
    return AuthorizationError(code=NOT_AVAILABLE, message_key="fees.not_available")


def _incomplete() -> ValidationError:
    """Build the refusal for a method missing or mixing its fields.

    :return: The refusal
    """
    return ValidationError(
        code="METHOD_FIELDS_INCOMPLETE",
        message_key="fees.method.fields_incomplete",
    )


#: The free-text fields of a draft, trimmed before any check.
_TEXT_FIELDS = (
    "provider",
    "mobile_number",
    "account_number",
    "account_name",
    "branch_name",
    "note",
)


@dataclass(frozen=True, slots=True)
class MethodDraft:
    """What a teacher typed for a method, before it is checked.

    **Text is trimmed on construction**, and a field left with nothing in
    it is treated as absent. A bank account name of three spaces would
    otherwise pass "present" and show the family a blank line.

    :ivar kind: ``mobile`` or ``bank``
    :ivar provider: The mobile service or the bank's name
    :ivar mobile_number: The number, mobile methods only
    :ivar account_number: The bank account number, bank methods only
    :ivar account_name: The account holder, bank methods only
    :ivar branch_name: The branch, bank methods only
    :ivar note: Optional text shown with the method
    """

    kind: str
    provider: str | None = None
    mobile_number: str | None = None
    account_number: str | None = None
    account_name: str | None = None
    branch_name: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        """Trim every text field, turning one left empty into None.

        :return: None
        """
        for name in _TEXT_FIELDS:
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, value.strip() or None)

    def validate(self) -> None:
        """Check the draft against its kind's required and forbidden fields.

        :raises ValidationError: A required field is absent, a field of
            the other kind is present, a length bound is exceeded, or a
            mobile number is not a Bangladeshi mobile
        """
        if self.kind == "mobile":
            self._validate_mobile()
        elif self.kind == "bank":
            self._validate_bank()
        else:
            raise _incomplete()
        self._validate_lengths()

    def stored_mobile_number(self) -> str | None:
        """Return the mobile number in its stored ``01XXXXXXXXX`` form.

        :return: The local form, or None for a bank draft
        :raises ValidationError: The number is not a Bangladeshi mobile
        """
        if self.mobile_number is None:
            return None
        return "0" + canonical_phone(self.mobile_number)[4:]

    def _validate_mobile(self) -> None:
        """Check a mobile draft.

        :raises ValidationError: See :meth:`validate`
        """
        if not self.provider or not self.mobile_number:
            raise _incomplete()
        if (
            self.account_number is not None
            or self.account_name is not None
            or self.branch_name is not None
        ):
            raise _incomplete()
        self.stored_mobile_number()

    def _validate_bank(self) -> None:
        """Check a bank draft.

        :raises ValidationError: See :meth:`validate`
        """
        if any(not getattr(self, name) for name in _BANK_FIELDS):
            raise _incomplete()
        if self.mobile_number is not None:
            raise _incomplete()

    def _validate_lengths(self) -> None:
        """Check each text field against its column bound.

        :raises ValidationError: A field is too long
        """
        bounds = (
            (self.provider, _PROVIDER_MAX),
            (self.account_number, _ACCOUNT_NUMBER_MAX),
            (self.account_name, _NAME_MAX),
            (self.branch_name, _NAME_MAX),
            (self.note, _NOTE_MAX),
        )
        for value, limit in bounds:
            if value is not None and len(value) > limit:
                raise ValidationError(
                    code="METHOD_FIELD_TOO_LONG",
                    message_key="fees.method.field_too_long",
                )


@dataclass(frozen=True, slots=True)
class FamilyMethods:
    """The methods a family may pay to, with the server's suggestions.

    :ivar methods: The owner's live methods, in display order
    :ivar services: The mobile service names the form suggests
    :ivar teacher_display_name: Who the money goes to, or None
    :ivar cash_allowed: Whether cash in hand is offered
    """

    methods: list[PaymentMethod]
    services: tuple[str, ...] = MOBILE_SERVICES
    teacher_display_name: str | None = None
    cash_allowed: bool = field(default=True)


def list_methods(session: Session, *, lens: TeacherLens) -> list[PaymentMethod]:
    """List this owner's live methods in display order.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :return: The methods, not retired, by position
    """
    return _live_for_owner(session, lens.owner_id)


def _live_for_owner(session: Session, owner_id: uuid.UUID) -> list[PaymentMethod]:
    """Read an owner's live methods in display order.

    :param session: The session to read through
    :param owner_id: The owner
    :return: The methods, not retired, by position
    """
    return list(
        session.scalars(
            sa.select(PaymentMethod)
            .where(
                PaymentMethod.owner_id == owner_id,
                PaymentMethod.retired_at.is_(None),
            )
            .order_by(PaymentMethod.position, PaymentMethod.created_at)
        )
    )


def create_method(
    session: Session, *, lens: TeacherLens, draft: MethodDraft
) -> PaymentMethod:
    """Add a method at the end of this owner's list.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param draft: What the teacher typed
    :return: The new method
    :raises ValidationError: The draft is incomplete or malformed
    """
    draft.validate()
    highest = session.scalar(
        sa.select(sa.func.max(PaymentMethod.position)).where(
            PaymentMethod.owner_id == lens.owner_id
        )
    )
    now = dt.datetime.now(tz=dt.UTC)
    method = PaymentMethod(
        owner_id=lens.owner_id,
        position=(highest if highest is not None else 0) + 1,
        created_at=now,
        updated_at=now,
    )
    _apply(method, draft)
    session.add(method)
    session.commit()
    return method


def update_method(
    session: Session,
    *,
    lens: TeacherLens,
    method_id: uuid.UUID,
    draft: MethodDraft,
) -> PaymentMethod:
    """Replace a live method's details.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param method_id: The method
    :param draft: The new details
    :return: The updated method
    :raises AuthorizationError: Absent, retired or another owner's
    :raises ValidationError: The draft is incomplete or malformed
    """
    method = _owned_live(session, lens=lens, method_id=method_id)
    draft.validate()
    _apply(method, draft)
    method.updated_at = dt.datetime.now(tz=dt.UTC)
    session.commit()
    return method


def retire_method(session: Session, *, lens: TeacherLens, method_id: uuid.UUID) -> None:
    """Hide a method while keeping the row.

    :param session: The session to write through
    :param lens: The teacher lens carrying the owner id
    :param method_id: The method
    :raises AuthorizationError: Absent, already retired or another
        owner's
    """
    method = _owned_live(session, lens=lens, method_id=method_id)
    now = dt.datetime.now(tz=dt.UTC)
    method.retired_at = now
    method.updated_at = now
    session.commit()


def methods_for_seat(
    session: Session,
    *,
    lens: StudentLens | GuardianLens,
    enrollment_id: uuid.UUID,
) -> FamilyMethods:
    """List the methods the teacher of an accepted seat accepts.

    :param session: The session to read through
    :param lens: The student or guardian lens
    :param enrollment_id: The seat
    :return: The teacher's live methods and the suggestions
    :raises AuthorizationError: The lens has not accepted that seat
    """
    seat = readable_enrollment(session, lens=lens, enrollment_id=enrollment_id)
    batch = session.get(Batch, seat.batch_id)
    if batch is None:
        raise _refuse()
    return FamilyMethods(
        methods=_live_for_owner(session, batch.owner_id),
        teacher_display_name=batch.teacher_display_name,
    )


def _owned_live(
    session: Session, *, lens: TeacherLens, method_id: uuid.UUID
) -> PaymentMethod:
    """Load a live method this owner holds, or refuse indistinguishably.

    :param session: The session to read through
    :param lens: The teacher lens carrying the owner id
    :param method_id: The method
    :return: The method
    :raises AuthorizationError: Absent, retired or another owner's
    """
    method = session.scalars(
        sa.select(PaymentMethod).where(
            PaymentMethod.id == method_id,
            PaymentMethod.owner_id == lens.owner_id,
            PaymentMethod.retired_at.is_(None),
        )
    ).one_or_none()
    if method is None:
        raise _refuse()
    return method


def _apply(method: PaymentMethod, draft: MethodDraft) -> None:
    """Copy a validated draft onto a method, clearing the other kind.

    :param method: The row to fill
    :param draft: A draft that has passed validation
    """
    method.kind = draft.kind
    method.provider = draft.provider
    method.mobile_number = draft.stored_mobile_number()
    method.account_number = draft.account_number
    method.account_name = draft.account_name
    method.branch_name = draft.branch_name
    method.note = draft.note
