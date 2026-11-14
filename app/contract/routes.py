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
    "CLASS_TEACHER_ROUTES",
    "LENS_EXEMPT_AUTHENTICATED",
    "PLATFORM_ADMIN_ROUTES",
    "PUBLIC_ROUTES",
    "RouteViolation",
    "class_teacher_routes",
    "platform_admin_routes",
    "unlensed_routes",
]

#: Routes reachable with no authentication at all. **Exactly fourteen**,
#: and the count IS asserted: a fifteenth entry is a diff against a
#: stated number rather than a line appended to a growing list. The three
#: admin sign-in routes moved it from eight, the app sign-in's second
#: step to twelve [0028], and password sign-in and password setup to
#: fourteen [0032].
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
#: **The two `/account-deletion` entries now have handlers, and D6 added
#: no entry here.** They were allowlisted ahead of the handlers as
#: pre-declared D6 scope — deliberate and not a hole, since an allowlist
#: entry grants nothing on its own: the route-enumeration gate walks
#: REGISTERED routes and an unregistered path is unreachable. What it bought
#: is exactly what happened: D6 landed handlers against entries already under
#: review, rather than editing the public-route allowlist in the same commit
#: that added a public route.
#:
#: It also shaped the implementation rather than merely recording it. The
#: external path needs two steps — send a code, then spend it — and a
#: separate `/account-deletion/code` would have been a ninth entry here. So
#: `POST /account-deletion` carries both steps, selected by whether the body
#: names a code, and the count stays at eight [BR3.2].
#:
#: **D6's in-app route is NOT here.** `DELETE /v1/me` is authenticated and
#: goes in `LENS_EXEMPT_AUTHENTICATED` below, which is the whole reason that
#: set is separate.
PUBLIC_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/v1/auth/otp"),
        ("POST", "/v1/auth/verify"),
        ("POST", "/v1/accounts"),
        ("GET", "/v1/accounts/already-added"),
        ("GET", "/health"),
        ("GET", "/account-deletion"),
        ("POST", "/account-deletion"),
        # Platform administrator sign-in [0028]. Unauthenticated because
        # a person signing in has nothing to authenticate with yet, but
        # NOT reachable by anyone: every one of them depends on
        # `admin_gate`, which refuses a request that did not come
        # through the admin hostname's distribution (its secret header)
        # from an allowed network. The SMS step texts only allowlisted
        # numbers and answers every number identically; the code it
        # sends reaches only the authenticator step, which grants
        # nothing until a second factor is typed.
        ("POST", "/v1/admin/auth/otp"),
        ("POST", "/v1/admin/auth/verify"),
        ("POST", "/v1/admin/auth/mfa"),
        # The app sign-in's second step [0028], public on `/verify`'s
        # reasoning: the person has no token yet. It is bounded by its
        # challenge, which only a verified SMS code yields, and by the
        # shared factor's lock after five wrong codes.
        ("POST", "/v1/auth/mfa"),
        # Passwords [0032], public on `/verify`'s reasoning: the person
        # has no token yet. Sign-in is bounded per phone number or
        # address and per network, answers every failure identically,
        # and leads only to the existing authenticator step for an
        # account that has one. Setup is bounded by its token, which only
        # a verified code yields and which the password it sets spends.
        ("POST", "/v1/auth/password"),
        ("POST", "/v1/auth/password/setup"),
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
        # Logout presents the refresh token, exactly as refresh does and
        # for the same reason [C-21]: a client whose access token has
        # expired must still be able to end its session. Here and not in
        # PUBLIC_ROUTES on refresh's reasoning -- a refresh token IS a
        # credential, and this set keeps that recorded.
        ("POST", "/v1/auth/logout"),
        # Sign out everywhere, on DELETE /v1/me's reasoning: it acts on
        # the authenticated account itself, takes no id from the
        # request, and an account holding no lens must still be able to
        # end its own sessions [C-21].
        ("POST", "/v1/auth/logout-all"),
        # The route that REPORTS the lenses, so it cannot require one:
        # an account would have to already know what it was in order to
        # ask what it is. Every value it returns is derived from the
        # authenticated account id and it reads nothing another account
        # could own, which is what makes the exemption safe rather than
        # merely necessary.
        ("GET", "/v1/me"),
        # The WRITE half of the same row, added 2026-10-27, exempt on
        # exactly GET /v1/me's reasoning and no wider. It reads and
        # writes only `profile` for the authenticated account id,
        # which no lens would narrow further: a lens says which OTHER
        # people's data you may reach, and this reaches none.
        #
        # What actually bounds it is row-level security. The app
        # connects as the restricted role and the policy on `profile`
        # admits only the owner's row, so a write aimed at another
        # account fails at the database rather than relying on the
        # handler [TC-13, D-7].
        ("PATCH", "/v1/me"),
        # The route that REPORTS which invitation lenses exist, exempt
        # on exactly GET /v1/me's reasoning: requiring one would mean a
        # person had to already know which seats they were offered in
        # order to ask. Every row it returns is resolved from the
        # authenticated account id by `available_invitations`, and the
        # four per-seat routes beneath it DO each resolve an
        # InvitationLens -- so the exemption covers the listing alone
        # and not anything it links to.
        ("GET", "/v1/invitations"),
        # D6's in-app deletion path. The FOURTH exemption, and the
        # count's fourth firing: each previous one forced the entry to
        # be justified rather than appended, and this is the reason for
        # this one.
        #
        # It acts on the authenticated account ITSELF, so there is no
        # other account's data to scope and a lens would carry nothing
        # the handler could use. Requiring one would be worse than
        # redundant: an account holding none of the three lenses -- a
        # person who signed up, was never enrolled and owns no batch --
        # could not delete itself at all, and that is precisely the
        # account with the least reason to stay.
        #
        # Authenticated and NOT public, which is the whole point of
        # this set being separate: the external, unauthenticated path
        # is the `/account-deletion` pair, and it proves ownership with
        # a verified code instead.
        ("DELETE", "/v1/me"),
        # The reader's own inbox, added 2026-10-28, exempt on exactly
        # GET /v1/me's reasoning. Both read and write only rows WHERE
        # account_id is the authenticated account, and take no id from
        # the request. A lens would scope nothing, and requiring one
        # would hide a fee reminder from a guardian whose seat is
        # precisely what the reminder is about.
        ("GET", "/v1/me/notifications"),
        ("POST", "/v1/me/notifications/read"),
        # The per-item pair, added 2026-10-31, exempt on the same
        # reasoning and no wider. The id is checked against the caller
        # in SQL (`owned_item`, `mark_one_read`), so another account's id
        # is refused exactly as a missing one is and reaches none of
        # that account's data. The detail's content is gated by the
        # caller's own lens onto the seat, resolved inside the call.
        ("GET", "/v1/me/notifications/{notification_id}"),
        ("POST", "/v1/me/notifications/{notification_id}/read"),
        # What stays if the caller deletes their account, added
        # 2026-10-28 on DELETE /v1/me's reasoning: it reads only what the
        # authenticated account itself owns, and an account owning
        # nothing must get zeros rather than a lens refusal.
        ("GET", "/v1/me/deletion-summary"),
        # Opening a coaching centre, added 2026-11-06 on DELETE /v1/me's
        # reasoning: it acts on the authenticated account itself, which
        # becomes the new centre's first manager, and an account holding
        # no lens must still be able to open one. It reads no other
        # account's data and takes no id from the request.
        ("POST", "/v1/centres"),
        # The centre offers this account holds, exempt on exactly GET
        # /v1/invitations's reasoning: it REPORTS which membership lenses
        # exist, and the two per-offer routes beneath it each resolve a
        # MembershipLens.
        ("GET", "/v1/memberships"),
        # A centre teacher's own classes [C4], exempt on GET
        # /v1/invitations's reasoning: it REPORTS which classes the
        # account's memberships are assigned, derived in the query from
        # the authenticated account id, and the three per-class routes
        # beneath it each resolve a ClassTeacherLens for one class.
        ("GET", "/v1/me/classes"),
        # The exams a centre member marks [C4], on the same reasoning;
        # the per-exam routes beneath it each resolve an ExaminerLens.
        ("GET", "/v1/me/exams"),
        # My pay [P1, D15], on the same reasoning: it reports only the
        # salary lines paying the authenticated account, through its own
        # live memberships, in the query that reads them.
        ("GET", "/v1/me/pay"),
        # The help centre [0027], exempt on the inbox's reasoning above
        # and no wider. All four act on the authenticated account's own
        # tickets, each statement scoped by that account id in SQL, so a
        # ticket id belonging to someone else answers the same 404 as
        # one that does not exist. Requiring a lens would lock out the
        # account holding none -- signed up, never enrolled, owning no
        # batch -- which is the person most likely to need help.
        ("GET", "/v1/me/help/tickets"),
        ("POST", "/v1/me/help/tickets"),
        ("GET", "/v1/me/help/tickets/{ticket_id}"),
        ("POST", "/v1/me/help/tickets/{ticket_id}/messages"),
        # Two-step verification settings [0028], exempt on GET /v1/me's
        # reasoning: each acts on the authenticated account's own factor
        # and reads nothing another account owns, and requiring a lens
        # would stop a person who holds none from protecting themselves.
        # Turning it off and renewing recovery codes each also demand a
        # code from the factor itself, not just the session.
        ("GET", "/v1/me/mfa"),
        ("POST", "/v1/me/mfa/setup"),
        ("POST", "/v1/me/mfa/confirm"),
        ("POST", "/v1/me/mfa/disable"),
        ("POST", "/v1/me/mfa/recovery-codes"),
        # The account's own password and its own phone number or email
        # address [0032], exempt on the MFA settings' reasoning: each
        # acts on the authenticated account alone, and a person holding
        # no lens -- an email-only student whose teacher's seats have not
        # reached them yet -- is exactly who must be able to add the
        # phone number that would bring them. Changing a password asks
        # for the current one; adding a destination asks for a code
        # sent to it.
        ("POST", "/v1/me/password"),
        ("POST", "/v1/me/contact"),
        ("POST", "/v1/me/contact/verify"),
        # Removing one of the account's own contacts [U2: FR8.4], on the
        # same reasoning: it acts on the authenticated account alone, and
        # asks for the account's password.
        ("POST", "/v1/me/contact/remove"),
    }
)

