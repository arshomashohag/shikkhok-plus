"""A deliberately unlensed application, committed as a gate fixture.

**Why this file exists.** In B2 the route-enumeration gate iterates the real
application's routes, and that set is *empty* -- no feature Unit has been
built yet. The gate therefore returns green having examined nothing, and a
passing test and a vacuous test are the same colour. This fixture is the
only thing that proves the gate can fire at all.

**It builds its own application object** rather than registering a bad route
on the real one and removing it afterwards. That mutation leaks into any
test running in between, and the failure presents as an unrelated test
failing mysteriously.

**It is otherwise valid.** The route is a perfectly ordinary endpoint that
simply forgot its lens -- which is the realistic defect. A merely malformed
fixture would fail the gate for the wrong reason and certify nothing while
looking like a working test.
"""

from __future__ import annotations

from fastapi import FastAPI

#: The path the gate must name when it reports this fixture.
UNLENSED_PATH = "/v1/fixture/unlensed"


def build_unlensed_app() -> FastAPI:
    """Build an application with exactly one unlensed route.

    :return: An application the route gate must reject
    """
    app = FastAPI(title="unlensed fixture")

    @app.get(UNLENSED_PATH)
    def _forgot_the_lens() -> dict[str, str]:
        """Read something owner-scoped without resolving a lens.

        :return: An empty payload
        """
        return {}

    return app
