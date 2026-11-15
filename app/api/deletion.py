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
route [NFR14.100]. The per-number and per-IP scopes are consumed on the
request path for every number; deletion's daily send budget only at the
send itself, so an unknown number spends none of it [PA-SEC-2].
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass
from typing import Annotated, Final
from urllib.parse import parse_qs

import sqlalchemy as sa
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.accounts.identifier import Channel, Identifier
from app.api.auth import (
    coarse_prefix_of,
    correlation_of,
    get_email_gateway,
    get_gateway,
    ip_prefix_of,
)
from app.api.deps import authenticated_account, get_session, token_subject
from app.api.html import html_response
from app.audit.log import AuthEvent, write_audit
from app.auth import otp
from app.auth.ceilings import CeilingBreach, CeilingChecker, SendBudget
from app.auth.delivery import deliver_code
from app.auth.mfa import APP_DOOR, check_code, load_factor
from app.auth.totp import DIGITS
from app.db.retry import run_with_retry
from app.errors import ConflictError, ValidationError
from app.gateway.email import EmailGateway
from app.gateway.sms import SmsGateway
from app.governance.deletion import delete_account
from app.governance.footprint import teacher_footprint
from app.money.wire import to_wire
from app.schemas.deletion import (
    DeletionOutcome,
    DeletionRequest,
    DeletionResponse,
    DeletionSummaryResponse,
)
from app.schemas.money import Money as WireMoney

__all__ = [
    "CODE_SENT_NOTICE",
    "DELETED_NOTICE",
    "DELETION_PAGE",
    "INVALID_NOTICE",
    "router",
]

router = APIRouter(tags=["deletion"])

#: Resolves the number from the authenticated account, because
#: :func:`~app.governance.deletion.delete_account` is keyed on the phone
#: number or the address -- the destination-scoped tables it must clear
#: have no account column to match on.
_DESTINATION_OF_ACCOUNT = sa.text(
    "SELECT phone, email FROM account WHERE id = :account_id"
)

#: The page a person reaches from the Play listing. Play requires the
#: route to **name the app and the developer** so a person can tell they
#: are on the right page before typing their number into it [AC1.7.2].
#:
#: Served from a string template rather than a template engine: this is
#: the product's only HTML, and adding a template dependency for one page
#: would be the larger change. It states what deletion removes and what
#: survives, in the terms the generated privacy policy uses -- but it is
#: NOT generated from the manifest, and that is a known gap recorded
#: rather than hidden: the policy is the generated document, and this
#: page points at it.
#:
#: **Every value substituted into it is escaped** by :func:`_render`,
#: including the canonical phone number, which is validated and could
#: not carry markup -- escaping at the one substitution site is cheaper
#: than proving that for each caller.
_PAGE_TEMPLATE: Final = """<!DOCTYPE html>
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
{notice}<p>
  Request a code on your registered phone number or email address, then
  enter it to delete your account. You do not need the app installed.
</p>
<p>
  Your account, your phone number, your email address and anything you
  wrote about
  yourself are deleted permanently. Records your teacher wrote --
  attendance, marks and fee entries -- stay with your teacher's own
  records, with your account link removed. See the privacy policy for
  the full list.
</p>
<p>
  If you teach classes on ShikkhokPlus, they stay with your students
  as read-only history: your name and payment number are removed from
  them, no new fees fall due, and amounts already owed stay on the
  records.
</p>
{form}</body>
</html>
"""

_FORM_TEMPLATE: Final = """<form method="post" action="/account-deletion">
  <label for="phone">Phone number or email address</label>
  <input id="phone" name="phone" type="text" required value="{phone}"
    autocomplete="username">
  <label for="code">Code</label>
  <input id="code" name="code" type="text" inputmode="numeric">
  <label for="authenticator_code">Authenticator code
    (only if you turned on two-step verification)</label>
  <input id="authenticator_code" name="authenticator_code" type="text"
    autocomplete="one-time-code">
  <button type="submit">Delete my account</button>
</form>
"""

#: What the confirm step says. **Identical for a number with an account
#: and one without** [BR2.7], which is why it says "if": the page cannot
#: know, and must not be made to.
CODE_SENT_NOTICE: Final = (
    "If this number or address has a ShikkhokPlus account, we have sent "
    "a code to it. Enter the code below and submit to delete the account. "
    "To get a new code, leave the code box empty and submit again."
)