#: Every route a :class:`~app.authz.lenses.PlatformAdminLens` reaches,
#: and exactly those [TC-14, D-6]. Asserted in both directions by
#: ``tests/contract/test_admin_routes.py``: a route taking the lens that
#: is not listed fails, and so does a ``/v1/admin`` route that does not
#: take it. The administrator boundary is the most consequential privacy
#: line after the teacher one, so a new route crossing it is a diff
#: against this set rather than a handler that quietly appeared.
PLATFORM_ADMIN_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/v1/admin/overview"),
        ("GET", "/v1/admin/teachers"),
        ("GET", "/v1/admin/help/requesters"),
        ("GET", "/v1/admin/help/tickets"),
        ("GET", "/v1/admin/help/tickets/{ticket_id}"),
        ("POST", "/v1/admin/help/tickets/{ticket_id}/messages"),
        ("PUT", "/v1/admin/help/tickets/{ticket_id}/status"),
    }
)

#: Every route a centre teacher's lens reaches [C4], class or exam. **Exactly these**,
#: and the set is asserted equal to what the application registers, so
#: opening a route to centre teachers is a visible diff and never an
#: accident: a ``ClassTeacherLens`` is not a ``TeacherLens``, and no
#: route accepts it unless it is written for it and listed here.
CLASS_TEACHER_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/v1/me/classes/{session_id}/attendance"),
        ("POST", "/v1/me/classes/{session_id}/attendance"),
        ("PUT", "/v1/me/classes/{session_id}/topic"),
        # The examiner's three [C4]: results, marks and publishing, for
        # the one exam an ExaminerLens carries.
        ("GET", "/v1/me/exams/{exam_id}/results"),
        ("POST", "/v1/me/exams/{exam_id}/marks"),
        ("POST", "/v1/me/exams/{exam_id}/publish"),
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


