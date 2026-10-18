"""The BulkSMSBD adapter. Every claim below was probed live.

**Success is ``response_code == 202`` and nothing else** [BR5.1]. An
application-level failure returns **HTTP 200** with the error in the body,
so ``raise_for_status()`` is worthless as a success check: a non-2xx
status means a transport problem -- proxy, DNS, a typo'd path -- and never
an application rejection.

The field is **``response_code``**, an integer, not ``code``. Named
explicitly because the most-installed Python client for this gateway
parses ``code`` and mocks ``{'code': 202}`` in its tests -- so its tests
pass against a fiction while the library would treat every real response,
success and failure alike, as unrecognised.

**HTTPS is enforced in code, not configuration** [BR5.2]. Plain HTTP
serves the same API with no redirect and no HSTS, so a misconfigured
``http://`` ships the phone number and the OTP in cleartext and
**succeeds silently** -- nothing fails, warns or logs. Under RC-1/RC-2/
RC-3 that is a privacy failure on children's-adjacent data, so the scheme
is not a configuration value and no TLS-verification toggle is exposed.

**``error_message`` echoes the API key back in plaintext** -- verified:
``"user id not found in this <key> key"``. It is never logged and never
stored [BR6.2]. The adapter logs ``(purpose, outcome, correlation_id)``
and the numeric code, and nothing else.
"""

from __future__ import annotations

import logging
from typing import Final
from urllib.parse import urlparse

import httpx

from app.errors import (
    AuthorizationError,
    ConflictError,
    FatalError,
    TaxonomyError,
    ValidationError,
)
from app.gateway.sms import Outcome, SendResult

__all__ = [
    "ALERTING_CODES",
    "BulkSmsBdGateway",
    "outcome_for_code",
    "taxonomy_for_code",
]

_log = logging.getLogger(__name__)

#: The only code that means the message was submitted.
SUCCESS_CODE: Final = 202

#: Internal error. **UNKNOWN, not FAILED**: the gateway offers no delivery
#: report and no message id, so the SMS may have been sent and billed.
INTERNAL_ERROR_CODE: Final = 1005

#: Balance exhausted. BUDGET_REFUSED, never a transient error -- retrying
#: into an empty balance is the same mistake as retrying into a ceiling.
_BUDGET_CODES: Final[frozenset[int]] = frozenset({1006, 1007})

#: The request or the number was wrong. No retry will fix it.
_VALIDATION_CODES: Final[frozenset[int]] = frozenset({1001, 1003, 1012})

#: Account or IP problem. Alerting: 1032 is "IP not whitelisted", and
#: retrying from the same IP never succeeds.
_AUTH_CODES: Final[frozenset[int]] = frozenset({1011, 1018, 1031, 1032})

#: Vendor provisioning failures.
_FATAL_CODES: Final[frozenset[int]] = frozenset(
    {1002, 1013, 1014, 1015, 1016, 1017, 1019, 1020, 1021}
)

#: Codes that must reach a human.
ALERTING_CODES: Final[frozenset[int]] = _AUTH_CODES | _FATAL_CODES

#: Default timeout. One attempt, so this is the whole budget.
DEFAULT_TIMEOUT: Final = 10.0


def outcome_for_code(code: int) -> Outcome:
    """Map a provider code onto an outcome.

    **The published table is not closed** -- three codes appear in
    community sources but not the vendor's own list -- so an unrecognised
    code is a failure of unknown class rather than evidence the
    enumeration is complete.

    :param code: The provider's ``response_code``
    :return: The outcome it maps to
    """
    if code == SUCCESS_CODE:
        return Outcome.SENT
    if code == INTERNAL_ERROR_CODE:
        return Outcome.UNKNOWN
    if code in _BUDGET_CODES:
        return Outcome.BUDGET_REFUSED
    return Outcome.FAILED


