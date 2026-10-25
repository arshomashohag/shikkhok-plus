"""D3's fee-cycle, ledger, claim and verification tests.

**Added at D4, and the absence was a latent hazard rather than a
style point.** Without a package marker pytest imports test modules by
bare basename, so this package's ``test_generation.py`` and
``test_generation_races.py`` collided with D4's the moment those
existed -- and a collection error is how a whole suite silently stops
running. Most test packages here already carried one; these two did
not.
"""

from __future__ import annotations
