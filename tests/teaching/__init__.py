"""D4's session, attendance, topic and announcement tests.

**A package marker, and it is load-bearing rather than conventional.**
Without it pytest imports test modules by bare basename, so
``tests/teaching/test_generation.py`` collides with
``tests/fees/test_generation.py`` and the second one collected errors
out -- which is how a whole suite can silently stop running.
"""

from __future__ import annotations
