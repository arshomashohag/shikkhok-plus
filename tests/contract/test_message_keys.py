"""Every message key the backend emits must be renderable by a client.

**The server names which string to show and never sends the string**
[TC-15, D-43]: a server-sent English message cannot be localized, and in
a Bangla-first UI it guarantees untranslated English in front of a
teacher.

That contract has a gap nothing else checks. The two surfaces are built
separately, so a new raise site with a new key ships a backend that is
correct and an app that renders a generic fallback -- which looks like a
working error message and is therefore never reported. This test
publishes the backend's keys so the Android side can assert against
them, and fails here when a key is added without one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Where the published key list lives. Committed, so a contract change
#: shows up as a reviewable diff rather than being invisible.
PUBLISHED = ROOT / "message-keys.json"

_KEY = re.compile(r'message_key="([^"]+)"')


def _emitted_keys() -> set[str]:
    """Collect every message key raised anywhere in the backend.

    :return: The keys, as written at the raise sites
    """
    return {
        match
        for path in (ROOT / "app").rglob("*.py")
        for match in _KEY.findall(path.read_text())
    }


def test_every_emitted_key_is_published() -> None:
    """A new raise site must publish its key.

    :return: None
    """
    published = set(json.loads(PUBLISHED.read_text())["keys"])

    missing = _emitted_keys() - published
    assert missing == set(), (
        f"these keys are raised but not published: {sorted(missing)}. "
        f"Add them to {PUBLISHED.name} and give each a string on every "
        "client, or the app renders a generic fallback that looks like a "
        "working error message."
    )


def test_the_published_list_has_no_phantom_keys() -> None:
    """A key nothing raises is misinformation to the client.

    :return: None
    """
    published = set(json.loads(PUBLISHED.read_text())["keys"])

    phantom = published - _emitted_keys()
    assert phantom == set(), (
        f"these keys are published but raised nowhere: {sorted(phantom)}"
    )


def test_keys_are_dotted_lowercase() -> None:
    """The shape is a convention, and a client maps on it.

    :return: None
    """
    for key in _emitted_keys():
        assert re.fullmatch(r"[a-z0-9]+(\.[a-z0-9_]+)+", key), key
