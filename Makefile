# The one entrypoint. CI invokes exactly this target, in this order.
#
# A gate reproducible only by pushing is a gate that gets bypassed, and for a
# solo build that is the single most important property of the gate. So there
# is one command, it runs the same sequence everywhere, and it needs no
# secret: a fresh clone runs the complete gate immediately.
#
# Ordered cheapest-first, so a cheap failure never waits behind an expensive
# one.

PY ?= python3

.PHONY: check format lint typecheck test gates install clean

check: lint typecheck test
	@echo ""
	@echo "All gates passed."

## 3. Format and lint, including GATE 2 (raw decimal banned outside
##    app/money). A banned-import rule belongs in lint so it also runs in the
##    pre-commit path.
lint:
	@echo "==> format"
	$(PY) -m ruff format --check app tests
	@echo "==> lint (includes Gate 2)"
	$(PY) -m ruff check app tests

## 4. Type check. The money module is a strict island, which is what makes
##    the ledger fold's exhaustiveness statically provable.
typecheck:
	@echo "==> typecheck"
	$(PY) -m mypy app

## 5-11. Tests, 100% branch coverage on the money module, both import gates
##       with their violation fixtures and configuration assertions, and the
##       property test over randomized histories.
test:
	@echo "==> tests + coverage"
	$(PY) -m pytest tests --cov=app.money --cov-branch --cov-report=term-missing

## The gates alone, for when that is what you are working on.
gates:
	$(PY) -m pytest tests/gates -v

format:
	$(PY) -m ruff format app tests
	$(PY) -m ruff check app tests --fix

install:
	$(PY) -m pip install -e ".[dev]"

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
