"""Both account-deletion paths, over one deletion function.

::

    In-app:    DELETE /v1/me            (authenticated)
    External:  GET    /account-deletion (the page, no session)
               POST   /account-deletion (after OTP ownership proof)

**Both are release-blocking V1 deliverables** [TC-19, RC-4, RC-5]. Play
requires a deletion route reachable without reinstalling the app, which
is why the external pair exists and why it is public; and the in-app
path exists because a person who still has the app should not have to
find a web page.

**The two external entries were already in ``PUBLIC_ROUTES``**, declared
in D1 with the comment "pre-declared D6 scope". D6 lands handlers
against entries already under review rather than editing the
public-route allowlist in the same commit that adds a public route, so
the asserted count of eight does not change.

``DELETE /v1/me`` needs a ``LENS_EXEMPT_AUTHENTICATED`` entry, which is
a **fourth** exemption and the first since D1. Its reason is a property
of the route and not a convenience, on exactly ``GET /v1/me``'s
reasoning: this route acts on the authenticated account ITSELF, so
there is no other account's data to scope, and requiring a lens would
mean an account had to hold a teacher, student or guardian role in
order to delete itself -- which would leave an account holding none of
the three unable to use the feature at all.

**The ceilings are consumed before the gateway call** [BR3.3], through
deletion's **own** cascade. Sharing sign-in's counters would let an
unauthenticated caller lock a victim out of their own account from this
route [NFR14.100].
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.auth import (
    APP_HASH_ENV,
    correlation_of,
    get_gateway,
    ip_prefix_of,
)
from app.api.deps import authenticated_account, get_session
from app.auth import otp
from app.auth.ceilings import CeilingChecker
from app.gateway.outbox import record_outbox
from app.gateway.sms import SmsGateway
from app.gateway.template import render_otp_message
from app.governance.deletion import delete_account
from app.schemas.deletion import (
    DeletionOutcome,
    DeletionRequest,
    DeletionResponse,
)

__all__ = ["DELETION_PAGE", "router"]

router = APIRouter(tags=["deletion"])

#: Resolves the number from the authenticated account, because
#: :func:`~app.governance.deletion.delete_account` is keyed on the phone
#: -- the two phone-scoped tables it must clear have no account column
#: to match on.
_PHONE_OF_ACCOUNT = sa.text("SELECT phone FROM account WHERE id = :account_id")

#: The page a person reaches from the Play listing. Play requires the
#: route to **name the app and the developer** so a person can tell they
#: are on the right page before typing their number into it [AC1.7.2].
#:
#: Served as a string constant rather than from a template engine: this
#: is the product's only HTML, and adding a template dependency for one
#: page would be the larger change. It states what deletion removes and
#: what survives, in the terms the generated privacy policy uses -- but
#: it is NOT generated from the manifest, and that is a known gap
#: recorded rather than hidden: the policy is the generated document,
#: and this page points at it.
DELETION_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Delete your ShikkhokPlus account</title>
</head>
<body>
<h1>Delete your ShikkhokPlus account</h1>
<p>App: <strong>ShikkhokPlus</strong> (com.shikkhokplus.app)</p>
<p>Developer: <strong>Nirmata</strong></p>
<p>
  Request a code on your registered phone number, then enter it to
  delete your account. You do not need the app installed.
</p>
<p>
  Your account, your phone number and anything you wrote about
  yourself are deleted permanently. Records your teacher wrote --
  attendance, marks and fee entries -- stay with your teacher's own
  records, with your account link removed. See the privacy policy for
  the full list.
</p>
<p>
  If you teach classes on ShikkhokPlus, hand them over or close them
  before deleting your account.
</p>
<form method="post" action="/account-deletion">
  <label for="phone">Phone number</label>
  <input id="phone" name="phone" type="tel" required>
  <label for="code">Code</label>
  <input id="code" name="code" type="text" inputmode="numeric">
  <button type="submit">Delete my account</button>
</form>
</body>
</html>
"""


@router.get("/account-deletion", response_class=HTMLResponse)
def deletion_page() -> HTMLResponse:
    """Serve the externally reachable deletion page.

    No session, no database read and no parameters: it is a static page
    whose only job is to be reachable and to name the app and developer
    [AC1.7.2].

    :return: The page
    """
    return HTMLResponse(content=DELETION_PAGE)


