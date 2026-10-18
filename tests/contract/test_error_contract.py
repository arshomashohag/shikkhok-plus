"""The error taxonomy, its envelope, and the non-disclosure rule.

Test-after by the team's predicate: the shape is knowable from the
requirement, but a wrong answer here is a 500 rather than a leak, so these
follow the implementation.

One exception is the non-disclosure group, which *is* an authorization
property -- it is written here rather than earlier only because it asserts
over a registry the implementation defines.
"""

from __future__ import annotations

import json

import pytest

from app.errors import (
    AuthorizationError,
    ConflictError,
    FatalError,
    TaxonomyError,
    TransientError,
    ValidationError,
    to_response,
)
from app.errors._exhaustive import TaxonomyClass, status_for
from app.errors.codes import (
    ACCESS_TOKEN_EXPIRED,
    AUTH_401_CODES,
    AUTH_403_CODES,
    NOT_AVAILABLE,
    TOKEN_MISSING,
    auth_status_for,
)


def _body(error: TaxonomyError) -> dict[str, object]:
    """Render an error and return its decoded envelope body.

    :param error: The error to render
    :return: The ``error`` object from the response envelope
    """
    response = to_response(error)
    payload = json.loads(bytes(response.body))
    assert isinstance(payload["error"], dict)
    return payload["error"]


# --------------------------------------------------------------------------
# Class-to-status mapping
# --------------------------------------------------------------------------


def test_validation_error_maps_to_400() -> None:
    """A validation error is a 400.

    :return: None
    """
    assert to_response(ValidationError("BAD", "error.bad")).status_code == 400


def test_conflict_error_maps_to_409() -> None:
    """A conflict is a 409.

    :return: None
    """
    assert to_response(ConflictError("C", "error.c")).status_code == 409


def test_transient_error_maps_to_503() -> None:
    """A transient failure is a 503.

    :return: None
    """
    assert to_response(TransientError("T", "error.t")).status_code == 503


def test_fatal_error_maps_to_500() -> None:
    """A fatal error is a 500.

    :return: None
    """
    assert to_response(FatalError("F", "error.f")).status_code == 500


def test_authorization_error_carries_both_statuses() -> None:
    """Authorization is the one class with two legitimate statuses.

    :return: None
    """
    missing = AuthorizationError(TOKEN_MISSING, "error.auth", status=401)
    refused = AuthorizationError(NOT_AVAILABLE, "error.auth", status=403)

    assert to_response(missing).status_code == 401
    assert to_response(refused).status_code == 403


# --------------------------------------------------------------------------
# retryable is derived at the handler, never set at a raise site
# --------------------------------------------------------------------------


def test_only_transient_is_retryable() -> None:
    """``retryable`` is read from the class and from nowhere else.

    A raise site that set it itself would let two sites of one class
    disagree, which is the condition the closed hierarchy prevents.

    :return: None
    """
    assert _body(TransientError("T", "error.t"))["retryable"] is True
    for error in (
        ValidationError("V", "error.v"),
        AuthorizationError(NOT_AVAILABLE, "error.a"),
        ConflictError("C", "error.c"),
        FatalError("F", "error.f"),
    ):
        assert _body(error)["retryable"] is False


def test_retryable_is_false_on_401_which_is_correct() -> None:
    """A 401 is not retryable, and that is not a contradiction.

    ``retryable`` answers "may the client repeat THIS REQUEST UNCHANGED?",
    which for an expired token is genuinely no: repeating it with the same
    token fails identically. What the refresh rule permits is a *different*
    request followed by exactly one replay, only on this code, with any
    second 401 ending the session.

    :return: None
    """
    expired = AuthorizationError(ACCESS_TOKEN_EXPIRED, "error.expired", status=401)
    assert _body(expired)["retryable"] is False


# --------------------------------------------------------------------------
# The envelope
# --------------------------------------------------------------------------


def test_envelope_carries_the_three_required_fields() -> None:
    """Every error body carries code, retryable and message_key.

    :return: None
    """
    body = _body(ValidationError("BAD_INPUT", "error.bad_input"))
    assert body["code"] == "BAD_INPUT"
    assert body["message_key"] == "error.bad_input"
    assert "retryable" in body


