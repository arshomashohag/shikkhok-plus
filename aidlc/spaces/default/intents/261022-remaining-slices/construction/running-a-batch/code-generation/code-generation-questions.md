# Code Generation Plan Approval

AI-DLC writes this file when it asks you to approve the plan. To answer here
instead of in chat, write your answer after `[Answer]:` and say done.

## Plan Approval

Approve the code plan for running-a-batch?

- Builds: the roster's per-link acceptance states and the batch accepted count, plus the four screens D1's model made necessary — add student, create batch, remove seat, and the guardian child home.
- Touches: `app/batches/service.py`, `app/api/batches.py`, `app/schemas/batches.py`, `openapi.json`, and `android/.../feature/{batches,roster,guardian}`.
- Tests: ~22 backend (4 test-first on the count and the refusals), ~26 Kotlin across mappers and screens, 6 Bangla layout rows. **No migration.**

Full plan: aidlc/spaces/default/intents/261022-remaining-slices/construction/running-a-batch/code-generation/code-generation-plan.md
Test instructions: aidlc/spaces/default/intents/261022-remaining-slices/construction/running-a-batch/code-generation/unit-test-instructions.md

[Approval Fingerprint]: sha256:v3:8c9c78aaa28c27e4d86d9f9b7da1d0867bbbf15adb191806547fbd4494a03008
[Planned Source]: 6630e72bce975e0b564e38962a29eae1340d448621f1e677f95424d19b5e93a1

- A. Approve Plan
- B. Request Changes
- C. I'll edit the files

[Answer]: A. Approve Plan
