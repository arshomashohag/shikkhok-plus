"""The registry of public view models.

Every model a public page renders is registered here so the privacy gate
can walk it. A view model that is not registered is invisible to
:func:`app.contract.privacy.public_field_leaks`, which is why registration
is a decorator on the class rather than a list kept somewhere else.
"""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["PUBLIC_VIEW_MODELS", "register_view"]

#: Every public view model. Empty until the public pages exist, and
#: appended to only through :func:`register_view`.
PUBLIC_VIEW_MODELS: tuple[type[BaseModel], ...] = ()


def register_view[M: type[BaseModel]](model: M) -> M:
    """Register a public view model with the privacy gate.

    :param model: The view model class
    :return: The same class, so this works as a decorator
    """
    global PUBLIC_VIEW_MODELS
    PUBLIC_VIEW_MODELS = (*PUBLIC_VIEW_MODELS, model)
    return model
