"""Resolve a callable's return annotation to a lens type.

**One function, two callers.** The route-enumeration gate uses it to decide
whether a route resolves a lens; the schema-wide privacy gate uses it to
decide which routes are teacher-facing. A second implementation would
almost certainly be the naive ``issubclass`` NFR14.7 exists to forbid, so
there is deliberately only one.

Three annotation shapes defeat a bare ``issubclass``, and none is exotic
here:

* **String annotations.** ``from __future__ import annotations`` makes every
  annotation a string, and this project's Ruff configuration selects ``UP``,
  which encourages that import. This is the expected shape.
* **Unions.** ``TeacherLens | GuardianLens`` is the natural annotation for
  the dual-lens account. A union counts only when *every* member qualifies,
  or the check admits a dependency that sometimes returns something else.
* **``Annotated`` and generic aliases**, which wrap the type the check needs.

A resolution failure raises. It is never swallowed: the real damage is the
implementer who catches the error and returns a default, which makes the
gate pass universally while authorizing nothing.
"""

from __future__ import annotations

import types
import typing
from collections.abc import Callable
from typing import Annotated, Any, Union, get_args, get_origin

from app.authz.lenses import Lens

__all__ = ["AnnotationResolutionError", "resolve_lens_type"]


class AnnotationResolutionError(Exception):
    """A return annotation could not be resolved to a type.

    Raised rather than swallowed so the build fails naming the offending
    callable. A resolver that returned a default on failure would let every
    route pass the lens check.
    """


def _unwrap(annotation: object) -> object:
    """Strip ``Annotated`` wrappers and generic aliases down to a type.

    :param annotation: The annotation to unwrap
    :return: The underlying type, or the annotation unchanged
    """
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    return annotation


def _is_union(annotation: object) -> bool:
    """Report whether an annotation is a union.

    Both spellings count: ``X | Y`` produces :class:`types.UnionType` while
    ``Union[X, Y]`` produces a ``typing`` special form.

    :param annotation: The annotation to inspect
    :return: True if the annotation is a union
    """
    origin = get_origin(annotation)
    return origin is types.UnionType or origin is Union


def _is_lens(annotation: object) -> bool:
    """Report whether an annotation is a lens type.

    :param annotation: The annotation to inspect
    :return: True if the annotation is :class:`Lens` or a subclass
    """
    return isinstance(annotation, type) and issubclass(annotation, Lens)


def resolve_lens_type(obj: Callable[..., Any]) -> type[Lens] | None:
    """Resolve a callable's return annotation to a lens type.

    :param obj: The callable whose return annotation is inspected
    :return: The lens type, or None when the annotation is not a lens
    :raises AnnotationResolutionError: The annotation cannot be resolved
    """
    try:
        hints = typing.get_type_hints(obj, include_extras=True)
    except Exception as error:
        raise AnnotationResolutionError(
            f"cannot resolve the return annotation of "
            f"{getattr(obj, '__qualname__', obj)!r}: {error}"
        ) from error

    if "return" not in hints:
        return None

    annotation = _unwrap(hints["return"])

    if _is_union(annotation):
        members = [_unwrap(member) for member in get_args(annotation)]
        if members and all(_is_lens(member) for member in members):
            return typing.cast("type[Lens]", members[0])
        return None

    if _is_lens(annotation):
        return typing.cast("type[Lens]", annotation)
    return None
