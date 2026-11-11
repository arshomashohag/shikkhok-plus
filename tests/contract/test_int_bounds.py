"""Every integer a caller sends has an upper bound [SEC-3].

``total_marks`` had a floor and no ceiling. A caller sending three
billion overflowed the ``Integer`` column at the INSERT, the
``DataError`` went unmapped, and the logged traceback carried the
statement's bound parameters. ``DataError`` is now a 400 and the engine
hides parameters, but the schema is where an absurd number should stop:
this gate makes a missing ceiling a CI failure rather than a review
catch.

It walks what the application actually accepts -- every route's body
model, the models nested inside it, and every integer query or path
parameter -- through :func:`app.contract.routes._api_routes`, the one
enumeration that sees included routers.
"""

from __future__ import annotations

import typing
from collections.abc import Iterator
from typing import Final

import annotated_types
from fastapi import FastAPI
from pydantic import BaseModel, Field
from pydantic.fields import FieldInfo

from app.contract.routes import _api_routes
from app.main import app as real_app

#: Integer parameters that may stay unbounded, each with its reason.
#: Keyed by ``(path, parameter)``; a stale entry fails the gate below.
ALLOWED_UNBOUNDED: Final[dict[tuple[str, str], str]] = {
    ("/v1/analytics/collections", "months"): (
        "clamped to 1..24 by clamp_months before any query uses it"
    ),
    ("/v1/enrollments/{enrollment_id}/fees", "months"): (
        "clamped to 1..24 by clamp_months before any query uses it"
    ),
}


def _leaves(annotation: object) -> Iterator[object]:
    """Yield the concrete types inside an annotation.

    :param annotation: A field's annotation
    :return: Each type inside unions, containers and ``Annotated``
    """
    origin = typing.get_origin(annotation)
    if origin is typing.Annotated:
        yield from _leaves(typing.get_args(annotation)[0])
        return
    if origin is None:
        yield annotation
        return
    for argument in typing.get_args(annotation):
        yield from _leaves(argument)


def _is_int(annotation: object) -> bool:
    """Say whether an annotation accepts a plain integer.

    ``bool`` is a subclass of ``int`` and is not a number a caller can
    overflow, so it does not count.

    :param annotation: A field's annotation
    :return: True when ``int`` is one of its concrete types
    """
    return any(leaf is int for leaf in _leaves(annotation))


def _bounded(field: FieldInfo) -> bool:
    """Say whether a field declares an upper bound.

    :param field: The field
    :return: True when ``le`` or ``lt`` is set
    """
    return any(
        isinstance(meta, (annotated_types.Le, annotated_types.Lt))
        for meta in field.metadata
    )


def _models(annotation: object) -> Iterator[type[BaseModel]]:
    """Yield the Pydantic models inside an annotation.

    :param annotation: A field's annotation
    :return: Each model type found
    """
    for leaf in _leaves(annotation):
        if isinstance(leaf, type) and issubclass(leaf, BaseModel):
            yield leaf


def unbounded_model_fields(roots: list[type[BaseModel]]) -> list[str]:
    """List every unbounded integer field reachable from some models.

    :param roots: The models to start from
    :return: ``module.Model.field`` per offender
    """
    seen: set[type[BaseModel]] = set()
    found: list[str] = []
    pending = list(roots)
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        for name, field in model.model_fields.items():
            if _is_int(field.annotation) and not _bounded(field):
                found.append(f"{model.__module__}.{model.__qualname__}.{name}")
            pending.extend(_models(field.annotation))
    return sorted(found)


def _body_models(app: FastAPI) -> list[type[BaseModel]]:
    """Collect every request body model the application accepts.

    :param app: The application
    :return: The body models
    """
    models: list[type[BaseModel]] = []
    for route in _api_routes(app):
        for param in route.dependant.body_params:
            models.extend(_models(param.field_info.annotation))
    return models


def _unbounded_parameters(app: FastAPI) -> set[tuple[str, str]]:
    """Collect every unbounded integer query or path parameter.

    :param app: The application
    :return: ``(path, parameter)`` per offender
    """
    found: set[tuple[str, str]] = set()
    for route in _api_routes(app):
        pending = [route.dependant]
        while pending:
            dependant = pending.pop()
            for param in (*dependant.query_params, *dependant.path_params):
                info = param.field_info
                if _is_int(info.annotation) and not _bounded(info):
                    found.add((route.path, param.name))
            pending.extend(dependant.dependencies)
    return found


def test_every_request_body_integer_has_an_upper_bound() -> None:
    """No body accepts an integer the database cannot hold.

    :return: None
    """
    roots = _body_models(real_app)
    assert roots, "no body models found: the walk is vacuous"

    assert unbounded_model_fields(roots) == [], (
        "these request fields accept any integer; give each an le= bound"
    )


def test_every_integer_parameter_is_bounded_or_allowlisted() -> None:
    """Query and path integers are bounded, or clamped for a stated reason.

    :return: None
    """
    unbounded = _unbounded_parameters(real_app)

    assert unbounded - ALLOWED_UNBOUNDED.keys() == set()
    # A stale allowance is a claim nothing checks any more.
    assert ALLOWED_UNBOUNDED.keys() - unbounded == set()


class _Inner(BaseModel):
    """A nested model with one unbounded integer.

    :ivar count: Unbounded
    """

    count: int


class _Leaky(BaseModel):
    """A body with each shape the walk must catch.

    :ivar bounded: Has a ceiling, so is fine
    :ivar plain: No ceiling
    :ivar optional: No ceiling, behind a union
    :ivar flag: A bool, which is not counted
    :ivar nested: Reaches an unbounded integer one level down
    """

    bounded: int = Field(ge=0, le=10)
    plain: int
    optional: int | None = None
    flag: bool = False
    nested: list[_Inner] = Field(default_factory=list)


def test_the_walk_fires_on_each_unbounded_shape() -> None:
    """Guards the gate itself: a fixture with known offenders is caught.

    :return: None
    """
    assert unbounded_model_fields([_Leaky]) == sorted(
        [
            f"{__name__}._Inner.count",
            f"{__name__}._Leaky.optional",
            f"{__name__}._Leaky.plain",
        ]
    )
