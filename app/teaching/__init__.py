"""Sessions, attendance, the topic log and announcements.

The unit's centre of gravity is :mod:`app.teaching.submissions`, which
holds the queued-write path: the replay check, the conditional version
update, and the atomic roster apply, in the order
``security-design.md`` § 5.4 requires.
"""

from __future__ import annotations
