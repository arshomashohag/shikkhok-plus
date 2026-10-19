"""Tests for return-annotation resolution to a lens type.

Written before the implementation [NFR14.7]: the correct output is knowable
from the requirement, and a wrong answer is an authorization error that
passes silently, so the team's ordering predicate puts the test first.

The damage this guards against is not the false negative. It is the
implementer who hits a ``TypeError``, wraps the call in
``except TypeError: return True``, and makes the whole route-lens check pass
universally while authorizing nothing.
"""

from __future__ import annotations

from typing import Annotated

import pytest

from app.authz.annotations import AnnotationResolutionError, resolve_lens_type
from app.authz.lenses import GuardianLens, Lens, StudentLens, TeacherLens


def _teacher() -> TeacherLens:
    """Return a teacher lens.

    :return: A teacher lens
    """
    raise NotImplementedError


def _union_all_lenses() -> TeacherLens | GuardianLens:
    """Return either lens the dual-lens account may resolve to.

    :return: A teacher or guardian lens
    """
    raise NotImplementedError


def _union_with_none() -> TeacherLens | None:
    """Return a teacher lens or nothing.

    :return: A teacher lens, or None
    """
    raise NotImplementedError


def _annotated() -> Annotated[TeacherLens, "dependency metadata"]:
    """Return a teacher lens behind an Annotated wrapper.

    :return: A teacher lens
    """
    raise NotImplementedError


def _not_a_lens() -> str:
    """Return something that is not a lens.

    :return: A string
    """
    raise NotImplementedError


def _unannotated():  # type: ignore[no-untyped-def]
    """Return a value with no declared type."""
    raise NotImplementedError


def _base_lens() -> Lens:
    """Return the lens base type itself.

    :return: A lens
    """
    raise NotImplementedError


def _student() -> StudentLens:
    """Return a student lens.

    :return: A student lens
    """
    raise NotImplementedError


def test_plain_annotation_resolves() -> None:
    """A direct subtype annotation resolves to that subtype.

    :return: None
    """
    assert resolve_lens_type(_teacher) is TeacherLens


def test_string_annotation_resolves() -> None:
    """A string annotation resolves rather than raising.

    This module declares ``from __future__ import annotations``, so every
    annotation above is a string at runtime. The project's Ruff config
    selects ``UP``, which encourages that import, so this is the expected
    shape rather than an edge case -- and a bare ``issubclass`` raises on it.

    :return: None
    """
    assert isinstance(_teacher.__annotations__["return"], str)
    assert resolve_lens_type(_teacher) is TeacherLens


def test_union_of_lenses_resolves() -> None:
    """A union resolves when every member is a lens subtype.

    :return: None
    """
    assert resolve_lens_type(_union_all_lenses) is not None


def test_union_with_non_lens_member_does_not_resolve() -> None:
    """A union does not resolve unless EVERY member qualifies.

    ``TeacherLens | None`` means the dependency sometimes returns no lens at
    all, so counting it as lensed would admit a route that authorizes
    nothing on that branch.

    :return: None
    """
    assert resolve_lens_type(_union_with_none) is None


def test_annotated_is_unwrapped() -> None:
    """``Annotated[...]`` is unwrapped to the type it wraps.

    :return: None
    """
    assert resolve_lens_type(_annotated) is TeacherLens


def test_non_lens_return_does_not_resolve() -> None:
    """A non-lens return annotation resolves to None.

    :return: None
    """
    assert resolve_lens_type(_not_a_lens) is None


def test_missing_annotation_does_not_resolve() -> None:
    """A dependency with no return annotation resolves to None.

    :return: None
    """
    assert resolve_lens_type(_unannotated) is None


def test_base_lens_resolves() -> None:
    """The ``Lens`` base itself counts as a lens.

    :return: None
    """
    assert resolve_lens_type(_base_lens) is Lens


def test_each_subtype_resolves_to_itself() -> None:
    """Resolution returns the specific subtype, not the base.

    The privacy gate selects teacher-facing routes by this value, so
    collapsing every lens to ``Lens`` would make it check every route or
    none.

    :return: None
    """
    assert resolve_lens_type(_student) is StudentLens
    assert resolve_lens_type(_teacher) is TeacherLens


def test_unresolvable_annotation_raises_and_is_never_swallowed() -> None:
    """An annotation naming an unimportable type raises.

    The failure must reach the caller: a resolver that returned a default
    here would let the route-lens gate pass universally, which is the
    specific defect NFR14.7 exists to forbid.

    :return: None
    """

    def _bad() -> None:
        raise NotImplementedError

    # Set the annotation after definition: the name must be unresolvable at
    # resolution time, which a literal annotation would make a lint error
    # rather than the runtime condition under test.
    _bad.__annotations__["return"] = "NoSuchLensType"

    with pytest.raises(AnnotationResolutionError):
        resolve_lens_type(_bad)
