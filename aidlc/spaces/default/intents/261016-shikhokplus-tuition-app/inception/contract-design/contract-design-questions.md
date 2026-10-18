# Contract Design — Questions

**Stage**: contract-design (2.8)
**Phase**: Inception
**Depth**: Comprehensive

## Sources

- [upstream] `inception/units-generation/unit-of-work.md` and `unit-of-work-dependency.md`
- [upstream] `inception/domain-design/components.md` and `decisions.md`
- [upstream] `inception/requirements-analysis/requirements.md`
- [team] the affirmed error taxonomy and money-as-a-type practices

---

## How this stage was answered

Running under the user's standing delegation to decide the remaining Inception
options. The contract decisions went to a dispatched architect with the system's
deployment shape stated explicitly, and its decisions were applied after the
OpenAPI fragment was validated.

## Q1. Public and external API surface

[Answer]: One public REST API between the FastAPI backend and the Android
client, plus a separately versioned external account-deletion web route that a
browser reaches without the app installed. The REST API is a genuine external
boundary: an installed Android app cannot be forced to update, so any version in
the field is a live consumer.

## Q2. Integration mechanism per boundary

[Answer]: Nine contracts (C1-C9). HTTPS/JSON with OpenAPI 3.1 for the public API;
vendor HTTPS behind one adapter each for the SMS gateway and FCM; HTML form plus
POST for the deletion route; and five in-process boundaries enforced by import
rules and CI tests rather than by a wire.

Most DAG edges are deliberately **not** contracts. All eleven Units deploy as one
FastAPI container plus one Android module, so between backend Units there is no
wire, no serialization, no partial failure and no version skew. The artifact
enumerates those nine edges once and says why, rather than inventing a spec per
edge.

## Q3. Contract ownership

[Answer]: `api-contract` (U2) owns the schema and its CI gates; route bodies
belong to the contributing Unit. `money-core` (U1) owns the money wire
representation and the import boundary. `identity-and-access` (U3) owns the lens
resolvers and the SMS adapter. `privacy-and-governance` (U11) owns the deletion
route and the manifest pair. The FCM adapter's owner is latent between U6 and U7
and is recorded as an open question rather than guessed.

## Q4. Versioning and breaking-change policy

[Answer]: `/v1/` additive-only. The client tolerates unknown fields; the server
never removes or retypes one. This is stricter than ordinary API hygiene because
an uninstallable client version stays in the field indefinitely, so a breaking
change is not a migration but a permanent fork.

## Q5. Error, timeout and retry behaviour

[Answer]: One error envelope carrying `code`, a server-supplied `retryable`
boolean and a `message_key`, over the five-class taxonomy mapped to HTTP status.
Retryability is a property of the error class decided at the raise site, never a
judgement at the call site, and never inferred by the client from a status code.

Per-boundary: the SMS gateway is attempted **once with no automatic retry**, and
a timeout is recorded as `unknown` rather than `failed`, because the message may
have been delivered and a retry double-charges and double-messages. FCM is
best-effort, dispatched post-commit outside the request transaction, and never
fails its caller. Database serialization failures retry the whole transaction;
connection failures fail fast rather than retrying into a loaded instance.

---

## Consolidated Summary Confirmation

Does this all look correct before I generate the artifact?

- **Nine contracts, not twenty.** Most dependency edges are in-process import
  boundaries, enumerated once with the reason, rather than each given a spec
  that would describe nothing.
- Four of the nine are in-process (money chokepoints, money import boundary,
  the lens as a data dependency, the governance manifests). They count as
  contracts because a violation fails CI, which is the operative meaning in a
  modular monolith with one reviewer.
- The public REST API is `/v1/` **additive-only**, with a validated OpenAPI 3.1
  fragment covering the error envelope, the Money type, the auth scheme and four
  exemplary endpoints — enough that the rest follows by pattern, without
  becoming a second source of truth beside the generated schema.
- **Money crosses as a JSON string**, pattern-constrained to exactly two decimal
  places, rejecting numbers, negatives and separators on the wire.
- **The SMS gateway is sent once, never retried**, with a timeout recorded as
  `unknown` rather than `failed`.
- Seven open questions are flagged with the Unit each blocks, rather than
  invented. Three are worth deciding soon: whether a display string accompanies
  every money field, the 404-instead-of-403 rule an implementer will otherwise
  "fix", and that a conflict re-apply must use a new idempotency key or it
  silently becomes a no-op.

[Answer]: Looks correct
