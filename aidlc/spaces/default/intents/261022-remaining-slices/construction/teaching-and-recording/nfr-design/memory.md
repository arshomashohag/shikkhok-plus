> This file is kept up to date automatically while the stage runs. Add observations at the review step, not by editing here directly.

## Interpretations

- 2026-10-24 — The brief names three concurrency mechanisms that must stay
  distinct. I treated that as the organising spine of `scalability-design.md`
  section 2 rather than scattering them: one table mapping mechanism to hazard
  to enforcement, then one subsection per mechanism with its own test shape.
  Blurring them is the failure the brief predicts, and a shared section is how
  blurring happens.
- 2026-10-24 — PU-3.6 carries no performance obligation [Q14.3 answer C].
  `performance-design.md` therefore designs no latency mechanism, no timing
  budget and no benchmark harness. What stands in its place is structural
  (default-present plus the single atomic write) and is designed as
  correctness. Stating the absence is the requirement [NFR2.6].
- 2026-10-24 — The queue's storage is a recommendation for the human, not a
  settled decision [tech-stack NFR5.10-5.12]. Every queue property in
  `reliability-design.md` section 3 is therefore designed against BEHAVIOUR,
  with a named subsection stating exactly which parts would differ under Room.

## Deviations

- 2026-10-24 — `tests/auth/test_ceilings.py:283` places `import threading`
  inside the function body, violating the imports-at-top rule. The brief says
  to copy the barrier pattern and not that part. The design specifies the
  barrier shape with the import at module scope and says why in one line, so a
  developer copying the file does not copy the violation.

## Tradeoffs

- 2026-10-24 — Session-level version granularity is inherited from ADR-006 and
  contract-summary section B.8, not chosen here. Its real cost (two devices on
  DIFFERENT students in the SAME session do conflict) is designed for rather
  than hidden: the conflict-resolution screen is the mechanism that makes that
  cost survivable, which is why it is specified in full.
- 2026-10-24 — A conflicted queue item the teacher never resolves has no
  automatic resolution by design. Designing an expiry would be inventing a
  discard rule BR3.6 forbids. The design specifies indefinite retention plus
  visibility instead, and names that as the accepted cost.

- 2026-10-24 — A proposal arrived mid-stage to specify a new test asserting
  the restricted role can SELECT from every live table, to catch a missing
  GRANT at `make check`. **I read `tests/db/test_governance.py` before
  specifying it and found it already built**, twice over —
  `test_the_restricted_role_can_read_every_live_table` and
  `test_every_owned_table_is_visible_to_the_restricted_role`, both reusing
  `_live_tables()` so the `alembic_version` exclusion has no second copy.
  Specifying it as new work would have been a wish dressed as an addition.
  `security-design.md` § 1.3 records it as inherited and says why the section
  exists at all.
- 2026-10-24 — The same check turned a second proposed finding into a
  non-finding: **table ownership is already correct**. `0001` GRANTs to
  `shikkhok_app` and never makes it owner, and the role is `NOINHERIT LOGIN`.
  What IS a live obligation is the **per-table GRANT**, because there is no
  `ALTER DEFAULT PRIVILEGES` anywhere — and `0002`'s docstring records that an
  ungranted table goes **invisible in `information_schema` to the restricted
  role**, so the governance gates silently stop covering it rather than
  failing. That is why the grant sits in the security document.

## Open questions

- 2026-10-24 — Docker is unavailable in this session, so I could not EXECUTE
  the governance or privacy suites. `python3 -m pytest tests/db/test_governance.py -q`
  returned `sss.sssss`. Every claim about built tests in these documents is
  from READING the files, and each is cited by path and symbol so it is
  checkable. No document claims a measured green run. **The skip itself is the
  gap `team.md` assigns a CI precondition assertion to**, and this session is a
  live instance of it.
- 2026-10-24 — The queue's storage remains the human's to settle. The
  recommendation (atomic serialized file) and the alternative (Room) are both
  designed for; `reliability-design.md` § 3.7 is the complete delta, and the
  only property that changes is where atomicity comes from.
- 2026-10-24 — Three artifacts remain stale for the human at a learnings gate,
  none of which this stage may edit: `project.md`'s NEVER on local write
  queues (contradicts NFR5, which it cites), `team.md`'s Android toolchain
  table (spotless, detekt and the coverage ratchet are built), and `team.md`'s
  PU-3.6 Macrobenchmark bullet (the obligation was dropped at Q14.3).
