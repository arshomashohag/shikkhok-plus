"""Where a view's money column comes from, read from the view's own rule.

``information_schema`` reports a view column built by ``CASE`` as an
unconstrained ``numeric``: PostgreSQL drops the type modifier through a
``CASE``. So a view's money column cannot be held to NUMERIC(12,2) by its
reported type. It is held to its **source** instead: the parsed rule
PostgreSQL stores for the view (``pg_rewrite.ev_action``) names, for each
output column, the exact expression and every column it reads.

**Only a pass-through is accepted**, and anything else fails closed:

* a plain column reference;
* a ``CASE`` with no test argument whose every result, and whose ``ELSE``,
  is a plain column reference or a NULL constant -- the shape a view uses
  to show a fee only when the owner chose to.

Each referenced column must be a NUMERIC(12,2) column of a table, or a
column of another view that passes the same rule. Arithmetic, a cast, a
function, an aggregate or a constant amount is refused, because each can
produce a value of a precision no table column holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import sqlalchemy as sa
from sqlalchemy.orm import Session

__all__ = [
    "Node",
    "money_source_offence",
    "parse_node_tree",
    "pass_through_vars",
]

#: A parsed node: ``{NAME :field value ...}`` as a dict carrying its name
#: under ``"_node"``, a list as a list, and every atom as its text.
Node = dict[str, object] | list[object] | str | None

#: The only type a table column a view's money column reads may have.
MONEY_SOURCE_TYPE: Final[str] = "numeric(12,2)"

#: ``RangeTblEntry.rtekind`` for a plain relation.
_RTE_RELATION: Final[str] = "0"

#: How deep a view may read another view before the walk gives up.
_MAX_DEPTH: Final[int] = 8

_DELIMITERS: Final[frozenset[str]] = frozenset("(){}")


def _tokens(text: str) -> list[tuple[str, str]]:
    """Split a node tree into its tokens.

    Delimiters stand alone; a double-quoted string keeps its spaces; a
    backslash makes the next character part of the atom, as PostgreSQL's
    ``outToken`` escapes it.

    :param text: ``pg_node_tree`` text
    :return: ``(kind, text)`` pairs, the kind ``delim``, ``atom`` or ``str``
    """
    tokens: list[tuple[str, str]] = []
    i, size = 0, len(text)
    while i < size:
        char = text[i]
        if char.isspace():
            i += 1
            continue
        if char in _DELIMITERS:
            tokens.append(("delim", char))
            i += 1
            continue
        atom: list[str] = []
        quoted = char == '"'
        if quoted:
            i += 1
        while i < size:
            char = text[i]
            if char == "\\" and i + 1 < size:
                atom.append(text[i + 1])
                i += 2
                continue
            if quoted and char == '"':
                i += 1
                break
            if not quoted and (char.isspace() or char in _DELIMITERS):
                break
            atom.append(char)
            i += 1
        tokens.append(("str" if quoted else "atom", "".join(atom)))
    return tokens


def parse_node_tree(text: str) -> Node:
    """Parse ``pg_node_tree`` text into dicts, lists and atoms.

    A field whose value spans several tokens, such as a constant's
    ``:constvalue 4 [ 0 0 0 0 ]``, is kept as the list of those tokens.

    :param text: The text, such as ``pg_rewrite.ev_action::text``
    :return: The parsed tree
    :raises ValueError: If the text is not a well-formed node tree
    """
    tokens = _tokens(text)
    position = 0

    def is_key(index: int) -> bool:
        kind, token = tokens[index]
        return kind == "atom" and token.startswith(":")

    def ends_field(index: int) -> bool:
        return is_key(index) or tokens[index] == ("delim", "}")

    def value() -> Node:
        nonlocal position
        kind, lexeme = tokens[position]
        position += 1
        if kind != "delim":
            return None if (kind, lexeme) == ("atom", "<>") else lexeme
        if lexeme == "(":
            items: list[object] = []
            while tokens[position] != ("delim", ")"):
                items.append(value())
            position += 1
            return items
        if lexeme == "{":
            node: dict[str, object] = {"_node": tokens[position][1]}
            position += 1
            while tokens[position] != ("delim", "}"):
                if not is_key(position):
                    raise ValueError(f"expected a field, got {tokens[position]!r}")
                key = tokens[position][1][1:]
                position += 1
                parts: list[object] = []
                while not ends_field(position):
                    parts.append(value())
                node[key] = parts[0] if len(parts) == 1 else (parts or None)
            position += 1
            return node
        raise ValueError(f"unbalanced {lexeme!r}")

    tree = value()
    if position != len(tokens):
        raise ValueError("trailing tokens after the node tree")
    return tree


def _is(node: object, name: str) -> bool:
    """Report whether a parsed value is a node of one kind.

    :param node: A parsed value
    :param name: The node name, such as ``VAR``
    :return: True when it is that node
    """
    return isinstance(node, dict) and node.get("_node") == name


def _is_null_constant(node: object) -> bool:
    """Report whether a parsed value is a NULL constant.

    :param node: A parsed value
    :return: True for ``{CONST ... :constisnull true ...}``
    """
    return _is(node, "CONST") and node.get("constisnull") == "true"  # type: ignore[union-attr]


def pass_through_vars(expr: object) -> list[dict[str, object]] | None:
    """Return the column references a pass-through expression returns.

    :param expr: A target entry's parsed ``:expr``
    :return: Every ``VAR`` the expression can return, or None when the
        expression is anything but a plain reference or a ``CASE`` whose
        every outcome is a plain reference or NULL
    """
    if _is(expr, "VAR"):
        assert isinstance(expr, dict)
        return [expr] if expr.get("varlevelsup") == "0" else None
    if not _is(expr, "CASEEXPR"):
        return None
    assert isinstance(expr, dict)
    if expr.get("arg") is not None:
        return None
    whens = expr.get("args")
    if not isinstance(whens, list) or not whens:
        return None
    outcomes = [when.get("result") if _is(when, "CASEWHEN") else when for when in whens]  # type: ignore[union-attr]
    outcomes.append(expr.get("defresult"))
    found: list[dict[str, object]] = []
    for outcome in outcomes:
        if outcome is None or _is_null_constant(outcome):
            continue
        if not _is(outcome, "VAR"):
            return None
        assert isinstance(outcome, dict)
        if outcome.get("varlevelsup") != "0":
            return None
        found.append(outcome)
    return found or None


@dataclass(frozen=True, slots=True)
class _Column:
    """One column a view reads.

    :ivar relid: The relation's oid, as text
    :ivar attnum: The column's number, as text
    """

    relid: str
    attnum: str


def _sources(session: Session, view: str, column: str) -> list[_Column] | str:
    """Resolve the columns one view column passes through.

    :param session: The session to read the catalogue through
    :param view: The view, in ``public``
    :param column: The output column
    :return: The source columns, or why the column is refused
    """
    text = session.execute(
        sa.text(
            "SELECT r.ev_action::text FROM pg_rewrite r "
            "JOIN pg_class c ON c.oid = r.ev_class "
            "WHERE c.oid = to_regclass(:v) AND r.rulename = '_RETURN'"
        ),
        {"v": view},
    ).scalar_one_or_none()
    if text is None:
        return f"{view} has no view rule"
    tree = parse_node_tree(text)
    query = tree[0] if isinstance(tree, list) and tree else None
    if not _is(query, "QUERY"):
        return f"{view}: the rule is not one query"
    assert isinstance(query, dict)
    entries = [
        entry
        for entry in query.get("targetList") or []  # type: ignore[attr-defined]
        if _is(entry, "TARGETENTRY")
        and entry.get("resname") == column
        and entry.get("resjunk") == "false"
    ]
    if len(entries) != 1:
        return f"{view}.{column}: not exactly one output column of that name"
    references = pass_through_vars(entries[0].get("expr"))
    if references is None:
        return f"{view}.{column}: computed, not passed through from a column"
    rtable = query.get("rtable") or []
    found: list[_Column] = []
    for reference in references:
        index = int(str(reference["varno"])) - 1
        rte = rtable[index] if 0 <= index < len(rtable) else None  # type: ignore[arg-type]
        if not _is(rte, "RANGETBLENTRY") or rte.get("rtekind") != _RTE_RELATION:  # type: ignore[union-attr]
            return f"{view}.{column}: reads through a join or subquery, not a relation"
        found.append(_Column(str(rte["relid"]), str(reference["varattno"])))  # type: ignore[index]
    return found


def money_source_offence(
    session: Session, view: str, column: str, *, depth: int = 0
) -> str | None:
    """Explain why a view's money column is not a NUMERIC(12,2) pass-through.

    Each source is cross-checked against ``pg_depend``, so a misread rule
    cannot name a column the view does not in fact depend on.

    :param session: The session to read the catalogue through
    :param view: The view, in ``public``
    :param column: Its money column
    :param depth: How many views deep this call already is
    :return: None when every source is a NUMERIC(12,2) table column, or
        a view column passing the same rule; otherwise the reason
    """
    if depth > _MAX_DEPTH:
        return f"{view}.{column}: views nest deeper than {_MAX_DEPTH}"
    sources = _sources(session, view, column)
    if isinstance(sources, str):
        return sources
    for source in sources:
        row = session.execute(
            sa.text(
                "SELECT c.relname, c.relkind::text, a.attname, "
                "format_type(a.atttypid, a.atttypmod), "
                "EXISTS (SELECT 1 FROM pg_rewrite r JOIN pg_depend d "
                "  ON d.classid = 'pg_rewrite'::regclass AND d.objid = r.oid "
                "  WHERE r.ev_class = to_regclass(:v) "
                "  AND d.refclassid = 'pg_class'::regclass "
                "  AND d.refobjid = c.oid AND d.refobjsubid = a.attnum) "
                "FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid "
                "WHERE c.oid = CAST(:relid AS oid) AND a.attnum = CAST(:att AS int)"
            ),
            {"v": view, "relid": source.relid, "att": source.attnum},
        ).one_or_none()
        if row is None:
            return f"{view}.{column}: its source column does not exist"
        relname, relkind, attname, type_name, depended = row
        if not depended:
            return f"{view}.{column}: pg_depend does not confirm {relname}.{attname}"
        if relkind == "v":
            inner = money_source_offence(session, relname, attname, depth=depth + 1)
            if inner is not None:
                return f"{view}.{column} <- {inner}"
        elif relkind != "r":
            return f"{view}.{column}: reads {relname}, which is not a table"
        elif type_name != MONEY_SOURCE_TYPE:
            return f"{view}.{column}: reads {relname}.{attname}, a {type_name}"
    return None
