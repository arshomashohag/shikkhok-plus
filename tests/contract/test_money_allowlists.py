"""Step 10: the allowlists exempt one thing, not the check.

**An allowlist and a disabled gate are indistinguishable from a green
build.** Both make the failure go away; only one still catches the next
money column that arrives typed wrongly. These tests are what tells them
apart, and they are the reason BR3.3 could be satisfied by deleting a
token from the list instead -- which would turn the build green while
silently retiring the check on every genuine fee column in U7 and U8.

Both gates are exercised with an **unlisted** money-named field of the
wrong type, which must still be reported.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import create_model

from app.contract.money_names import (
    MONEY_NAME_TOKENS,
    NON_MONEY_COLUMNS,
    NON_MONEY_FIELDS,
    is_money_name,
)
from app.contract.money_schema import money_schema_violations


def _app_with(name: str, **fields: type) -> FastAPI:
    """Build a one-route app exposing a schema generated under ``name``.

    The model is **created dynamically** so the component name in the
    generated document is the one passed here. Renaming a class after
    definition does not work: Pydantic resolves the component name from
    the class at definition time, so the document would carry the
    placeholder name and the allowlist -- which is keyed on the real
    schema name -- would never match.

    :param name: The component name the schema is generated under
    :param fields: Field names mapped to their annotations
    :return: The application
    """
    model = create_model(name, **{key: (value, ...) for key, value in fields.items()})
    app = FastAPI()

    @app.get("/probe", response_model=model)
    def _probe() -> object:  # pragma: no cover - never called
        raise NotImplementedError

    return app


def test_the_allowlisted_field_is_exempt() -> None:
    """``BatchResponse.fee_due_day`` passes once allowlisted.

    :return: None
    """
    violations = money_schema_violations(_app_with("BatchResponse", fee_due_day=int))

    assert violations == []


def test_an_unlisted_money_named_integer_is_still_reported() -> None:
    """The gate still fires on anything not explicitly exempted.

    **This is the test that distinguishes the allowlist from having
    deleted the tokens.** With ``fee`` removed from the vocabulary this
    would pass while reporting nothing.

    :return: None
    """
    violations = money_schema_violations(_app_with("BatchResponse", fee_total=int))

    assert [v.field for v in violations] == ["fee_total"]
    assert violations[0].kind == "numeric-money"


def test_the_exemption_is_keyed_on_schema_and_field_together() -> None:
    """The same field name in a different schema is NOT exempt.

    An exemption that keyed on the field name alone would silently
    excuse ``fee_due_day`` everywhere it ever appeared, including on a
    schema nobody reasoned about.

    :return: None
    """
    violations = money_schema_violations(_app_with("SomeOtherSchema", fee_due_day=int))

    assert [v.field for v in violations] == ["fee_due_day"]


def test_passing_an_empty_allowlist_restores_the_false_positive() -> None:
    """With no exemptions the gate reports the known false positive.

    This pins that the allowlist is doing the work, rather than the
    field having stopped matching for some unrelated reason.

    :return: None
    """
    violations = money_schema_violations(
        _app_with("BatchResponse", fee_due_day=int), exempt={}
    )

    assert [v.field for v in violations] == ["fee_due_day"]


def test_every_allowlist_entry_actually_matches_a_money_token() -> None:
    """A stale entry exempting something that never matched is removed.

    An entry that does not match any token exempts nothing and is pure
    misinformation to the next reader.

    :return: None
    """
    for _, column in NON_MONEY_COLUMNS:
        assert is_money_name(column), f"{column} matches no money token"
    for _, field in NON_MONEY_FIELDS:
        assert is_money_name(field), f"{field} matches no money token"


def test_both_gates_read_the_same_token_list() -> None:
    """The database gate imports the shared vocabulary, not a copy.

    The two lists were independent before U4, so an entry added to one
    protected only that surface.

    :return: None
    """
    import tests.db.test_governance as governance

    assert governance.is_money_name is is_money_name
    assert "fee" in MONEY_NAME_TOKENS
    assert "due" in MONEY_NAME_TOKENS


def test_a_nullable_money_field_typed_as_a_number_is_caught() -> None:
    """The hole U4 was the first Unit able to expose.

    A nullable field emits ``{"anyOf": [{"type": "number"}, {"type":
    "null"}]}`` with no top-level ``type``, so a check reading
    ``node["type"]`` sees nothing. U3 carried no money at all, and this
    project's first real money column -- ``fee_amount`` -- is **nullable
    by design**, since null means inherit while zero is a waiver. The one
    shape the project uses for money was the one the gate could not see.

    :return: None
    """
    violations = money_schema_violations(
        _app_with("LeakyResponse", fee_amount=float | None), exempt={}
    )

    assert [v.kind for v in violations] == ["numeric-money"]


def test_a_nullable_money_field_typed_as_a_bare_string_is_caught() -> None:
    """The same wrapper hides the unconstrained-string case too.

    :return: None
    """
    violations = money_schema_violations(
        _app_with("LeakyResponse", fee_amount=str | None), exempt={}
    )

    assert [v.kind for v in violations] == ["unconstrained-money"]


def test_the_real_application_needs_the_allowlist() -> None:
    """The allowlist is load-bearing, not decorative.

    Pins BR3.3's prediction against the built application: without the
    exemptions the gate reports only the two date-and-day fields that
    match a money token while carrying no amount, and every real money
    property passes either way.

    ``due_date`` joined ``fee_due_day`` at D3 [BR2.2]. Both are the same
    false positive in two shapes -- an integer day-of-month and a
    computed date -- and each is exempted by its own
    ``(schema, field)`` pair so an exemption can never widen beyond the
    property it was reasoned about.

    :return: None
    """
    from app.main import create_app

    app = create_app()

    assert money_schema_violations(app) == []

    without = money_schema_violations(app, exempt={})
    assert {v.field for v in without} == {"fee_due_day", "due_date"}


def test_a_list_of_money_named_numbers_is_caught() -> None:
    """A COLLECTION of money is money.

    ``fee_amounts: list[float]`` emits ``{"type": "array", "items":
    {"type": "number"}}``, so a check reading only the outer type sees
    ``array`` and reports nothing -- while every element is an IEEE 754
    double on the client. U7's ledger is a list of amounts, so this is
    the next Unit's shape rather than a hypothetical one.

    :return: None
    """
    violations = money_schema_violations(
        _app_with("LedgerResponse", fee_amounts=list[float]), exempt={}
    )

    assert [(v.field, v.kind) for v in violations] == [("fee_amounts", "numeric-money")]


def test_a_dict_of_money_named_numbers_is_caught() -> None:
    """The same hole through ``additionalProperties``.

    :return: None
    """
    violations = money_schema_violations(
        _app_with("TotalsResponse", fee_totals=dict[str, float]), exempt={}
    )

    assert [(v.field, v.kind) for v in violations] == [("fee_totals", "numeric-money")]


def test_a_list_of_bare_money_strings_is_caught() -> None:
    """An unconstrained string inside a collection escapes the same way.

    :return: None
    """
    violations = money_schema_violations(
        _app_with("LedgerResponse", fee_amounts=list[str]), exempt={}
    )

    assert [v.kind for v in violations] == ["unconstrained-money"]


def test_a_list_of_non_money_strings_is_not_reported() -> None:
    """Guards the fix against over-reaching.

    ``subjects: list[str]`` is already on BatchCreateRequest and
    BatchResponse. A fix that flagged every string array would fail the
    real application, and the cheapest repair would be deleting the
    check.

    :return: None
    """
    violations = money_schema_violations(
        _app_with("BatchResponse", subjects=list[str]), exempt={}
    )

    assert violations == []
