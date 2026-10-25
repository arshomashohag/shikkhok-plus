"""Correction is reachable through the real route [BR5.7, FR9.2].

**The mechanism was built and unreachable.** ``verify_claim`` and
``reject_claim`` have carried a ``correcting`` flag since the unit was
written, with the whole correction path behind it -- ``previous_decision``
capture, compensating ledger entries, the reversal of the prior decision.
Fifteen tests exercised it. Every one of them called the service function
directly.

No route passed the flag and no request schema carried it, so a teacher
revising a decided claim through the API always lost the row-lock race
guard and received a 409. The state diagram in ``functional-spec.md``
draws the correction transitions; FR9.2 makes every verification
correctable; and the API could not reach any of it.

**These assert the wiring, not the mechanism**, because the mechanism
already had fifteen passing tests and the wiring had none. A service
level test cannot distinguish "this works" from "this is reachable", and
the unit shipped the first without the second.
"""

from __future__ import annotations

import inspect

from app.api import fees
from app.schemas.fees import RejectionRequest, VerificationRequest


def test_the_request_schemas_carry_correcting() -> None:
    """Both decision schemas declare the flag, defaulting False [BR5.7].

    Asserted on the schema itself because ``extra="forbid"`` makes an
    undeclared field a 422 rather than a silently ignored key: the
    absence did not merely fail to reach the service, it actively
    refused the request that carried it.

    Defaulting ``False`` is the other half. An ordinary verification of
    an undecided claim must need no flag, or every caller would have to
    opt out of a correction they were not making.

    :return: None
    """
    assert "correcting" in VerificationRequest.model_fields
    assert VerificationRequest.model_fields["correcting"].default is False

    assert "correcting" in RejectionRequest.model_fields
    assert RejectionRequest.model_fields["correcting"].default is False


def test_both_routes_forward_correcting_to_the_service() -> None:
    """The handlers pass the flag rather than dropping it [FR9.2].

    The defect was a missing wire rather than a missing mechanism: the
    service took the parameter, the routes never supplied it, and the
    default ``False`` reached every call.

    Asserted against the handlers' own source. A behavioural test here
    would pass whether the route forwarded ``False`` or dropped the
    argument entirely, since both produce the same refusal -- which is
    exactly how this survived a green suite.

    :return: None
    """
    verify_source = inspect.getsource(fees.record_verification)
    assert "correcting=body.correcting" in verify_source

    reject_source = inspect.getsource(fees.record_rejection)
    assert "correcting=" in reject_source
