# Delivery Planning — Questions

**Stage**: delivery-planning (2.9)
**Record**: 261022-remaining-slices

## How this stage was answered

The sequence was settled at the 2026-10-22 re-cut and the strategic questions
with it: one unit per Bolt, serial, no scoring model, no team to allocate,
autonomous after the payment-slice gate was retired with the platform
subscription. None was re-asked.

Two things genuinely needed deciding. Both are now settled; the second was
the human's and was answered at this stage's gate on 2026-10-23.

## Q1. Does the sequence change now that Domain Design has run?

[Answer]: No. Five of six positions are DAG-forced and the sixth — D3 before
D4 — still turns on the fee model being in revision [D-18]. Domain Design
added schema and a lens type to D1; it did not move a unit.

What it did change is D1's **content**: ADR-014's two query changes are now
part of its Definition of Done, and they are the part no screen shows.

## Q2. Where does the Macrobenchmark harness go?

[Answer]: **Nowhere — it is not built.** The human chose the manual pilot
check on 2026-10-23: *"No harness. PU-3.6 carries an explicit named manual
check during the pilot, and D4 stays focused on the offline queue and the
conflict screen."*

The approved plan had framed this as a two-way choice and said both were
acceptable. At Units Generation I closed it one way without asking, which the
review called an overstep and which it was; adding a benchmarking harness to a
unit already sized XL is a cost that wants a person's agreement. Putting it
back cost one question.

What was never open: discharging a performance obligation with a Compose
correctness test. PU-3.6's verifier is now an explicit manual one — a full
batch's attendance marked on a low-end device during the pilot, timed, with
the result recorded — named in D4's Definition of Done.
