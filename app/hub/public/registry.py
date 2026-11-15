"""The registry of public view models.

Every model a public page renders is registered here so the privacy gate
can walk it. A view model that is not registered is invisible to
:func:`app.contract.privacy.public_field_leaks`, which is why registration
is a decorator on the class rather than a list kept somewhere else.
"""

from __future__ import annotations

from pydantic import BaseModel

__all__ = ["PUBLIC_VIEW_MODELS", "register_view", "registered_views"]

#: Every public view model, appended to in place by :func:`register_view`.
#: Read it through :func:`registered_views` rather than importing the name,
#: so a reader never holds a stale snapshot.
PUBLIC_VIEW_MODELS: list[type[BaseModel]] = []


def register_view[M: type[BaseModel]](model: M) -> M:
    """Register a public view model with the privacy gate.

    :param model: The view model class
    :return: The same class, so this works as a decorator
    :raises ValueError: When the model is already registered
    """
    if model in PUBLIC_VIEW_MODELS:
        msg = f"public view model {model.__name__} is already registered"
        raise ValueError(msg)
    PUBLIC_VIEW_MODELS.append(model)
    return model


def registered_views() -> tuple[type[BaseModel], ...]:
    """Return the view models registered at the time of the call.

    :return: A snapshot taken now
    """
    return tuple(PUBLIC_VIEW_MODELS)
