# Personas

**Stage**: user-stories (2.4)
**Phase**: Inception
**Record**: 261022-remaining-slices

> **The personas are unchanged and are not restated here.** P1 Rafiq (the
> private tuition teacher), P2 Tanvir (the student), P3 Shireen (the guardian)
> and P4 the platform owner are defined in full at
> `261016-shikhokplus-tuition-app/inception/user-stories/personas.md`, with
> their goals, pain points, context and relationships. Nothing in the re-cut
> adds a persona or alters one.
>
> What follows is only what the acceptance model changes about two of them.

## Sources

- [prior] `261016-shikhokplus-tuition-app/inception/user-stories/personas.md`
- [upstream] `inception/requirements-analysis/requirements.md` — FR1a

---

## What acceptance changes

### P2 Tanvir and P3 Shireen now make a decision

Under the superseded model, a student or guardian had no decision to make.
Their teacher recorded a number, they signed in, and the records were simply
there. The prior personas describe them accordingly: Tanvir's first encounter
with the product is seeing what was recorded about him.

**That is no longer their first encounter.** It is now a question: *a teacher
has added this number — is that you, and do you accept?*

Three things follow that matter for the stories:

- **The decision precedes the relationship.** Shireen's first interaction with
  ShikhokPlus is not seeing her child's attendance; it is being asked to take
  responsibility for a child's enrollment and a fee obligation. She needs
  enough to answer — which is why [FR1.9d] gives her batch, subject and fee
  rather than only a name.
- **Either of them may be the wrong person.** The prior personas assumed the
  number was right. The commonest cause of a pending seat nobody accepts is a
  mistyped digit, and the person holding that number is a stranger with no
  relationship to the teacher, the child, or the product. The stories must work
  for that person too, and for them the correct outcome is to decline and never
  hear about it again.
- **Either of them may mis-tap.** A declining person who meant to accept is a
  real student locked out of their own fee and attendance records, which is why
  [FR1.9c.1] makes the decision reversible by the person who made it.

### P1 Rafiq gains a state he must read

Rafiq's existing persona is defined by scarce time: he is teaching, and
anything that costs him attention between classes is a cost. The acceptance
model asks him to notice something new — that a seat is pending or declined
rather than simply quiet.

The prior record was explicit that dormant is deliberately *not* marked on the
roster, because "decorating most rows would flag normality as a problem"
[AC1.3.3]. That reasoning holds for dormant and fails for pending and declined:
those two states are not normality, and the whole reason to show them is that a
mistyped number is otherwise indistinguishable from a student who has not
opened the app.

No notification is sent for either [FR1.9h], which keeps the cost inside the
roster he already reads rather than adding an interruption.

### P4 the platform owner gains a second abuse surface

Signup's response is deliberately informative — it tells an existing number to
log in instead — where the OTP path's response is deliberately uniform. That
makes signup an existence oracle by construction, and it needs its own
per-number and per-IP ceilings [FR1.7d]. The operator's concern is unchanged in
character and now applies to two surfaces rather than one.

## Assumptions & Open Questions

None.
