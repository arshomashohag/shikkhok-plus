"""The health endpoint, and what it must not become.

**Unversioned, public, and deliberately thin.** It reports liveness,
database connectivity and the applied Alembic revision -- enough for the
post-deploy smoke set to be meaningful, and nothing more.

It is one of the ``PUBLIC_ROUTES``, reachable by anyone, so **every
field added here is information disclosed**. Version numbers, dependency
states and queue depths do not belong, and the response model forbids
extra fields so adding one is a deliberate edit to this file rather than
a dictionary key someone slipped in.
"""

from __future__ import annotations

from typing import Annotated, Literal

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.auth import get_session

__all__ = ["HealthResponse", "router"]

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """What the smoke set reads.

    :ivar status: ``ok`` when the process is serving
    :ivar database: ``ok`` or ``fail``
    :ivar migration_revision: The applied Alembic revision, or None
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    database: Literal["ok", "fail"]
    migration_revision: str | None


@router.get("/health", response_model=HealthResponse)
def health(session: Annotated[Session, Depends(get_session)]) -> HealthResponse:
    """Report liveness, database connectivity and schema revision.

    :param session: The request-scoped session
    :return: The health report
    """
    try:
        revision: str | None = session.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
        database: Literal["ok", "fail"] = "ok"
    except sa.exc.SQLAlchemyError:
        revision = None
        database = "fail"

    return HealthResponse(status="ok", database=database, migration_revision=revision)
