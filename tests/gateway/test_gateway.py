"""The gateway boundary: the one place a failure costs money.

Three assertions here fail against implementations that look correct:

* **HTTP 200 carrying an error code is not success.** This gateway
  returns 200 with the error in the body, so ``raise_for_status()`` is
  worthless -- and the most-installed Python client for it parses
  ``code`` rather than ``response_code``, with tests mocking
  ``{'code': 202}`` that pass against a fiction.
* **The null adapter is the default.** A missing setting must fail
  toward not sending.
* **``error_message`` is never logged.** It echoes the API key back in
  plaintext, verified live.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from app.errors import (
    AuthorizationError,
    ConflictError,
    FatalError,
    TransientError,
    ValidationError,
)
from app.gateway.bulksmsbd import (
    ALERTING_CODES,
    SUCCESS_CODE,
    BulkSmsBdGateway,
    outcome_for_code,
    taxonomy_for_code,
)
from app.gateway.null import ADAPTER_ENV, NullGateway, build_gateway
from app.gateway.sms import Outcome
from app.gateway.template import (
    APP_HASH_LENGTH,
    GSM7_SEGMENT,
    gsm7_length,
    render_otp_message,
)

BASE = "https://bulksmsbd.net/api/smsapi"
CORRELATION = "test-correlation-id"
LEAKY_ERROR = "user id not found in this SECRETKEY123 key"


def _gateway() -> BulkSmsBdGateway:
    """Build the adapter under test, with a key worth leaking.

    The key is a recognisable literal so the log assertions can prove
    it did NOT appear, rather than proving nothing against a blank.

    :return: The adapter under test
    """
    return BulkSmsBdGateway(
        base_url=BASE, api_key="SECRETKEY123", sender_id="ShikhokPlus"
    )


def _respond(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response | Exception
) -> list[str]:
    """Make ``httpx.post`` return one response or raise.

    :param monkeypatch: The patcher
    :param response: What the call should produce
    :return: The urls called
    """
    seen: list[str] = []

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        seen.append(url)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(httpx, "post", fake_post)
    return seen


# ---------------------------------------------------------------------------
# 202 AND NOTHING ELSE. [BR5.1]
# ---------------------------------------------------------------------------


def test_response_code_202_is_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _respond(
        monkeypatch,
        httpx.Response(200, json={"response_code": SUCCESS_CODE}),
    )
    result = _gateway().send("+8801711111111", "body", CORRELATION)
    assert result.outcome is Outcome.SENT


def test_http_200_carrying_an_error_code_is_not_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # THE ONE raise_for_status() WOULD GET WRONG. An application
    # failure arrives as HTTP 200 with the error in the body.
    _respond(
        monkeypatch,
        httpx.Response(
            200,
            json={
                "response_code": 1011,
                "success_message": "",
                "error_message": LEAKY_ERROR,
            },
        ),
    )
    result = _gateway().send("+8801711111111", "body", CORRELATION)
    assert result.outcome is Outcome.FAILED


def test_the_field_is_response_code_not_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The most-installed Python client for this gateway parses `code`
    # and mocks {'code': 202} in its tests, so its tests pass against a
    # fiction. A body carrying only `code` must NOT read as success.
    _respond(monkeypatch, httpx.Response(200, json={"code": SUCCESS_CODE}))
    result = _gateway().send("+8801711111111", "body", CORRELATION)
    assert result.outcome is not Outcome.SENT


def test_a_non_2xx_status_is_unknown_not_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A transport problem is not an application rejection -- and it is
    # also not evidence the message was NOT sent.
    _respond(monkeypatch, httpx.Response(502))
    result = _gateway().send("+8801711111111", "body", CORRELATION)
    assert result.outcome is Outcome.UNKNOWN


def test_a_timeout_is_unknown_not_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The SMS may have been delivered and billed, and there is no
    # delivery report to ask [BR5.3].
    _respond(monkeypatch, httpx.TimeoutException("timed out"))
    result = _gateway().send("+8801711111111", "body", CORRELATION)
    assert result.outcome is Outcome.UNKNOWN


def test_code_1005_is_unknown_not_a_transient_error() -> None:
    assert outcome_for_code(1005) is Outcome.UNKNOWN


def test_balance_codes_are_budget_refused() -> None:
    # Retrying into an empty balance is the same mistake as retrying
    # into a cost ceiling.
    assert outcome_for_code(1006) is Outcome.BUDGET_REFUSED
    assert outcome_for_code(1007) is Outcome.BUDGET_REFUSED


def test_an_unrecognised_code_fails_rather_than_passing() -> None:
    # The published table is NOT closed, so an unknown code is a
    # failure of unknown class rather than evidence of completeness.
    assert outcome_for_code(9999) is Outcome.FAILED


def test_the_ip_whitelist_code_alerts() -> None:
    # 1032 is "IP not whitelisted": retrying from the same IP never
    # succeeds, and it looks like an auth failure.
    assert 1032 in ALERTING_CODES


def test_only_one_attempt_is_made(monkeypatch: pytest.MonkeyPatch) -> None:
    # Automatic retry double-charges and double-messages, and there is
    # no idempotency key to deduplicate against [BR5.3].
    seen = _respond(monkeypatch, httpx.TimeoutException("timed out"))
    _gateway().send("+8801711111111", "body", CORRELATION)
    assert len(seen) == 1


# ---------------------------------------------------------------------------
# HTTPS, ENFORCED IN CODE. [BR5.2]
# ---------------------------------------------------------------------------


def test_a_non_https_base_url_raises_at_construction() -> None:
    # Plain HTTP serves the same API with no redirect and no HSTS, so a
    # misconfigured endpoint ships the number AND the code in cleartext
    # and SUCCEEDS SILENTLY. Raising at construction fails the
    # deployment instead of the privacy guarantee.
    with pytest.raises(ValueError, match="https"):
        BulkSmsBdGateway(
            base_url="http://bulksmsbd.net/api/smsapi",
            api_key="k",
            sender_id="s",
        )


def test_an_https_base_url_constructs() -> None:
    assert BulkSmsBdGateway(
        base_url=BASE, api_key="k", sender_id="s"
    ).base_url.startswith("https://")


def test_no_tls_verification_toggle_is_exposed() -> None:
    import inspect

    parameters = set(inspect.signature(BulkSmsBdGateway.__init__).parameters)
    assert not parameters & {"verify", "verify_ssl", "insecure", "ssl_verify"}


# ---------------------------------------------------------------------------
# THE LOG MUST NOT LEAK. [BR6.2]
# ---------------------------------------------------------------------------


def test_the_error_message_is_never_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # error_message echoes the API key back in plaintext -- verified
    # live. This is a credential-leak path into the logs, not a
    # hypothetical one.
    _respond(
        monkeypatch,
        httpx.Response(200, json={"response_code": 1011, "error_message": LEAKY_ERROR}),
    )
    with caplog.at_level(logging.DEBUG):
        _gateway().send("+8801711111111", "body", CORRELATION)

    rendered = caplog.text + str([record.__dict__ for record in caplog.records])
    assert "SECRETKEY123" not in rendered
    assert LEAKY_ERROR not in rendered


def test_the_request_body_is_never_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # The gateway call carries the phone number and the code together.
    _respond(monkeypatch, httpx.Response(200, json={"response_code": 202}))
    with caplog.at_level(logging.DEBUG):
        _gateway().send("+8801711111111", "code is 123456", CORRELATION)

    rendered = caplog.text + str([record.__dict__ for record in caplog.records])
    assert "+8801711111111" not in rendered
    assert "123456" not in rendered


def test_the_log_carries_the_correlation_id(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _respond(monkeypatch, httpx.Response(200, json={"response_code": 202}))
    with caplog.at_level(logging.INFO):
        _gateway().send("+8801711111111", "body", CORRELATION)
    assert any(
        getattr(record, "correlation_id", None) == CORRELATION
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# THE NULL ADAPTER IS THE DEFAULT. [BR5.4]
# ---------------------------------------------------------------------------


def test_the_null_adapter_is_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ADAPTER_ENV, raising=False)
    assert isinstance(build_gateway(), NullGateway)


def test_a_misspelt_setting_yields_the_null_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Failing TOWARD NOT SENDING is the whole point: the alternative
    # spends real money and messages a real person.
    monkeypatch.setenv(ADAPTER_ENV, "bulksmbd")
    assert isinstance(build_gateway(), NullGateway)


def test_the_null_adapter_makes_no_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("the null adapter made a network call")

    monkeypatch.setattr(httpx, "post", explode)
    result = NullGateway().send("+8801711111111", "body", CORRELATION)
    assert result.outcome is Outcome.SENT


def test_the_real_adapter_requires_explicit_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ADAPTER_ENV, "bulksmsbd")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_BASE_URL", BASE)
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_API_KEY", "k")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_SENDER_ID", "s")
    assert isinstance(build_gateway(), BulkSmsBdGateway)


def test_a_partially_configured_real_adapter_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Refusing beats falling back: a silent fallback either spends
    # money unexpectedly or stops sending without anyone noticing.
    monkeypatch.setenv(ADAPTER_ENV, "bulksmsbd")
    monkeypatch.setenv("SHIKKHOKPLUS_SMS_BASE_URL", BASE)
    monkeypatch.delenv("SHIKKHOKPLUS_SMS_API_KEY", raising=False)
    monkeypatch.delenv("SHIKKHOKPLUS_SMS_SENDER_ID", raising=False)
    with pytest.raises(RuntimeError):
        build_gateway()


# ---------------------------------------------------------------------------
# ONE SEGMENT, APP HASH INCLUDED. [BR5.5]
# ---------------------------------------------------------------------------


def test_the_rendered_template_fits_one_gsm7_segment() -> None:
    body = render_otp_message("123456", "A" * APP_HASH_LENGTH)
    assert gsm7_length(body) <= GSM7_SEGMENT


def test_the_app_hash_is_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    # Easy to forget until the invoice arrives: exceeding one segment
    # silently doubles the per-OTP cost with no error and no signal.
    with_hash = render_otp_message("123456", "A" * APP_HASH_LENGTH)
    without = render_otp_message("123456", "")
    assert gsm7_length(with_hash) > gsm7_length(without)


def test_an_oversized_body_raises_rather_than_doubling_the_cost() -> None:
    import app.gateway.template as module

    long_template = "X" * 200 + " {code} {app_hash}"
    original = module.OTP_TEMPLATE
    try:
        module.OTP_TEMPLATE = long_template
        with pytest.raises(ValueError, match="segment"):
            render_otp_message("123456", "A" * APP_HASH_LENGTH)
    finally:
        module.OTP_TEMPLATE = original


def test_a_non_gsm7_character_is_rejected() -> None:
    # A character outside GSM-7 forces UCS-2 and a 70-character
    # segment, which is the other way the cost silently doubles.
    with pytest.raises(ValueError, match="GSM-7"):
        gsm7_length("আপনার কোড")


def test_the_extended_characters_cost_two_septets() -> None:
    # A naive len() passes on a body that actually needs two segments.
    assert gsm7_length("{") == 2
    assert gsm7_length("a") == 1


# ---------------------------------------------------------------------------
# The code -> taxonomy map. [contract-summary C.4.4]
#
# Separate from the outcome map because the two answer different
# questions: the outcome decides what to record, the class decides
# whether the caller may retry.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", [1001, 1003, 1012])
def test_request_errors_are_validation_errors(code: int) -> None:
    assert taxonomy_for_code(code) is ValidationError


@pytest.mark.parametrize("code", [1011, 1018, 1031, 1032])
def test_account_and_ip_errors_are_authorization_errors(code: int) -> None:
    assert taxonomy_for_code(code) is AuthorizationError


@pytest.mark.parametrize("code", [1006, 1007])
def test_balance_errors_are_conflicts_never_transient(code: int) -> None:
    # Retrying into an empty balance is the same error as retrying into
    # a cost ceiling, so it must not be a TransientError.
    assert taxonomy_for_code(code) is ConflictError
    assert not issubclass(taxonomy_for_code(code), TransientError)


@pytest.mark.parametrize("code", [1002, 1013, 1017, 1021])
def test_provisioning_errors_are_fatal(code: int) -> None:
    assert taxonomy_for_code(code) is FatalError


def test_an_unrecognised_code_is_fatal_not_transient() -> None:
    # The enumeration is known to be incomplete, so "unknown" must not
    # imply "safe to try again" on a boundary where a retry costs money.
    assert taxonomy_for_code(9999) is FatalError
    assert not issubclass(taxonomy_for_code(9999), TransientError)


def test_no_gateway_code_maps_to_a_transient_error() -> None:
    # There is no automatic retry at any layer [BR5.3], so a
    # TransientError here would be a standing invitation to add one.
    every_code = [
        202,
        1001,
        1002,
        1003,
        1005,
        1006,
        1007,
        1011,
        1012,
        1013,
        1017,
        1018,
        1021,
        1031,
        1032,
        9999,
    ]
    assert not any(
        issubclass(taxonomy_for_code(code), TransientError) for code in every_code
    )
