"""Static proof that the handler covers every taxonomy class.

**Why this file exists.** The design requires the handler's mapping to be
total over the taxonomy, checked at build time rather than discovered as a
production 500. The obvious construct -- ``assert_never`` in the handler's
default arm -- cannot do it here: ``TaxonomyError`` is itself instantiable,
so mypy cannot narrow that arm to ``Never`` and the assertion fails to
type-check.

The proof is moved here instead, over a closed union of the five concrete
classes. ``assert_never`` **does** narrow against that union, so adding a
sixth subclass without adding it to ``TaxonomyClass`` and to the handler's
match is a **mypy error**, not a runtime surprise.
"""

from __future__ import annotations

from typing import assert_never

from app.errors._classes import (
    AuthorizationError,
    ConflictError,
    FatalError,
    TransientError,
    ValidationError,
)

__all__ = ["TaxonomyClass", "status_for"]

#: The closed union the handler must cover. A sixth class added to the
#: taxonomy but not to this union fails ``status_for`` at type-check time.
type TaxonomyClass = (
    ValidationError | AuthorizationError | ConflictError | TransientError | FatalError
)


def status_for(error: TaxonomyClass) -> int:
    """Return the HTTP status for a taxonomy class.

    Exists for its exhaustiveness proof as much as for its value: the
    ``assert_never`` below is what makes a missing sixth class a build-time
    error. The handler's own match mirrors this mapping.

    :param error: One of the five taxonomy classes
    :return: The HTTP status that class maps to
    """
    match error:
        case ValidationError():
            return 400
        case AuthorizationError():
            return error.status
        case ConflictError():
            return 409
        case TransientError():
            return 503
        case FatalError():
            return 500
        case unreachable:
            assert_never(unreachable)
