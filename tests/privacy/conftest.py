"""Order the meta-test first, and make it a gate rather than a sibling.

The plan says to order the meta-test first "so nothing downstream runs
without it". Alphabetical collection happens to do that today, which is
exactly the kind of guarantee that quietly stops holding when someone adds
``test_access_probes.py``.

So two mechanisms, because they fail differently:

* ``pytest_collection_modifyitems`` puts the meta-test first by name, not
  by filename.
* The session-scoped guard below re-checks the three conditions and
  **errors the whole package** if any has slipped. A probe suite that runs
  against a missing policy does not report a failure -- it reports a pass,
  which is the worst possible outcome and the reason this is belt and
  braces.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy import Engine

META_MODULE = "test_rls_meta"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run the RLS meta-test before every other privacy test.

    :param items: The collected items, reordered in place
    :return: None
    """
    meta = [item for item in items if META_MODULE in item.nodeid]
    rest = [item for item in items if META_MODULE not in item.nodeid]
    items[:] = meta + rest


@pytest.fixture(autouse=True)
def _privacy_suite_gate(request: pytest.FixtureRequest) -> None:
    """Refuse to run a privacy probe when the boundary is not in force.

    :param request: The pytest request, used to reach the engine fixture
    :return: None
    :raises pytest.FixtureLookupError: Never; failures raise directly
    """
    if META_MODULE in request.node.nodeid:
        return
    if "restricted_engine" not in request.fixturenames:
        return

    engine: Engine = request.getfixturevalue("restricted_engine")
    with engine.connect() as connection:
        superuser = connection.execute(
            sa.text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar_one()
        row_security = connection.execute(sa.text("SHOW row_security")).scalar_one()
        policies = [
            row[0]
            for row in connection.execute(
                sa.text(
                    "SELECT policyname FROM pg_policies WHERE tablename = 'profile'"
                )
            )
        ]

    if superuser:
        pytest.fail("privacy probe attempted as a SUPERUSER -- RLS is bypassed")
    if row_security != "on":
        pytest.fail("privacy probe attempted with row_security off")
    if not policies:
        pytest.fail("privacy probe attempted with no policy on profile")