def class_teacher_routes(app: FastAPI) -> set[tuple[str, str]]:
    """List every route whose dependencies yield a centre teacher's lens.

    Either kind: the per-class ``ClassTeacherLens`` or the per-exam
    ``ExaminerLens``.

    :param app: The application to enumerate
    :return: ``(method, path)`` per such route
    """
    from app.authz.annotations import resolve_lens_type
    from app.authz.lenses import ClassTeacherLens, ExaminerLens

    def yields(dependant: Dependant) -> bool:
        """Report whether this dependency tree yields a class-teacher lens.

        :param dependant: The dependency node
        :return: True if any node returns a ``ClassTeacherLens``
        """
        lens = resolve_lens_type(dependant.call) if dependant.call else None
        if lens is not None and issubclass(lens, ClassTeacherLens | ExaminerLens):
            return True
        return any(yields(sub) for sub in dependant.dependencies)

    found: set[tuple[str, str]] = set()
    for route in _api_routes(app):
        if yields(route.dependant):
            found.update((method, route.path) for method in route.methods or set())
    return found


def platform_admin_routes(app: FastAPI) -> set[tuple[str, str]]:
    """List every route whose dependencies yield a platform admin lens.

    :param app: The application to enumerate
    :return: ``(method, path)`` per such route
    """
    from app.authz.lenses import PlatformAdminLens

    def yields(dependant: Dependant) -> bool:
        """Report whether this dependency tree yields the admin lens.

        :param dependant: The dependency node
        :return: True if any node returns a ``PlatformAdminLens``
        """
        lens = resolve_lens_type(dependant.call) if dependant.call else None
        if lens is not None and issubclass(lens, PlatformAdminLens):
            return True
        return any(yields(sub) for sub in dependant.dependencies)

    found: set[tuple[str, str]] = set()
    for route in _api_routes(app):
        if yields(route.dependant):
            found.update((method, route.path) for method in route.methods or set())
    return found