def taxonomy_for_code(code: int) -> type[TaxonomyError]:
    """Map a provider code onto the error class a caller would raise.

    Separate from :func:`outcome_for_code` because the two answer
    different questions: the outcome decides what to record, the class
    decides whether the caller may retry. Collapsing them would put a
    budget refusal and a validation failure in one bucket purely because
    both mean "not sent".

    An unrecognised code is :class:`~app.errors.FatalError` rather than
    :class:`~app.errors.TransientError`: the enumeration is known to be
    incomplete, so "unknown" must not imply "safe to try again" on a
    boundary where a retry costs money.

    :param code: The provider's ``response_code``
    :return: The taxonomy class for that code
    """
    if code in _VALIDATION_CODES:
        return ValidationError
    if code in _AUTH_CODES:
        return AuthorizationError
    if code in _BUDGET_CODES:
        # ConflictError, never TransientError: retrying into an empty
        # balance is the same mistake as retrying into a cost ceiling.
        return ConflictError
    return FatalError


class BulkSmsBdGateway:
    """The real adapter. Constructing one requires an https base URL.

    :ivar base_url: The gateway endpoint
    :ivar sender_id: The registered sender id
    :ivar timeout: How long one attempt may take
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        sender_id: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Build the adapter, refusing a non-https endpoint.

        :param base_url: The gateway endpoint
        :param api_key: The account's API key, from the environment
        :param sender_id: The registered sender id
        :param timeout: How long one attempt may take
        :raises ValueError: The scheme is not https
        """
        if urlparse(base_url).scheme != "https":
            # Raised at CONSTRUCTION rather than at send time, so a
            # misconfigured deployment fails at startup instead of
            # shipping the first OTP in cleartext.
            raise ValueError(
                "the SMS gateway base URL must be https: plain HTTP serves "
                "the same API with no redirect, so a misconfigured "
                "endpoint leaks the number and the code silently [BR5.2]"
            )
        self.base_url = base_url
        self._api_key = api_key
        self.sender_id = sender_id
        self.timeout = timeout

    def send(self, number: str, message: str, correlation_id: str) -> SendResult:
        """Attempt one send. **Once**, with no retry at any layer.

        :param number: The destination number
        :param message: The rendered body
        :param correlation_id: Ties the log line to a request
        :return: The outcome
        """
        try:
            response = httpx.post(
                self.base_url,
                data={
                    "api_key": self._api_key,
                    "senderid": self.sender_id,
                    "number": number,
                    "message": message,
                },
                timeout=self.timeout,
            )
        except httpx.TimeoutException:
            # UNKNOWN, never FAILED: the message may have been delivered
            # and billed, and there is no delivery report to ask [BR5.3].
            self._log(Outcome.UNKNOWN, None, correlation_id)
            return SendResult(outcome=Outcome.UNKNOWN)
        except httpx.HTTPError:
            # A transport problem is not an application rejection, and
            # it is also not evidence the message was NOT sent.
            self._log(Outcome.UNKNOWN, None, correlation_id)
            return SendResult(outcome=Outcome.UNKNOWN)

        if response.status_code >= 300:
            self._log(Outcome.UNKNOWN, None, correlation_id)
            return SendResult(outcome=Outcome.UNKNOWN)

        try:
            body = response.json()
        except ValueError:
            self._log(Outcome.FAILED, None, correlation_id)
            return SendResult(outcome=Outcome.FAILED)

        # `response_code`, NOT `code`. See the module docstring.
        raw = body.get("response_code")
        if not isinstance(raw, int):
            self._log(Outcome.FAILED, None, correlation_id)
            return SendResult(outcome=Outcome.FAILED)

        outcome = outcome_for_code(raw)
        self._log(outcome, raw, correlation_id)
        return SendResult(outcome=outcome, provider_code=raw)

    @staticmethod
    def _log(outcome: Outcome, code: int | None, correlation_id: str) -> None:
        """Log one send, carrying nothing that could leak.

        **Never the request body** -- it carries the number and the code
        together -- and **never ``error_message``**, which echoes the API
        key back in plaintext [BR6.2].

        :param outcome: What happened
        :param code: The provider code, or None
        :param correlation_id: Ties the line to a request
        :return: None
        """
        level = (
            logging.ERROR
            if code is not None and code in ALERTING_CODES
            else logging.INFO
        )
        _log.log(
            level,
            "sms send",
            extra={
                "purpose": "otp",
                "outcome": outcome.value,
                "provider_code": code,
                "correlation_id": correlation_id,
            },
        )
