# Units Generation — Questions

**Stage**: units-generation (2.7)
**Phase**: Inception
**Depth**: Comprehensive

## Sources

- [upstream] `inception/domain-design/components.md` and `decisions.md`
- [upstream] `inception/requirements-analysis/requirements.md`
- [upstream] `inception/user-stories/stories.md` — 45 stories
- [upstream] `ideation/scope-definition/intent-backlog.md` — PU-1..PU-8
- [team] the affirmed Walking Skeleton and Way of Working practices

---

## How this stage was answered

Running under the user's standing delegation to decide the remaining Inception
options. The decomposition decision went to a dispatched architect with the
binding constraints stated, and its decision was applied after the DAG was
validated independently.

## Q1. Unit boundary strategy

[Answer]: Hybrid — vertical by default, split in four places. Each feature Unit
(U3–U9) carries its backend endpoints, its Android screens and its tests
together. Four Units are not feature slices because what they deliver is not
one: `money-core` below the graph, `api-contract` beside it, `release-packaging`
to one side, `privacy-and-governance` as the terminal join. A split-by-surface
alternative was rejected because it puts the affirmed walking skeleton across
two Units, and because a backend-only checkpoint can be reviewed only against a
test suite — the worst allocation for a single reviewer whose Android depth is
the declared weak spot.

## Q2. Unit granularity

[Answer]: Eleven Units. Coarse enough that each is demonstrable at its
checkpoint, fine enough that the three genuinely non-vertical concerns get their
own gate. The money library is the clearest case: it has no I/O by affirmed
practice, carries 100% branch coverage, and is fully testable before any
endpoint exists.

## Q3. Dependency ordering

[Answer]: Topology only, with parallelism recorded. Four independent sets exist;
the useful one is `release-packaging` against all feature work, which decouples
the Play-release toolchain from feature delivery. This stage states no build
order and no critical path — those are Delivery Planning's.

## Q4. Integration points and contracts

[Answer]: Seven named integration points, recorded in the dependency artifact.
The load-bearing ones: the `Money` type enforced by import boundary rather than
convention; the committed OpenAPI schema as a gate every `service` Unit must
pass; the lens handed to handlers as a data dependency carrying its scoping
value; and `Enrollment` as the privacy pivot every teacher-facing read is keyed
on.

## Q5. Deployment model

[Answer]: One FastAPI container — a modular monolith — behind one Lightsail
instance, with Alembic as a distinct logged step before traffic. Every Android
Unit is a feature package inside the single `:app` Gradle module. No ADR asserts
independent deployability, so one image violates nothing, and the USD 50/month
ceiling forbids anything else.

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- Eleven Units: `money-core` (library), `api-contract` (spec), seven feature
  services, `release-packaging` (packaging), `privacy-and-governance` (spec).
  Validated acyclic by topological sort, single root, every dependency declared.
- **U3 `identity-and-access` is the walking skeleton**, and it runs before any
  later Unit: its only predecessors are a pure value type and a schema. It
  carries the full scope `team.md` binds the skeleton to, and it is XL —
  deliberately, because trimming it would contradict an affirmed practice.
- All 45 stories assigned: 41 to one Unit, 4 cross-cutting with an explicit
  split naming who owns the mechanism and who carries the obligation.
- PU-8 splits three ways: packaging and Play compliance become Units, push
  splits across U6 and U7 by trigger, and Bangla layout, accessibility and
  low-end discipline become **standing per-Unit obligations** — none of them can
  be a Unit, because they are obligations on every Unit that adds a screen.
- Two deletion stories move out of the auth Unit into `privacy-and-governance`,
  because a deletion path built before the disposition manifest would delete by
  ad-hoc logic and then need rewriting.
- Flagged, not resolved: `privacy-and-governance` is both terminal in the DAG
  and release-blocking. That tension belongs to Delivery Planning.

[Answer]: Looks correct
