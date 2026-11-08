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

The address parts appear on the signup REQUEST and on no response. They
are ``Profile`` fields and therefore owner-private [BR3.2, BR3.4], and
the schema-wide invariant would flag any teacher-lens response carrying
them.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.address import CityField, HouseField, PostcodeField, RoadField
from app.schemas.identifier import IdentifierFields
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

#: What sign-up accepts: the three roles, and ``coaching`` [0022], which
#: creates a centre and makes the person its first manager. Kept apart
#: from :data:`RoleName` because the lookup never locks a form to it.
SignupRoleName = Literal["teacher", "student", "guardian", "coaching"]


class SignupRequest(IdentifierFields):
    """Create an account for a number or an address nobody has registered.

    The number is **typed by the person** and never read from the SIM
    [TC-4, D-35]: there is no device-side source for this field, here
    or anywhere in this product.

    :ivar phone: The number this identity is keyed on, or None
    :ivar email: Or the address [0032]; exactly one of the two. No
        password here: it is chosen after the code is verified, with the
        token that verification yields, so the person who proved the
        destination is the one who sets it
    :ivar role: The claimed role; nothing verifies it [BR4.2]
    :ivar self_name: The name the person chose for themselves. Lands on
        ``Profile.self_name`` and never on an ``Enrollment.display_name``
        [BR3.1]
    :ivar address_house: House or flat. **Required**, on every path,
        including a number a teacher already added (decided 2026-11-05)
    :ivar address_road: Road or area, required
    :ivar address_city: City or district, required
    :ivar address_postcode: Four digits, required
    :ivar centre_name: The centre's name. Required for ``coaching`` and
        refused for every other role
    """

    model_config = ConfigDict(extra="forbid")

    role: SignupRoleName
    self_name: str = Field(min_length=1, max_length=120)
    address_house: HouseField
    address_road: RoadField
    address_city: CityField
    address_postcode: PostcodeField
    centre_name: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def _centre_name_matches_role(self) -> SignupRequest:
        """Require a centre name for ``coaching`` and refuse it otherwise.

        :return: The request
        :raises ValueError: The name is missing or blank for a centre, or
            sent for any other role
        """
        named = self.centre_name is not None and self.centre_name.strip() != ""
        if (self.role == "coaching") != named:
            raise ValueError("centre_name is required for coaching and only for it")
        return self


class SignupResponse(BaseModel):
    """The account exists and a code is on its way [BR4.3].

    **No token and no lens.** The account is created before the code is
    sent, and the person is authenticated by the existing OTP flow,
    unchanged [BR2.2]. Returning a token here would make signup a
    second authentication path with none of the seven controls the
    first one carries.

    :ivar account_id: The new account
    :ivar code_sent_to: The number or address the code was sent to, echoed so the
        screen can name its destination [BR4.3, AC1.11.4]
    """

    model_config = ConfigDict(extra="forbid")

    account_id: uuid.UUID
    code_sent_to: str


class AlreadyAddedResponse(BaseModel):
    """What the lookup may say about a number [BR2.3, BR4.5].

    **The absences are the requirement.** No teacher name, no teacher
    id, no batch name, no batch subject, no fee, no enrollment id, and
    no name for the person [C-06]. With any of those this becomes an
    oracle readable by anyone who can type a phone number [AC1.12.2].

    :ivar already_added: Whether a teacher recorded this number
    :ivar display_name: **Deprecated, and never a name.** Kept so
        clients already installed still parse the response: an empty
        string when ``already_added`` is true, None otherwise. A
        guardian reads the child's name after sign-in, from
        ``InvitationResponse.child_name``
    :ivar role: The role to lock the form to, or None
    """

    model_config = ConfigDict(extra="forbid")

    already_added: bool
    display_name: str | None = Field(
        default=None,
        deprecated=True,
        max_length=0,
        description=(
            "Deprecated and never a name: an empty string when "
            "already_added is true, null otherwise. Kept only so clients "
            "already installed still parse the response."
        ),
    )
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
    :ivar role: Which link this account holds on the seat. Present
        because the DECLINE CONFIRMATION differs by role [BR5.2]: a
        student's decline stops their fee, a guardian's leaves the
        student's obligation entirely intact. The client had no
        trustworthy way to tell them apart, and one confirmation shown
        to both told a guardian a debt was cancelled when it was not.

        This discloses nothing new -- the holder is on this seat -- and
        it is decided server-side rather than inferred from a lens hint
        the client supplied [TC-11, D-2]
    :ivar child_name: For a guardian, the child this seat is for, as the
        teacher typed the name, so the guardian can answer "is this my
        child?" (decided by the owner 2026-11-05). None for a student.
        Teacher-authored, never the child's own profile name
    :ivar also_covers: The other batches of the same teacher this
        decision also answers, by name [D1, 0018]. Acceptance is per
        student, so a student in three classes is asked once; the
        person is shown every class they are agreeing to, which keeps
        the invitation at "what you are being asked to join"
    """

    model_config = ConfigDict(extra="forbid")

    enrollment_id: uuid.UUID
    batch_name: str
    subject: list[str]
    fee_amount: MoneyField | None = None
    decision: Literal["pending", "declined"]
    role: Literal["student", "guardian"]
    child_name: str | None = None
    also_covers: list[str] = Field(default_factory=list)


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
