# The committed API contract

`openapi.json` is **generated output**, not a source file.

## Changing it

```bash
make openapi
```

That is the only sanctioned way to update it. Then **read the diff** — it
is the contract change under review, and with one reviewer the pull
request is where review actually happens.

## Why hand-editing it breaks the control

The schema-diff gate compares the committed bytes against bytes generated
from the live application, and fails CI on any difference. It **cannot
tell a deliberate hand-edit from drift** — both are "the two files
differ". So editing this file to turn a red diff green inverts the gate
into a rubber stamp, and it looks exactly like fixing the problem.

If the generated document is wrong, the **model or route definition** is
wrong. That is where the fix goes.

## What the gate guarantees, and what it does not

It guarantees the committed contract matches the application. It does not
guarantee anyone read the diff — that is the one bypass no check closes,
and it is why the diff lives in a pull request rather than in a log.

## Determinism

Generation is deterministic **across processes**, which is stronger than
it sounds and had to be measured rather than assumed. `sort_keys` orders
object *keys*, not list *values*: a `required` list built from a `set`
keeps its hash ordering straight through a fully canonical dump, and
Python seeds hash randomization once per process. Verified — five
interpreter processes serializing one seven-element set produced five
different orderings.

So `app/contract/serialize.py` also sorts the order-insensitive lists
(`required`, `enum`, `tags`, `security`), and `tests/contract/test_schema_diff.py`
compares an in-process generation against a **subprocess** one, which is
the only arrangement that gets a fresh hash seed and can therefore observe
the failure. `PYTHONHASHSEED` is deliberately not pinned: pinning it would
make the test pass while CI still failed intermittently.

Order-**sensitive** lists keep their order. `servers` is tried in order and
`allOf` composition order affects how a reader merges subschemas, so the
sorted allowlist is deliberately narrow.