#: The last page, with no form: there is nothing left to submit.
DELETED_NOTICE: Final = "Your ShikkhokPlus account has been deleted."

#: The English copy for each refusal the form path can meet, keyed by
#: the same ``message_key`` the JSON envelope carries and worded as the
#: app's English bundle words it. The page is English, as the GET page
#: always was; localising it is a separate change.
_REFUSAL_COPY: Final = {
    "auth.otp.wrong": "That code isn't right. {attempts_left} tries left.",
    "auth.otp.expired": (
        "That code has expired. Codes last 5 minutes. Leave the code box "
        "empty and submit to get a new one."
    ),
    "auth.otp.no_tries_left": (
        "That code isn't right, and no tries are left. Leave the code box "
        "empty and submit to get a new code."
    ),
    "auth.otp.not_valid": (
        "That code is not valid. Leave the code box empty and submit to get a new one."
    ),
    "auth.otp.temporarily_unavailable": (
        "We cannot send a code right now. Please try again later."
    ),
    # The network-wide failed-verify ceilings [SEC-6]. Says nothing about
    # the code or the number: nothing was checked.
    "auth.verify.temporarily_unavailable": (
        "Too many wrong codes have been tried from your network. "
        "Please try again later."
    ),
    # Two-step verification [0028]. The SMS code has been spent by the
    # time these are shown, so each says to request a new one.
    "mfa.code_required": (
        "This account has two-step verification on. Leave the code box "
        "empty and submit to get a new code, then enter it together with "
        "the 6-digit code from your authenticator app, or a recovery code."
    ),
    "mfa.code_wrong": (
        "That authenticator code isn't right. Leave the code box empty and "
        "submit to get a new SMS code, then try again."
    ),
    "mfa.locked": ("Too many wrong authenticator codes. Try again in 15 minutes."),
}

#: For a submission that fails schema validation, or a refusal with no
#: entry above.
INVALID_NOTICE: Final = (
    "Check the phone number or email address and the code, then submit "
    "again. Use the one your account is registered with, like 01711234567."
)

#: A form submission is two short fields; anything far larger is not
#: this page's form, and is refused before it is parsed.
_MAX_FORM_BYTES: Final = 2048

_FORM_CONTENT_TYPE: Final = "application/x-www-form-urlencoded"


def _render(
    *, notice: str | None = None, phone: str = "", show_form: bool = True
) -> str:
    """Render the deletion page, escaping every substituted value.

    :param notice: A sentence shown above the explanation, or None
    :param phone: The number to prefill the form with
    :param show_form: Whether the page still offers the form
    :return: The page's HTML
    """
    notice_html = f"<p><strong>{html.escape(notice)}</strong></p>\n" if notice else ""
    form_html = (
        _FORM_TEMPLATE.format(phone=html.escape(phone, quote=True)) if show_form else ""
    )
    return _PAGE_TEMPLATE.format(notice=notice_html, form=form_html)


#: The page as first served: no notice, an empty form.
DELETION_PAGE: Final = _render()


@dataclass(frozen=True, slots=True)
class DeletionSubmission:
    """One POST to the external route, as JSON or as the page's form.

    :ivar body: The validated JSON body, or None for a form submission
    :ivar form: The form's ``phone`` and ``code``, or None for JSON.
        Validated by the handler rather than here, so a bad form value
        can be answered with a page instead of FastAPI's JSON 422.
    """

    body: DeletionRequest | None
    form: dict[str, str | None] | None


def _form_fields(raw: bytes) -> dict[str, str | None]:
    """Read the page form's two fields from an urlencoded body.

    **A blank code is an absent code.** The page has one form with an
    optional code box, so a browser submitting it empty sends
    ``code=`` -- which, read literally, is a code of length zero to
    verify, and the person asking for a code would be told theirs is
    wrong. Whitespace is stripped first, since a pasted code often
    carries some.

    Parsed with the standard library rather than ``request.form()``:
    Starlette's form parser needs ``python-multipart``, a new runtime
    dependency for one two-field form.

    :param raw: The request body
    :return: ``phone`` and ``code``, either possibly None
    :raises ValueError: The body is not this page's form
    """
    if len(raw) > _MAX_FORM_BYTES:
        raise ValueError("form body too large")
    parsed = parse_qs(
        raw.decode("utf-8", errors="replace"),
        keep_blank_values=True,
        max_num_fields=8,
    )

    def first(name: str) -> str | None:
        """Return a field's first value, stripped, or None when blank.

        :param name: The field name
        :return: The value, or None
        """
        values = parsed.get(name)
        value = values[0].strip() if values else ""
        return value or None

    # One box for a number or an address [0032]: an "@" says which.
    typed = first("phone")
    is_email = typed is not None and "@" in typed
    return {
        "phone": None if is_email else typed,
        "email": typed if is_email else None,
        "code": first("code"),
        "authenticator_code": first("authenticator_code"),
    }


