"""How a review's author is named to a platform administrator.

An administrator moderating a review sees its author's role and an opaque
reference, never a name, a phone number or an account id [TC-14, D-6].

**The reference is not the help desk's** (Call 14). It is the same hash
function as :func:`app.help.identity.requester_ref` under a different
prefix, so one guardian's review and their help tickets -- where a teacher
who is also a guardian is shown by name -- carry references that cannot be
matched to each other.
"""

from __future__ import annotations

import uuid
from typing import Final

from app.help.identity import _opaque_ref

__all__ = ["review_author_ref"]

#: Domain-separates the review author's label from every other label.
_REF_PREFIX: Final = b"shikkhokplus/hub-review-author/v1:"


def review_author_ref(account_id: uuid.UUID) -> str:
    """Derive the opaque label for a review's author.

    :param account_id: The author's account
    :return: Ten upper-case hex characters
    """
    return _opaque_ref(_REF_PREFIX, account_id)
