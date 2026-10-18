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
