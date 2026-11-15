"""The consent text an owner agrees to before a listing goes public."""

from __future__ import annotations

from typing import Final

__all__ = ["HUB_CONSENT_VERSION"]

#: The version of the consent text shown at publish time. Publishing records
#: it, so a change of wording means every owner must agree again.
HUB_CONSENT_VERSION: Final = "2026-11-14"