def test_no_english_message_field_is_ever_emitted() -> None:
    """No ``message`` field appears at any level.

    A server-authored English string cannot be localized by the client, and
    in a Bangla-first UI that guarantees untranslated English error text in
    front of a teacher.

    :return: None
    """
    payload = json.loads(bytes(to_response(FatalError("F", "error.f")).body))
    assert "message" not in payload
    assert "message" not in payload["error"]


def test_details_are_typed_and_optional() -> None:
    """``details`` is a typed mapping, absent when not supplied.

    It is never a free-form dump of request state, which is what keeps a
    phone number, an OTP or a token from being casually placed in it.

    :return: None
    """
    assert _body(ValidationError("V", "error.v"))["details"] is None
    assert _body(ValidationError("V", "error.v", {"field": "phone"}))["details"] == {
        "field": "phone"
    }


# --------------------------------------------------------------------------
# Non-disclosure: the registry must not contain an existence oracle
# --------------------------------------------------------------------------


def test_one_code_covers_both_unreachable_and_absent() -> None:
    """A single code serves both cases, so neither is distinguishable.

    A pair such as ``BATCH_NOT_FOUND`` / ``BATCH_NOT_YOURS`` is an oracle
    even though each code reads as good practice alone.

    :return: None
    """
    assert NOT_AVAILABLE in AUTH_403_CODES
    oracle_shaped = {
        code
        for code in AUTH_403_CODES
        if "NOT_FOUND" in code or "NOT_YOURS" in code or "FORBIDDEN" in code
    }
    assert not oracle_shaped, f"existence-oracle codes registered: {oracle_shaped}"


def test_a_403_never_carries_a_401_only_code() -> None:
    """The status/code pairing is asserted, not assumed.

    A 403 carrying ``ACCESS_TOKEN_EXPIRED`` would tell a prober that their
    token was fine and the *resource* was the problem -- the oracle
    re-entering through a field the status rule alone does not constrain.

    :return: None
    """
    assert not (AUTH_401_CODES & AUTH_403_CODES)
    assert auth_status_for(ACCESS_TOKEN_EXPIRED) == 401
    assert auth_status_for(TOKEN_MISSING) == 401
    assert auth_status_for(NOT_AVAILABLE) == 403


def test_an_unregistered_authorization_code_is_refused() -> None:
    """A code in neither set raises rather than defaulting to a status.

    :return: None
    """
    with pytest.raises(KeyError):
        auth_status_for("INVENTED_CODE")


# --------------------------------------------------------------------------
# Totality
# --------------------------------------------------------------------------


def test_the_closed_union_matches_the_actual_subclasses() -> None:
    """Every direct subclass of the base appears in the closed union.

    This is the half ``assert_never`` cannot reach. The exhaustiveness
    proof in ``_exhaustive.py`` fails at type-check time when a class is
    added to the union but not to the match -- but it is silent when a
    sixth class is added to the taxonomy and to *neither*. This test closes
    that gap at runtime, so the two together are total.

    :return: None
    """
    declared = set(TaxonomyClass.__value__.__args__)
    actual = set(TaxonomyError.__subclasses__())

    assert actual == declared, (
        "a taxonomy class is missing from the closed union in "
        f"_exhaustive.py: {actual ^ declared}"
    )


def test_status_for_covers_every_class() -> None:
    """The exhaustive mapping returns a status for all five.

    :return: None
    """
    assert status_for(ValidationError("V", "error.v")) == 400
    assert status_for(ConflictError("C", "error.c")) == 409
    assert status_for(TransientError("T", "error.t")) == 503
    assert status_for(FatalError("F", "error.f")) == 500
    assert status_for(AuthorizationError(NOT_AVAILABLE, "error.a")) == 403


def test_a_bare_taxonomy_error_is_refused() -> None:
    """The abstract base is not renderable; raise sites choose a class.

    :return: None
    """
    with pytest.raises(TypeError, match="must choose one"):
        to_response(TaxonomyError("X", "error.x"))