async def read_submission(request: Request) -> DeletionSubmission:
    """Read the POST body as the page's form or as JSON.

    **One route, two encodings**, because ``PUBLIC_ROUTES`` asserts its
    count and a second route for the browser would be a further entry
    [BR3.2]. The page's plain HTML form posts urlencoded; every other
    content type is read as JSON, exactly as before, and a JSON body
    that fails validation still answers FastAPI's 422.

    :param request: The incoming request
    :return: The submission, tagged with how it arrived
    :raises RequestValidationError: A JSON body is malformed or invalid
    """
    raw = await request.body()
    content_type = request.headers.get("content-type", "")
    if content_type.split(";", 1)[0].strip().lower() == _FORM_CONTENT_TYPE:
        try:
            return DeletionSubmission(body=None, form=_form_fields(raw))
        except ValueError:
            return DeletionSubmission(
                body=None,
                form={
                    "phone": None,
                    "email": None,
                    "code": None,
                    "authenticator_code": None,
                },
            )
    try:
        return DeletionSubmission(
            body=DeletionRequest.model_validate_json(raw), form=None
        )
    except PydanticValidationError as error:
        raise RequestValidationError(
            [
                {**detail, "loc": ("body", *detail["loc"])}
                for detail in error.errors(include_url=False)
            ]
        ) from error


#: The request body, documented by hand because the handler reads it
#: through :func:`read_submission` rather than a body parameter. Both
#: encodings carry the same two fields under the same rules.
_REQUEST_BODY: Final = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": DeletionRequest.model_json_schema()},
            _FORM_CONTENT_TYPE: {"schema": DeletionRequest.model_json_schema()},
        },
    }
}


@router.get("/account-deletion", response_class=HTMLResponse)
def deletion_page() -> HTMLResponse:
    """Serve the externally reachable deletion page.

    No session, no database read and no parameters: it is a static page
    whose only job is to be reachable and to name the app and developer
    [AC1.7.2].

    :return: The page
    """
    return html_response(DELETION_PAGE)


@router.post(
    "/account-deletion",
    response_model=DeletionOutcome,
    openapi_extra=_REQUEST_BODY,
    responses={
        200: {
            "description": (
                "JSON for a JSON request; an HTML page for a form submission"
            ),
            "content": {"text/html": {"schema": {"type": "string"}}},
        },
        # Declared by hand because the body is read by a dependency, so
        # FastAPI no longer adds it -- and the JSON path still returns
        # it for a body that fails validation.
        422: {
            "description": "Validation Error",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/HTTPValidationError"}
                },
                "text/html": {"schema": {"type": "string"}},
            },
        },
    },
)
def external_deletion(
    submission: Annotated[DeletionSubmission, Depends(read_submission)],
    request: Request,
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[SmsGateway, Depends(get_gateway)],
    email_gateway: Annotated[EmailGateway, Depends(get_email_gateway)],
) -> DeletionOutcome | HTMLResponse:
    """Send a deletion code, or delete once one is presented.

    **One route with two steps rather than two routes**, and that is a
    deliberate consequence of the allowlist rather than a convenience.
    ``PUBLIC_ROUTES`` declares exactly two external deletion entries
    and asserts its count, and D6's stated job is to land handlers
    against entries already under review -- not to add a public route
    in the commit that implements one. A separate
    ``/account-deletion/code`` would have been a further public entry,
    which is a diff against a stated number [BR3.2].

    The step is chosen by whether ``code`` is present, which is also how
    the page's single form behaves: submit a number to be sent a code,
    submit it again with the code to confirm.

    **A form submission is answered with a page** [PA-SEC-1]: the
    confirm step with the number prefilled, the deleted page, or the
    form again with what went wrong. A JSON submission is answered as
    it always was, with the outcome or the error envelope. From the
    form, an empty or whitespace-only code box means no code.

    :param submission: The body, as JSON or as the page's form
    :param request: The incoming request
    :param background: Runs the SMS send after the response is written
    :param session: The request-scoped session
    :param gateway: The configured SMS gateway
    :param email_gateway: The configured email gateway
    :return: ``requested`` after a code is sent, ``deleted`` after one
        is spent -- or the page saying so, for a form submission
    :raises CeilingBreach: A deletion ceiling refused a JSON send
    :raises ValidationError: A JSON submission's code is wrong, expired,
        used or was issued for a different purpose
    """
    if submission.body is not None:
        return _external_deletion(
            submission.body, request, background, session, gateway, email_gateway
        )

    fields = submission.form or {}
    try:
        body = DeletionRequest.model_validate(fields)
    except (PydanticValidationError, ValidationError):
        # The phone canonicaliser raises the app's own ValidationError
        # from inside the model; a code of the wrong length is
        # pydantic's. Both mean "nothing we can act on", and neither has
        # reached the database.
        typed = fields.get("phone") or fields.get("email") or ""
        return _page(422, notice=INVALID_NOTICE, phone=typed)

    typed = body.identifier.value
    try:
        outcome = _external_deletion(
            body, request, background, session, gateway, email_gateway
        )
    except (ValidationError, ConflictError) as refusal:
        copy = _REFUSAL_COPY.get(refusal.message_key, INVALID_NOTICE)
        status = 409 if isinstance(refusal, ConflictError) else 400
        return _page(
            status,
            notice=copy.format_map(refusal.details or {}),
            phone=typed,
        )

    if outcome.status == "deleted":
        return _page(200, notice=DELETED_NOTICE, show_form=False)
    # THE SAME PAGE for a known and an unknown number [BR2.7]: the only
    # value in it is the number the caller typed, canonicalised.
    return _page(200, notice=CODE_SENT_NOTICE, phone=typed)


