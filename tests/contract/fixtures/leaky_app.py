"""A teacher-facing application that leaks both forbidden field sets.

**Why this file exists.** In B2 the privacy gate iterates the real
application's routes, and that set is empty. The gate returns green having
examined nothing, and a passing test and a vacuous test are the same
colour. This fixture is the only thing proving the gate can fire.

**It leaks two fields, deliberately, in two separate response models.** The
gate carries two forbidden sets on one iteration [BR2.4]: owner-private
profile fields, and account identifiers per ADR-001. A fixture tripping
only the first would leave ADR-001's half entirely unexercised while the
gate still reported green -- which is the specific gap the two-error
assertion closes.

**Both models are otherwise valid.** Each is an ordinary teacher-facing
response that simply carries one field it must not. A merely malformed
fixture would fail the gate for the wrong reason and certify nothing.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app.authz.lenses import TeacherLens

#: The owner-private field this fixture leaks, and the route carrying it.
PROFILE_LEAK_FIELD = "self_name"
PROFILE_LEAK_PATH = "/v1/fixture/roster"

#: The account identifier this fixture leaks, and the route carrying it.
ACCOUNT_ID_LEAK_FIELD = "student_account_id"
ACCOUNT_ID_LEAK_PATH = "/v1/fixture/attendance"


class LeakyRoster(BaseModel):
    """A roster carrying an owner-private profile field.

    :ivar enrollment_id: Scoped to one owner, which is correct
    :ivar self_name: Written by the student; no teacher may see it
    """

    enrollment_id: UUID
    self_name: str


class LeakyAttendance(BaseModel):
    """An attendance row carrying a global account key.

    :ivar enrollment_id: Scoped to one owner, which is correct
    :ivar student_account_id: A global handle, forbidden by ADR-001
    """

    enrollment_id: UUID
    student_account_id: UUID


def _teacher_lens() -> TeacherLens:
    """Stand in for U3's teacher-lens resolver.

    :return: A teacher lens
    """
    return TeacherLens(account_id=UUID(int=1), owner_id=UUID(int=2))


def build_leaky_app() -> FastAPI:
    """Build an application whose schema violates both forbidden sets.

    :return: An application the privacy gate must reject twice
    """
    app = FastAPI(title="leaky fixture")

    @app.get(
        PROFILE_LEAK_PATH,
        response_model=LeakyRoster,
        dependencies=[Depends(_teacher_lens)],
    )
    def _roster() -> dict[str, str]:
        """Return a roster that leaks the student's own profile name.

        :return: An empty payload
        """
        return {}

    @app.get(
        ACCOUNT_ID_LEAK_PATH,
        response_model=LeakyAttendance,
        dependencies=[Depends(_teacher_lens)],
    )
    def _attendance() -> dict[str, str]:
        """Return attendance that leaks a global account key.

        :return: An empty payload
        """
        return {}

    return app
