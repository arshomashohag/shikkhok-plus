"""Request and response bodies for signup, lookup and invitations.

Three disclosure obligations live in these schemas rather than in the
handlers that fill them, because a schema is what the privacy gate and
the committed contract can both read:

* **The lookup names neither a teacher nor a batch** [BR2.3]. There is
  no field for either, so there is nothing a later handler edit could
  accidentally populate. What the lookup *does* disclose -- that a seat
  exists -- is its purpose, and the bound here is on the WIDTH of the
  disclosure, not its existence.
* **An invitation carries exactly three fields** [BR1.4]: batch name,
  subject and fee amount. A response-schema obligation and not a
  filter, so the unaccepted read has nothing to leak. All three are
  teacher-authored, which is why it crosses no privacy boundary.
* **Signup's response says nothing about lenses** [BR1.1]. It reports
  that an account exists and that a code is on its way; what the
  account may do is resolved per request from the data, after the
  person verifies.

``address`` appears on the signup REQUEST and on no response. It is a
``Profile`` field and therefore owner-private [BR3.2, BR3.4], and the
schema-wide invariant would flag any teacher-lens response carrying it.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.money import MoneyField

__all__ = [
    "AlreadyAddedResponse",
    "DecisionResponse",
    "InvitationResponse",
    "SignupRequest",
    "SignupResponse",
]

#: The role a person may claim at signup. A CLAIM and never a stored
#: value [BR4.2]: ``teacher`` creates an ``Owner`` row and the three
#: have no other consequence. Spelled as a literal union rather than
#: reusing the service enum, so the wire vocabulary is fixed by the
#: contract and a later rename inside the service is a visible schema
#: diff rather than a silent one.
RoleName = Literal["teacher", "student", "guardian"]


class SignupRequest(BaseModel):
    """Create an account for a number nobody has registered.

    The number is **typed by the person** and never read from the SIM
    [TC-4, D-35]: there is no device-side source for this field, here
    or anywhere in this product.

    :ivar phone: The number this identity is keyed on
    :ivar role: The claimed role; nothing verifies it [BR4.2]
    :ivar self_name: The name the person chose for themselves. Lands on
        ``Profile.self_name`` and never on an ``Enrollment.display_name``
        [BR3.1]
    :ivar address: Owner-private, and optional because the
        already-added path reaches signup with no address yet
    """

    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=8, max_length=20)
    role: RoleName
    self_name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=500)


class SignupResponse(BaseModel):
    """The account exists and a code is on its way [BR4.3].

    **No token and no lens.** The account is created before the code is
    sent, and the person is authenticated by the existing OTP flow,
    unchanged [BR2.2]. Returning a token here would make signup a
    second authentication path with none of the seven controls the
    first one carries.

    :ivar account_id: The new account
    :ivar code_sent_to: The number the code was sent to, echoed so the
        screen can name its destination [BR4.3, AC1.11.4]
    """

    model_config = ConfigDict(extra="forbid")

    account_id: uuid.UUID
    code_sent_to: str


class AlreadyAddedResponse(BaseModel):
    """What the lookup may say about a number [BR2.3, BR4.5].

    **Three fields, and the absences are the requirement.** No teacher
    name, no teacher id, no batch name, no batch subject, no fee, no
    enrollment id. With any of those this becomes an oracle for who
    teaches whom, readable by anyone who can type a phone number
    [AC1.12.2].

    :ivar already_added: Whether a teacher recorded this number
    :ivar display_name: The teacher-typed name to pre-fill as
        correctable, or None
    :ivar role: The role to lock the form to, or None
    """

    model_config = ConfigDict(extra="forbid")

    already_added: bool
    display_name: str | None = None
    role: RoleName | None = None


class InvitationResponse(BaseModel):
    """One unaccepted seat, in exactly the width BR1.4 permits.

    Batch name, subject and fee amount -- all teacher-authored, so this
    read crosses no privacy boundary -- plus the seat's own id, which
    the accept and decline routes are keyed on, and this holder's own
    decision so the screen can offer the right action without deciding
    what ``declined`` means for itself [TC-9].

    **There is no attendance, no mark, no other enrollment and no
    further batch field**, and no write action but accept and decline
    on the link that names the holder [AC1.10.2].

    :ivar enrollment_id: The seat, which the decision routes are keyed on
    :ivar batch_name: The class being joined
    :ivar subject: The subjects taught, as the teacher named them
    :ivar fee_amount: This seat's fee, or None when it inherits the
        batch default. None is NOT zero: zero is a waiver
    :ivar decision: This holder's own decision, ``pending`` or
        ``declined``
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    batch_name: str
    subject: list[str]
    fee_amount: MoneyField | None = None
    decision: Literal["pending", "declined"]


class DecisionResponse(BaseModel):
    """The seat's state after this holder decided [BR5.2].

    Reports **this holder's own** decision. The other link's state is
    deliberately absent: it belongs to another person, and a seat whose
    student and guardian are different people shows each state only to
    its own holder. The teacher's roster is where both appear side by
    side, and that screen is D2's [AC1.10.7].

    :ivar enrollment_id: The seat decided on
    :ivar decision: This holder's decision after the write
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    decision: Literal["accepted", "declined"]
