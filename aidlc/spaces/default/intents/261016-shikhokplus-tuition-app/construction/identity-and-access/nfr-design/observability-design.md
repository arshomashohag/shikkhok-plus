# Observability Design — `identity-and-access` (U3)

**Stage**: nfr-design (3.3)
**Phase**: Construction
**Unit**: U3 `identity-and-access` — `service`, XL
**Bolt**: B3 `b3-identity-and-access`

> **Redaction is designed in, not applied afterwards.** The mechanism is
> that there is nowhere to put a forbidden value — which is stronger than a
> rule saying not to.

## Sources

- [stage] `nfr-design-questions.md`
- [upstream] `construction/identity-and-access/nfr-requirements/observability-requirements.md` — NFR8.1–NFR8.7
- [upstream] `construction/identity-and-access/nfr-requirements/security-requirements.md` — T8
- [upstream] `construction/identity-and-access/functional-design/rules.md` — BR6.2
- [upstream] `inception/requirements-analysis/requirements.md` — NFR12
- [upstream] `inception/units-generation/unit-of-work-story-map.md` — US1.8
- [team] `## Deployment`
- [project] `## Forbidden`

---

## A. The audit row has nowhere to hide a secret

```python
class AuthEvent(StrEnum):
    OTP_ISSUED = "otp_issued"
    VERIFY_FAILED = "verify_failed"
    VERIFY_SUCCEEDED = "verify_succeeded"
    REFRESH_ROTATED = "refresh_rotated"
    REFRESH_REUSE_DETECTED = "refresh_reuse_detected"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event: AuthEvent              # closed enum
    account_id: UUID | None       # nullable, deliberately
    correlation_id: str
    occurred_at: datetime
```

**No free-form field exists.** A test asserts the dataclass has no `str`
field other than `correlation_id`, so there is physically nowhere to put a
phone number, an OTP, a token or a child name [NFR8.2].

> This is the difference between a redaction *rule* and a redaction
> *mechanism*. A rule is applied by whoever writes the next log line; a
> missing field is applied by the type checker.

`account_id` is nullable because an OTP issued for an unknown number has no
account — and writing a placeholder would reintroduce the existence oracle
the issue path exists to close.

## B. The two questions, and what answers them

| Question | Answered by |
|---|---|
| *"Was this child's data accessed improperly?"* | The append-only auth log + the production-session log [NFR8.1, NFR8.5] |
| *"Is something burning the SMS budget?"* | The ceiling alert + `getBalanceApi` polling [NFR8.4] |

**`getBalanceApi` is the only hook the gateway offers** — no delivery
report, no message id — and it catches both *"about to run out"* and,
indirectly, *"something is burning SMS"*.

## C. Correlation without content

Every request carries a correlation id, in every log line and every audit
row [NFR8.6]. That is what ties an investigation together **without
carrying what is under investigation**.

## D. The gateway's two logging prohibitions, enforced not reviewed

| Never logged | Why | Enforced by |
|---|---|---|
| `error_message` | **Echoes the API key in plaintext** — verified live | A call-level test over `gateway/` |
| The request body | Carries the number **and** the code | The same test |

Each send logs `(purpose, outcome, correlation_id)` and nothing else.

## E. Not built

| Not built | Why |
|---|---|
| Per-row access logging | Disproportionate and unaffordable in storage at this scale |
| Distributed tracing | One process; nothing to correlate across |
| A metrics dashboard | No operator watches one. An alert reaching a phone beats a chart nobody opens |
| SLI/SLO | Needs an availability target Phase 1 cannot honestly state |

---

## Assumptions & Open Questions

**None.** [assumption] Alert *delivery* — where an alert goes and who sees
it — belongs to Infrastructure Design. This states what must alert.
