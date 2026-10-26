"""The log formatter keeps what the default one drops.

**Written against a real diagnosis that this cost.** A production log
line read ``sms send`` and nothing else, so whether an OTP had reached
a person was unanswerable from the logs: the outcome and the provider
code were attached through ``extra=`` and the default formatter prints
only the message.
"""

from __future__ import annotations

import logging

from app.logging_setup import StructuredFormatter


def _record(**extra: object) -> logging.LogRecord:
    """Build a record carrying the given structured fields.

    :param extra: Fields a call site would pass through ``extra=``
    :return: The record
    """
    record = logging.LogRecord(
        name="app.gateway.bulksmsbd",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="sms send",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_the_outcome_and_provider_code_are_printed() -> None:
    """The fields that answer "did it send" reach the output.

    :return: None
    """
    line = StructuredFormatter("%(message)s").format(
        _record(outcome="sent", provider_code=202, purpose="otp")
    )

    assert "outcome='sent'" in line
    assert "provider_code=202" in line


def test_a_failure_code_is_visible() -> None:
    """1032 is "IP not whitelisted" and never succeeds on retry.

    It must be distinguishable from a successful send in the log, which
    is the whole point: the gateway offers no delivery report, so this
    is the only record that exists.

    :return: None
    """
    line = StructuredFormatter("%(message)s").format(
        _record(outcome="failed", provider_code=1032)
    )

    assert "1032" in line
    assert "failed" in line


def test_a_record_with_no_extras_is_unchanged() -> None:
    """Most lines are uvicorn's and must not grow a trailing bracket.

    :return: None
    """
    line = StructuredFormatter("%(message)s").format(_record())

    assert line == "sms send"


def test_the_correlation_id_ties_a_line_to_a_request() -> None:
    """Without it a send cannot be matched to the request that caused it.

    :return: None
    """
    line = StructuredFormatter("%(message)s").format(_record(correlation_id="abc-123"))

    assert "correlation_id='abc-123'" in line


def test_no_message_body_is_printed_even_if_attached() -> None:
    """The formatter prints a fixed field list, never everything.

    **The field list is an allowlist and that is deliberate** [BR6.2].
    The request body carries the number and the code together, and the
    provider's ``error_message`` echoes the API key back in plaintext.
    A formatter that printed every attribute would put both in the log
    the first time somebody attached one.

    :return: None
    """
    line = StructuredFormatter("%(message)s").format(
        _record(outcome="sent", message_body="123456 is your code", api_key="SECRET")
    )

    assert "123456" not in line
    assert "SECRET" not in line
    assert "outcome='sent'" in line
