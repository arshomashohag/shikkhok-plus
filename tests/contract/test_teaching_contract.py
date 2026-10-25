"""D4's two schema-wide contract invariants [BR3.9, § 5.1].

**Both iterate the generated document rather than checking per
endpoint.** A per-endpoint test fails to cover the endpoint added
after everyone stopped thinking about it, which is the shape
``app/contract/privacy.py`` already establishes for the field-level
invariant.
"""

from __future__ import annotations

from typing import Any

from app.main import create_app

#: The two D4 writes § B.7 names, and no others. Generalising the
#: field would contradict a deliberate decision rather than extend
#: one: § B.7 says that stating the four writes explicitly is what
#: makes the rule reviewable.
EXPECTED_MUTATION_ID_BODIES: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/v1/sessions/{session_id}/attendance"),
        ("PUT", "/v1/sessions/{session_id}/topic"),
    }
)


def _document() -> dict[str, Any]:
    """Generate the OpenAPI document.

    :return: The document
    """
    document: dict[str, Any] = create_app().openapi()
    return document


def _resolve(document: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolve a local component reference.

    :param document: The whole document
    :param ref: A ``#/components/schemas/Name`` pointer
    :return: The referenced schema
    """
    name = ref.rsplit("/", 1)[-1]
    schema: dict[str, Any] = document["components"]["schemas"][name]
    return schema


def _body_properties(document: dict[str, Any], operation: dict[str, Any]) -> set[str]:
    """Collect every property name a request body can carry.

    Follows ``$ref`` one level, which is the shape FastAPI emits for a
    Pydantic model. A body with no schema contributes nothing.

    :param document: The whole document
    :param operation: One operation object
    :return: The property names
    """
    body = operation.get("requestBody")
    if not body:
        return set()

    names: set[str] = set()
    for media in body.get("content", {}).values():
        schema = media.get("schema", {})
        if "$ref" in schema:
            schema = _resolve(document, schema["$ref"])
        names |= set(schema.get("properties", {}))
    return names


def test_exactly_two_d4_request_bodies_carry_client_mutation_id() -> None:
    """§ B.7's four writes, of which these are D4's two.

    An EQUALITY over the whole document rather than a membership:
    a membership test passes the moment the field spreads to a third
    body, which is precisely what § B.7 forbids.

    **This asserts DECLARATION, which is only half the rule**, and the
    half it does not assert is the one that shipped broken: the topic
    body declared the field while the handler never forwarded it and
    ``write_topic`` had no parameter for it, so this test passed with
    one of the two paths implemented. The implementation half is
    ``tests/teaching/test_api.py``'s
    ``test_both_declared_mutation_id_paths_actually_replay``, which
    replays a real request per path. Both are kept: this one guards
    against the field spreading to a third body, which an
    implementation test cannot see.

    :return: None
    """
    document = _document()

    carrying = {
        (method.upper(), path)
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        if "client_mutation_id" in _body_properties(document, operation)
    }

    assert carrying == EXPECTED_MUTATION_ID_BODIES, (
        f"bodies carrying client_mutation_id: {sorted(carrying)}. "
        "§ B.7 names the writes that need it explicitly, and "
        "enumerating them is what makes the rule reviewable."
    )


def test_no_schema_anywhere_carries_a_queue_state_field() -> None:
    """The four queue states never reach the wire [BR3.9].

    The server cannot know whether an item is queued on a device it
    has never heard from, so whatever value it invented would be
    wrong for every device except the one that just called.

    Checked over the whole document rather than per endpoint, because
    the failure mode is a field added later by someone who did not
    read this rule.

    :return: None
    """
    document = _document()

    # **Property NAMES, not a substring of the rendered document.** A
    # raw `"queue_state" not in json.dumps(...)` matches the prose of
    # any docstring that explains the rule, so the first version of
    # this test failed against a schema that obeys it -- a check that
    # fires on its own documentation is a check nobody keeps.
    for schema_name, schema in document["components"]["schemas"].items():
        properties = set(schema.get("properties", {}))
        offending = properties & {
            "queue_state",
            "queueState",
            "queued",
            "conflicted",
        }
        assert offending == set(), (
            f"{schema_name} carries {sorted(offending)}: the four "
            "queue states are CLIENT-side vocabulary and the server "
            "cannot know them [BR3.9]"
        )


def test_the_marksheet_carries_no_per_student_collection() -> None:
    """The published marksheet has no array of student-shaped rows.

    **The mechanism is schema SHAPE, not filtering** [§ 4.1]. A
    filtered list is one forgotten predicate from a leak; an absent
    field is not, which is why this is asserted over the TYPE rather
    than over one response.

    :return: None
    """
    document = _document()
    published = document["components"]["schemas"]["PublishedMarksheetResponse"]

    arrays = {
        name
        for name, prop in published["properties"].items()
        if prop.get("type") == "array"
    }
    assert arrays == {"bands"}, (
        f"PublishedMarksheetResponse carries the collections {arrays}. "
        "The only one permitted is `bands`, which holds COUNTS rather "
        "than people [BR6.2]."
    )

    band = document["components"]["schemas"]["BandResponse"]
    assert set(band["properties"]) == {"low", "high", "count"}, (
        "a band carries something other than two bounds and a count: "
        "a band of one IS a named mark [BR6.3]"
    )


def test_the_suppressed_marksheet_is_a_distinct_shape() -> None:
    """A suppressed marksheet is not the published one with nulls.

    A rank of null beside an average of zero would read as a real
    result [BR6.4], so the client switches on ``published`` rather
    than inspecting whether a comparison field happens to be absent.

    :return: None
    """
    document = _document()
    suppressed = document["components"]["schemas"]["SuppressedMarksheetResponse"]

    assert set(suppressed["properties"]) == {
        "published",
        "viewer_marks",
        "reason",
    }
    for absent in ("average", "highest", "viewer_rank", "bands"):
        assert absent not in suppressed["properties"], (
            f"the suppressed marksheet carries {absent!r}: no "
            "comparison of any kind is published below the thresholds "
            "[BR6.4]"
        )