def _page(
    status: int, *, notice: str, phone: str = "", show_form: bool = True
) -> HTMLResponse:
    """Answer a form submission with the page.

    :param status: The HTTP status, mirroring the JSON path's
    :param notice: What happened, in a sentence
    :param phone: The number to prefill
    :param show_form: Whether to offer the form again
    :return: The response
    """
    return html_response(
        _render(notice=notice, phone=phone, show_form=show_form), status
    )


def _external_deletion(
    body: DeletionRequest,
    request: Request,
    background: BackgroundTasks,
    session: Session,
    gateway: SmsGateway,
    email_gateway: EmailGateway,
) -> DeletionOutcome:
    """Run one step of the external route, whichever encoding asked.

    ``verify`` is CALLED rather than reimplemented, which is what gives
    this route the single-use rule, the expiry and the attempt ceiling
    without a second copy of any of them [NFR14.81]. Reimplementing it
    is the obvious shortcut for a route living in a different module.

    :param body: The validated request
    :param request: The incoming request
    :param background: Runs the SMS send after the response is written
    :param session: The request-scoped session
    :param gateway: The configured SMS gateway
    :param email_gateway: The configured email gateway
    :return: ``requested`` after a code is sent, ``deleted`` after one
        is spent
    :raises CeilingBreach: A deletion ceiling refused this send, or a
        failed-verify ceiling refused this verify
    :raises ValidationError: The code is wrong, expired, used or was
        issued for a different purpose
    """
    correlation_id = correlation_of(request)
    identifier = body.identifier

    if body.code is None:
        # BEFORE the gateway call, through deletion's OWN cascade
        # [BR3.3, NFR14.100]. Sharing sign-in's counters would let an
        # unauthenticated caller lock a victim out of their account
        # from this very route.
        CeilingChecker(session).check_and_consume_deletion(
            number=identifier.rate_key, ip_prefix=ip_prefix_of(request)
        )
        issued = otp.issue(
            session,
            identifier,
            correlation_id,
            purpose=otp.DELETION_PURPOSE,
        )

        # Only a destination with an account is sent to, and only after
        # the response, for the reasons the sign-in route gives: a code
        # sent where there is no account can confirm nothing, and
        # sending inline would make the known branch slower by a gateway
        # round trip, which is a timing oracle [BR2.7]. A text spends
        # deletion's daily budget, an email the email budget, inside the
        # deferred task, by real sends only [PA-SEC-2, NFR14.102]. A code
        # whose send a budget skipped is killed [C-20].
        #
        # The staging outbox entry rides the same guard: recording one
        # for a destination with no account would be an existence oracle
        # one endpoint over, on the route where the caller is
        # unauthenticated.
        if issued.account_exists:
            deliver_code(
                background,
                session,
                identifier,
                issued.code,
                correlation_id,
                sms_budget=SendBudget.DELETION,
                sms_gateway=gateway,
                email_gateway=email_gateway,
                otp_request_id=issued.request_id,
            )

        # The SAME response either way [BR2.7]. `issue` already does
        # equivalent work on both branches, and the schema has fixed
        # fields, so there is nothing here that could differ.
        return DeletionOutcome(status="requested")

    # **The same guessing controls as ``POST /v1/auth/verify``** [SEC-6,
    # C-20]. The route that destroys data used to have the weakest: no
    # /64, /48 or global failed-verify ceiling, and no dead-code
    # cool-off. A verify is refused before its code is checked while any
    # of those ceilings is full, and every failure counts against them.
    checker = CeilingChecker(session)
    ip_prefix = ip_prefix_of(request)
    coarse_prefix = coarse_prefix_of(request)
    try:
        checker.check_verify_allowed(ip_prefix, coarse_prefix)
    except CeilingBreach:
        write_audit(session, None, AuthEvent.VERIFY_CEILING_BREACHED, correlation_id)
        session.commit()
        raise
    try:
        account_id = otp.verify(
            session,
            identifier,
            body.code,
            correlation_id,
            purpose=otp.DELETION_PURPOSE,
        )
    except otp.CodeRefused as refusal:
        checker.record_verify_failure(ip_prefix, coarse_prefix)
        if refusal.code_died:
            checker.record_dead_code(identifier.rate_key)
        raise
    # **The second factor guards deletion too** [0028]. Asked only after
    # the SMS code has proven the phone, so the page never says which
    # numbers have it; a SIM swap alone then cannot destroy an account
    # its owner protected.
    factor = load_factor(session, account_id)
    if factor is not None and factor.confirmed_at is not None:
        typed = body.authenticator_code
        if typed is None:
            raise ValidationError(
                code="MFA_CODE_REQUIRED", message_key="mfa.code_required"
            )
        digits = typed.replace(" ", "")
        is_totp = digits.isdigit() and len(digits) == DIGITS
        check_code(
            session,
            account_id,
            factor,
            digits if is_totp else None,
            None if is_totp else typed,
            APP_DOOR,
            correlation_id,
        )
    # `otp.verify` committed the spent code above, so the retried unit of
    # work is the deletion alone [U2: NFR4.3]; it sends nothing.
    run_with_retry(
        session,
        lambda: delete_account(session, identifier),
        correlation_id=correlation_id,
    )
    return DeletionOutcome(status="deleted")