@router.post("/account-deletion", response_model=DeletionOutcome)
def external_deletion(
    body: DeletionRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[SmsGateway, Depends(get_gateway)],
) -> DeletionOutcome:
    """Send a deletion code, or delete once one is presented.

    **One route with two steps rather than two routes**, and that is a
    deliberate consequence of the allowlist rather than a convenience.
    ``PUBLIC_ROUTES`` declares exactly two external deletion entries,
    its count is asserted at eight, and D6's stated job is to land
    handlers against entries already under review -- not to add a public
    route in the commit that implements one. A separate
    ``/account-deletion/code`` would have been a ninth public entry,
    which is a diff against a stated number [BR3.2].

    The step is chosen by whether ``code`` is present, which is also how
    the page's single form behaves: submit a number to be sent a code,
    submit it again with the code to confirm.

    ``verify`` is CALLED rather than reimplemented, which is what gives
    this route the single-use rule, the expiry and the attempt ceiling
    without a second copy of any of them [NFR14.81]. Reimplementing it
    is the obvious shortcut for a route living in a different module.

    :param body: The request body
    :param request: The incoming request
    :param session: The request-scoped session
    :param gateway: The configured SMS gateway
    :return: ``requested`` after a code is sent, ``deleted`` after one
        is spent
    :raises CeilingBreach: A deletion ceiling refused this send
    :raises ValidationError: The code is wrong, expired, used or was
        issued for a different purpose
    :raises DeletionRefused: The account owns at least one batch
    """
    correlation_id = correlation_of(request)

    if body.code is None:
        # BEFORE the gateway call, through deletion's OWN cascade
        # [BR3.3, NFR14.100]. Sharing sign-in's counters would let an
        # unauthenticated caller lock a victim out of their account
        # from this very route.
        CeilingChecker(session).check_and_consume_deletion(
            number=body.phone, ip_prefix=ip_prefix_of(request)
        )
        issued = otp.issue(
            session,
            body.phone,
            correlation_id,
            purpose=otp.DELETION_PURPOSE,
        )
        message = render_otp_message(issued.code, os.environ.get(APP_HASH_ENV, ""))
        gateway.send(body.phone, message, correlation_id)

        # Records the message a staging host did NOT text, exactly as
        # the sign-in route does, and GUARDED ON `account_exists` for
        # the same reason: the unknown-number path renders a message it
        # never persisted a code for, and recording that would put an
        # entry in the outbox for a number with no account. That is an
        # existence oracle in a new place -- the thing `issue`'s
        # rolled-back write exists to close, reintroduced one endpoint
        # over, on the route where the caller is unauthenticated.
        #
        # A no-op unless the environment permits it and an operator
        # opted in, so production runs it to no effect.
        if issued.account_exists:
            record_outbox(
                session,
                phone=body.phone,
                message=message,
                correlation_id=correlation_id,
            )

        # The SAME response either way [BR2.7]. `issue` already does
        # equivalent work on both branches, and the schema has fixed
        # fields, so there is nothing here that could differ.
        return DeletionOutcome(status="requested")

    otp.verify(
        session,
        body.phone,
        body.code,
        correlation_id,
        purpose=otp.DELETION_PURPOSE,
    )
    delete_account(session, body.phone)
    return DeletionOutcome(status="deleted")


@router.delete("/v1/me", response_model=DeletionResponse)
def delete_own_account(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> DeletionResponse:
    """Delete the authenticated account.

    **The same deletion function the external route calls** [BR3.1].
    The access token is the ownership proof here, where the external
    route uses a verified code, and that is the ONLY difference between
    the two paths -- the outcome is identical row for row, which the
    test asserts by comparing the surviving row sets rather than each
    against a hand-written expectation.

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: The acknowledgement
    :raises DeletionRefused: The account owns at least one batch
    """
    phone: str | None = session.execute(
        _PHONE_OF_ACCOUNT, {"account_id": account_id}
    ).scalar_one_or_none()

    # An authenticated token naming an account that no longer exists is
    # the double-click case [BR1.4], not an error: the token outlives
    # the row by its own lifetime. Reporting success is honest -- the
    # account is gone, which is what was asked for.
    if phone is not None:
        delete_account(session, phone)

    return DeletionResponse()
