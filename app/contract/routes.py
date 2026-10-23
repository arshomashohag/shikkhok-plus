"""The route-enumeration gate: every route resolves a lens.

The failure mode is not a *wrong* lens -- it is a **forgotten** one. A
dependency nobody added produces an endpoint that works perfectly and
authorizes nothing, and review cannot reliably catch an absence, so this
must fail in CI.

``unlensed_routes`` takes the application as an argument rather than
reaching for a module-level one. That is what lets the committed violation
fixture and the real gate call **one function**: without it the fixture
exercises a parallel implementation that can drift silently, so the fixture
keeps passing while the real gate is broken -- precisely the false
confidence the fixtures exist to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from app.authz.annotations import resolve_lens_type

__all__ = [
    "LENS_EXEMPT_AUTHENTICATED",
    "PUBLIC_ROUTES",
    "RouteViolation",
    "unlensed_routes",
]

#: Routes reachable with no authentication at all. **Exactly eight**, and
#: the count IS asserted: a ninth entry is a diff against a stated number
#: rather than a line appended to a growing list.
#:
#: The number read "five" over a six-entry set until 2026-10-22 — the two
#: deletion routes were added without it, so the stated count and the
#: asserted count had diverged and nothing noticed, because nothing asserted
#: the count at all. Corrected along with the assertion that now makes the
#: claim real [practices 2026-10-22: a comment may not state a number that
#: nothing checks]. D1 adds two and moves the number with them.
#:
#: **D1's two are the product's first unauthenticated WRITE and its first
#: deliberate disclosure** [BR2.1, BR2.3]. `POST /v1/accounts` must be
#: public because there is no session to authenticate with before an
#: account exists, and the already-added lookup must be public because it
#: is called while the signup form renders. Both are bounded by signup's
#: OWN ceilings, counted separately from the OTP path's, and neither
#: reaches a batch, a fee, a mark or an attendance record
#: [logical-components § 4].
#:
#: **Two of these have no handler yet.** `/account-deletion`, GET and POST,
#: is pre-declared D6 scope: both account-deletion paths are release-blocking
#: V1 deliverables [TC-19, RC-4, RC-5] and neither exists. Allowlisting them
#: ahead of the handlers is deliberate and is not a hole — an allowlist entry
#: grants nothing on its own, since the route-enumeration gate walks
#: REGISTERED routes and an unregistered path is unreachable. What it buys is
#: that D6 lands handlers against entries already under review, rather than
#: editing the public-route allowlist in the same commit that adds a public
#: route.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/v1/auth/otp"),
        ("POST", "/v1/auth/verify"),
        ("POST", "/v1/accounts"),
        ("GET", "/v1/accounts/already-added"),
        ("GET", "/health"),
        ("GET", "/account-deletion"),
        ("POST", "/account-deletion"),
        # Staging only, and absent entirely in production -- the router
        # is not registered unless the environment permits it. It is
        # public because it must work before anyone can authenticate,
        # which is its whole purpose.
        ("GET", "/staging/last-otp"),
    }
)

#: Authenticated routes that resolve no lens. Deliberately a SEPARATE set:
#: with one combined allowlist, whoever first hits a failing refresh route
#: takes the cheapest green edit and adds it to PUBLIC_ROUTES, after which
#: nothing records that the route must stay authenticated.
LENS_EXEMPT_AUTHENTICATED: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/v1/auth/refresh"),
        # The route that REPORTS the lenses, so it cannot require one:
        # an account would have to already know what it was in order to
        # ask what it is. Every value it returns is derived from the
        # authenticated account id and it reads nothing another account
        # could own, which is what makes the exemption safe rather than
        # merely necessary.
        ("GET", "/v1/me"),
        # The route that REPORTS which invitation lenses exist, exempt
        # on exactly GET /v1/me's reasoning: requiring one would mean a
        # person had to already know which seats they were offered in
        # order to ask. Every row it returns is resolved from the
        # authenticated account id by `available_invitations`, and the
        # four per-seat routes beneath it DO each resolve an
        # InvitationLens -- so the exemption covers the listing alone
        # and not anything it links to.
        ("GET", "/v1/invitations"),
    }
)


@dataclass(frozen=True, slots=True)
class RouteViolation:
    """A route that resolves no lens and is not allowlisted.

    :ivar method: The HTTP method
    :ivar path: The route path, as declared
    """

    method: str
    path: str


def _resolves_a_lens(dependant: Dependant) -> bool:
    """Report whether this dependency tree yields a lens.

    Walks sub-dependencies recursively, because a lens is routinely nested
    inside a composed dependency rather than named directly on the handler.

    :param dependant: The dependency node to inspect
    :return: True if any dependency in the tree returns a lens type
    :raises AnnotationResolutionError: An annotation cannot be resolved
    """
    if dependant.call is not None and resolve_lens_type(dependant.call):
        return True
    return any(_resolves_a_lens(sub) for sub in dependant.dependencies)


def _api_routes(app: FastAPI) -> list[APIRoute]:
    """Collect every real endpoint, however the app stores them.

    **``app.routes`` does not always hold ``APIRoute`` objects.** In this
    FastAPI version an included router appears as an opaque
    ``_IncludedRouter`` wrapper, so ``isinstance(route, APIRoute)`` over
    ``app.routes`` matched NOTHING -- and this gate, the one control
    guaranteeing no endpoint ships unlensed, passed against zero routes
    for as long as that was true.

    Enumerating the routers directly is version-independent: a router
    holds its own ``APIRoute`` objects whatever the application does with
    it afterwards. The count is cross-checked against the generated
    OpenAPI document by a test, so a future version that hides routes
    from here too fails loudly instead of silently narrowing.

    :param app: The application to enumerate
    :return: Every APIRoute reachable from the app or its routers
    """
    seen: dict[int, APIRoute] = {}

    def collect(routes: object) -> None:
        if not isinstance(routes, list):
            return
        for route in routes:
            if isinstance(route, APIRoute):
                seen[id(route)] = route
            nested = getattr(route, "routes", None)
            if nested is not None:
                collect(nested)

    collect(list(app.routes))

    # Every router the application included, recorded by main.py at
    # include time. NOT a hardcoded import list, which was the first
    # fix and was itself the vacuous-enumeration defect in a new form:
    # a router added by a later Unit -- or registered conditionally,
    # like the staging outbox -- would be invisible to both gates while
    # they reported clean.
    #
    # main.py appends to app.state.included_routers as it includes, so
    # the gate sees exactly what was registered rather than what
    # somebody remembered to list here.
    for router in getattr(app.state, "included_routers", []):
        collect(list(router.routes))

    return list(seen.values())


def unlensed_routes(app: FastAPI) -> list[RouteViolation]:
    """List every route that resolves no lens and is not allowlisted.

    :param app: The application to enumerate
    :return: One entry per violating route, empty when the app is clean
    :raises AnnotationResolutionError: An annotation cannot be resolved;
        the message names the offending route so the build fails loudly
        rather than passing universally
    """
    violations: list[RouteViolation] = []

    for route in _api_routes(app):
        for method in sorted(route.methods or set()):
            key = (method, route.path)
            if key in PUBLIC_ROUTES or key in LENS_EXEMPT_AUTHENTICATED:
                continue
            try:
                lensed = _resolves_a_lens(route.dependant)
            except Exception as error:
                raise type(error)(f"{method} {route.path}: {error}") from error
            if not lensed:
                violations.append(RouteViolation(method=method, path=route.path))

    return violations