@router.get("/v1/me/deletion-summary", response_model=DeletionSummaryResponse)
def read_deletion_summary(
    account_id: Annotated[uuid.UUID, Depends(authenticated_account)],
    session: Annotated[Session, Depends(get_session)],
) -> DeletionSummaryResponse:
    """Tell the caller what stays if they delete their account.

    Lens-exempt on ``DELETE /v1/me``'s reasoning: it reads only what the
    authenticated account itself owns.

    :param account_id: The authenticated account
    :param session: The request-scoped session
    :return: Batches, students and money still owed; zeros when none
    """
    found = teacher_footprint(session, account_id)
    return DeletionSummaryResponse(
        batch_count=found.batch_count,
        student_count=found.student_count,
        outstanding=WireMoney(to_wire(found.outstanding)),
    )


@router.delete("/v1/me", response_model=DeletionResponse)
def delete_own_account(
    # The token's subject, NOT authenticated_account: a second tap on
    # Delete arrives with a token whose account this route has just
    # removed, and must report the deletion rather than a 401 [BR1.4].
    account_id: Annotated[uuid.UUID, Depends(token_subject)],
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
    """
    row = session.execute(
        _DESTINATION_OF_ACCOUNT, {"account_id": account_id}
    ).one_or_none()

    # An authenticated token naming an account that no longer exists is
    # the double-click case [BR1.4], not an error: the token outlives
    # the row by its own lifetime. Reporting success is honest -- the
    # account is gone, which is what was asked for.
    if row is not None:
        destination = (
            Identifier(Channel.PHONE, row.phone)
            if row.phone
            else Identifier(Channel.EMAIL, row.email)
        )
        # Re-run on a deadlock or serialization failure [U2: NFR4.3].
        run_with_retry(
            session,
            lambda: delete_account(session, destination),
            correlation_id=None,
        )

    return DeletionResponse()
