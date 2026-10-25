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

.PHONY: check format lint typecheck test gates contract openapi install clean android lock audit android-quality

check: lint typecheck test android android-quality
	@echo ""
	@echo "All gates passed."

## Regenerate the Python lockfile. THE ONLY SANCTIONED WAY to update
## requirements.txt.
##
## Like openapi.json, that file is an OUTPUT, and the CI check compares it
## against a fresh compile — so hand-editing it to turn a red check green
## inverts the control. Unlike openapi.json, getting this wrong has a supply
## chain consequence rather than only a contract one.
##
## `--generate-hashes` is the point. Without it the file pins versions but
## not ARTIFACTS, and a version pin does not detect a substituted wheel.
## Compiled against Python 3.12 deliberately: that is what CI and the
## container run, and a lockfile compiled on a different minor version can
## resolve different markers.
## `--allow-unsafe` is required, not optional, and the name is misleading.
## It pins `pip` and `setuptools`, which pip-tools excludes by default —
## and with `--require-hashes` pip REFUSES an install where any requirement
## lacks a hash, so omitting it produces a lockfile that cannot be
## installed. Verified by installing into a clean venv rather than by
## reading the flag's documentation.
lock:
	@echo "==> compiling requirements.txt (hashes: this downloads every wheel)"
	$(PY) -m piptools compile --extra dev --extra api --generate-hashes \
		--allow-unsafe --output-file requirements.txt pyproject.toml
	@echo "    done — now read the diff."

## Dependency CVEs, locally. Annotating, same as the per-push CI step.
## The BLOCKING check is at the release gate, where each Critical and High
## is fixed or carries a dated row in .security-exceptions.md.
audit:
	@echo "==> dependency CVEs (annotating)"
	@$(PY) -m pip_audit --requirement requirements.txt --desc \
		--progress-spinner off \
		|| echo "    findings above do not block; they block the release gate."

## The Kotlin quality toolchain: format, static analysis, lint, coverage
## ratchet. Part of `check` for the same reason the Android suite is —
## team.md requires ONE entrypoint, local and in CI.
##
## Skipped with a loud notice when no JDK is reachable, matching the
## `android` target. The notice is the point: a silent skip would make this
## gate vacuous, which is this project's most common defect shape.
## **`set -e` is load-bearing, not decoration.** Inside a shell `if`, only
## the LAST command's exit status reaches make — so without it, a spotless,
## detekt or lint failure is silently discarded and the recipe reports
## success. That was true of the first version of this target and `make
## check` printed "All gates passed" over a failing build, which is this
## project's most-documented defect shape reproduced inside a gate written
## to prevent it. Caught by running it; a reader would not have seen it.
##
## One `gradlew` invocation for all four tasks rather than four: Gradle
## configures the project once, which is most of the wall-clock cost, and a
## single non-zero exit covers every task.
android-quality:
	@if ./gradlew --version >/dev/null 2>&1; then \
		set -e; \
		echo "==> kotlin quality: format, static analysis, lint, coverage"; \
		./gradlew :android:spotlessCheck :android:detekt \
		          :android:lintDebug :android:verifyCoverageRatchet \
		          --console=plain -q; \
	else \
		echo "SKIPPED: the Kotlin quality gates need a JDK and none was reachable."; \
		echo "          These gates did NOT run. CI runs them on every push."; \
	fi

## The Android suite. Part of `check` rather than a separate command the
## person has to remember: `team.md` requires ONE entrypoint, local and in
## CI, because a gate reproducible only by pushing is a gate that gets
## bypassed. CI still SPLITS the jobs so a Kotlin build does not gate a
## backend PR; that is a scheduling decision, not a second entrypoint.
##
## Skipped with a loud notice when no JDK is reachable, rather than failing
## the whole gate: a backend-only change on a machine without a JDK should
## not be unverifiable. The notice is the point — a silent skip would make
## this gate vacuous, which is this project's most common defect shape.
android:
	@if ./gradlew --version >/dev/null 2>&1; then \
		./gradlew :android:testDebugUnitTest --console=plain -q; \
	else \
		echo "SKIPPED: the Android suite needs a JDK and none was reachable."; \
		echo "          This gate did NOT run. CI runs it on every push."; \
	fi

## Regenerate the committed contract. THE ONLY SANCTIONED WAY to update
## openapi.json.
##
## That file is an OUTPUT. The diff gate compares committed bytes against
## generated bytes and cannot tell a deliberate hand-edit from drift — both
## are "the two files differ" — so hand-editing it to turn a red diff green
## inverts the control into a rubber stamp. It also looks exactly like
## fixing the problem, which is why this target exists and is named in the
## README beside the file.
##
## After regenerating, READ THE DIFF. It is the contract change under
## review, and with one reviewer the pull request is where that happens.
openapi:
	@echo "==> regenerating openapi.json"
	$(PY) -m app.contract.emit > openapi.json
	@echo "    done — now read the diff."

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
	@echo "==> tests + money coverage (100% branch)"
	$(PY) -m pytest tests --cov=app.money --cov-branch --cov-report=term-missing
	@echo ""
	@echo "==> backend coverage floor (80% line) for the rest of app/"
	@# A SECOND run, because the two floors genuinely differ: 100% branch on
	@# the money module, 80% line elsewhere. One run cannot enforce both, and
	@# the floor that is not enforced is the one that quietly erodes.
	@#
	@# app.contract.emit is excluded: it is a `python -m` entry point whose
	@# whole body is the subprocess the determinism test invokes, so it is
	@# exercised in a child process where this run's tracer cannot see it.
	@#
	@# The package list is EXPLICIT rather than `--cov=app`, so a new
	@# package is a deliberate line here. The cost of that choice is real
	@# and was paid at B3: five new packages existed for a whole Bolt
	@# before this line mentioned them, and the floor passed at 95% while
	@# measuring none of the code the Bolt had just written. A missing
	@# entry does not fail -- it silently narrows what the floor covers,
	@# which is the quietest way a coverage gate erodes.
	@#
	@# test_coverage_scope.py asserts this list against what is on disk.
	@# It checks top-level MODULES as well as packages: its own first
	@# version globbed only */__init__.py, so app/config.py arrived
	@# outside the floor and the gate passed -- the very failure the
	@# gate exists to prevent, reproduced inside the gate.
	$(PY) -m pytest tests -q -p no:cacheprovider \
		--cov=app.accounts --cov=app.analytics \
		--cov=app.api --cov=app.audit --cov=app.auth --cov=app.authz \
		--cov=app.batches \
		--cov=app.config --cov=app.contract --cov=app.db --cov=app.errors \
		--cov=app.fees \
		--cov=app.gateway --cov=app.governance --cov=app.main \
		--cov=app.marks \
		--cov=app.notifications \
		--cov=app.schemas \
		--cov=app.teaching \
		--cov-report=term-missing --cov-fail-under=80 \
		--cov-config=.coveragerc-backend

## The gates alone, for when that is what you are working on.
gates:
	$(PY) -m pytest tests/gates -v

## The contract gates alone: schema diff, money, privacy, route lenses, and
## the four violation fixtures that prove each one can fire.
contract:
	$(PY) -m pytest tests/contract -v

format:
	$(PY) -m ruff format app tests
	$(PY) -m ruff check app tests --fix
	@if ./gradlew --version >/dev/null 2>&1; then \
		echo "==> kotlin format"; \
		./gradlew :android:spotlessApply --console=plain -q; \
	else \
		echo "SKIPPED: Kotlin formatting needs a JDK and none was reachable."; \
	fi

install:
	$(PY) -m pip install -e ".[dev]"

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

# ---------------------------------------------------------------------------
# Deployment.
#
# The ordering in `deploy-staging` is LOAD-BEARING, not procedural, and
# it is encoded here rather than left to a runbook because B5's
# infrastructure specification found that skipping step 2 fails the
# deploy at step 4 with an opaque error AFTER the operator has already
# done work.
# ---------------------------------------------------------------------------

## Bring the full stack up locally. Same image staging runs.
up:
	docker compose up -d --build
	@echo ""
	@echo "Waiting for the API to answer..."
	@until curl -fsS http://localhost:8000/health >/dev/null 2>&1; do sleep 1; done
	@echo "API is up. Applying migrations as a SEPARATE step:"
	docker compose exec -T api alembic upgrade head
	@curl -s http://localhost:8000/health
	@echo ""

## Stop the stack. Keeps the database volume.
down:
	docker compose down

## Stop the stack AND destroy the database. Named so nobody runs it by
## accident while reaching for `down`.
destroy-local-data:
	docker compose down -v

## Apply migrations against whatever SHIKKHOKPLUS_DATABASE_URL names.
## A distinct, logged step -- never a side effect of container start.
migrate:
	$(PY) -m alembic upgrade head

## The post-deploy smoke set: the skeleton path end to end.
##
## This is what makes a deploy "done". A container that started is not a
## container that serves: the health endpoint reports database
## connectivity and the applied revision, so a schema that did not
## migrate fails HERE rather than on a teacher's first request.
##
## Usage: make smoke BASE_URL=https://staging.example.com
BASE_URL ?= http://localhost:8000
smoke:
	@echo "==> health"
	@curl -fsS --max-time 10 $(BASE_URL)/health > /tmp/shikkhok-smoke.json \
	  || (echo "SMOKE FAILED: $(BASE_URL)/health did not answer." && \
	      echo "             The container may not be running, or the" && \
	      echo "             URL is wrong. Nothing was deployed." && exit 1)
	@cat /tmp/shikkhok-smoke.json
	@echo ""
	@$(PY) -c "import json,sys; d=json.load(open('/tmp/shikkhok-smoke.json')); \
	  ok = d.get('database')=='ok' and d.get('migration_revision'); \
	  print('SMOKE FAILED: database=%r revision=%r. Did the migration step run?' \
	        % (d.get('database'), d.get('migration_revision'))) if not ok else None; \
	  sys.exit(0 if ok else 1)"
	@echo "==> OTP issue (null gateway in staging: no real SMS)"
	@curl -fsS -X POST $(BASE_URL)/v1/auth/otp \
	  -H 'Content-Type: application/json' \
	  -d '{"phone":"+8801700000000"}' >/dev/null
	@echo "==> unauthenticated roster read is refused"
	@test "$$(curl -s -o /dev/null -w '%{http_code}' \
	  $(BASE_URL)/v1/batches)" = "401" \
	  || (echo "SMOKE FAILED: an unauthenticated read was NOT refused" && exit 1)
	@echo ""
	@echo "Smoke passed."

.PHONY: up down destroy-local-data migrate smoke

# ---------------------------------------------------------------------
# The Android upload key
# ---------------------------------------------------------------------

## Where the keystore lives. OUTSIDE the repository by default: a .jks
## committed by accident means rotating through Play support, and no
## .gitignore rule catches a file you did not expect to create.
KEYSTORE ?= $(HOME)/.shikkhokplus/upload.jks
KEY_ALIAS ?= upload

## Generate the Play upload key. Run ONCE, ever.
##
## **Losing this is not a normal mistake.** With Play App Signing,
## Google holds the real signing key and this is only the upload key,
## so loss is recoverable through Play support -- but only if you still
## have the app. Keep the file and the password somewhere durable
## before you need them.
##
## Refuses to overwrite an existing keystore. Regenerating one after a
## release means Play rejects every future upload for that app, which
## is not recoverable by any command here.
##
## Usage: make android-key
##        make android-key KEYSTORE=/path/to/upload.jks
android-key:
	@test ! -f "$(KEYSTORE)" || (\
	  echo "REFUSING: $(KEYSTORE) already exists."; \
	  echo ""; \
	  echo "Overwriting a keystore after a release means Play rejects"; \
	  echo "every future upload for this app, permanently. If you are"; \
	  echo "certain this one was never used, move it aside yourself:"; \
	  echo "  mv $(KEYSTORE) $(KEYSTORE).old"; \
	  exit 1)
	@mkdir -p "$$(dirname "$(KEYSTORE)")"
	@chmod 700 "$$(dirname "$(KEYSTORE)")"
	@echo "==> Generating the upload key at $(KEYSTORE)"
	@echo ""
	@echo "    Keystore password: choose a strong one and SAVE IT NOW."
	@echo "    Name (CN):         ShikhokPlus"
	@echo "    Country code:      BD"
	@echo "    Key password:      press Enter to reuse the keystore one."
	@echo ""
	@keytool -genkeypair -v \
	  -keystore "$(KEYSTORE)" \
	  -alias "$(KEY_ALIAS)" \
	  -keyalg RSA -keysize 4096 \
	  -validity 10000
	@chmod 600 "$(KEYSTORE)"
	@echo ""
	@echo "Done. Now run:  make android-key-secrets"

## Print the four GitHub secrets and one variable, ready to paste.
##
## **This prints a signing key to your terminal.** That is the point --
## GitHub needs it pasted in -- but it means the value lands in your
## scrollback and possibly your shell history file. Clear the scrollback
## afterwards if that matters to you.
##
## The password is NOT printed: make cannot read it back out of the
## keystore, and echoing a password you typed would put it somewhere it
## does not need to be.
##
## Usage: make android-key-secrets
android-key-secrets:
	@test -f "$(KEYSTORE)" || (\
	  echo "No keystore at $(KEYSTORE)."; \
	  echo "Run 'make android-key' first, or set KEYSTORE=<path>."; \
	  exit 1)
	@echo "==> Verifying the keystore decodes cleanly"
	@# base64 -> decode -> keytool, because a corrupt secret otherwise
	@# surfaces in CI as an opaque Gradle signing error rather than as
	@# "the secret is wrong".
	@base64 -i "$(KEYSTORE)" | tr -d '\n' | base64 -d > /tmp/shikkhok-rt.jks
	@cmp -s "$(KEYSTORE)" /tmp/shikkhok-rt.jks \
	  && echo "    round-trip OK" \
	  || (echo "    ROUND-TRIP FAILED -- do not paste this."; \
	      rm -f /tmp/shikkhok-rt.jks; exit 1)
	@rm -f /tmp/shikkhok-rt.jks
	@echo ""
	@echo "GitHub -> Settings -> Environments -> android-release"
	@echo ""
	@echo "The ENVIRONMENT matters: without it, a workflow edit on any"
	@echo "branch could read this key."
	@echo ""
	@echo "--- Environment secrets -------------------------------------"
	@echo ""
	@echo "ANDROID_KEY_ALIAS"
	@echo "$(KEY_ALIAS)"
	@echo ""
	@echo "ANDROID_KEYSTORE_PASSWORD"
	@echo "  <the password you typed during 'make android-key'>"
	@echo ""
	@echo "ANDROID_KEY_PASSWORD"
	@echo "  <same, if you pressed Enter at the key password prompt>"
	@echo ""
	@echo "ANDROID_KEYSTORE_BASE64"
	@base64 -i "$(KEYSTORE)" | tr -d '\n'
	@echo ""
	@echo ""
	@echo "--- Environment variable ------------------------------------"
	@echo ""
	@echo "ANDROID_API_BASE_URL"
	@echo "https://api.shikkhokplus.nirmatabd.com"
	@echo ""
	@echo "-------------------------------------------------------------"
	@echo ""
	@echo "The base URL is a VARIABLE, not a secret: it appears in build"
	@echo "output and logs anyway, so hiding it would be theatre."
	@echo ""
	@echo "Then rehearse before spending a version number:"
	@echo "  Actions -> release-android -> Run workflow -> version: 0.2.0"

## Copy just the base64 keystore to the clipboard, on macOS.
## The value is long enough that selecting it from scrollback is where
## a truncated paste comes from -- and a truncated secret fails in CI
## as an opaque signing error.
android-key-copy:
	@test -f "$(KEYSTORE)" || (echo "No keystore at $(KEYSTORE)."; exit 1)
	@base64 -i "$(KEYSTORE)" | tr -d '\n' | pbcopy
	@echo "ANDROID_KEYSTORE_BASE64 is on the clipboard."
	@echo "Paste it into GitHub before copying anything else."

## The key's fingerprints and expiry.
##
## Prompts for the keystore password. keytool prints its own warning
## block ABOVE that prompt, so the password line scrolls out of sight
## and the command looks hung -- the echo below says so first.
android-key-info:
	@test -f "$(KEYSTORE)" || (echo "No keystore at $(KEYSTORE)."; exit 1)
	@echo "==> keytool will ask for the keystore password."
	@echo "    Its warning block prints first; type the password anyway."
	@echo ""
	@keytool -list -v -keystore "$(KEYSTORE)" -alias "$(KEY_ALIAS)" 2>/dev/null \
	  | grep -E "Alias name|Valid from|SHA1:|SHA256:" || true
	@echo ""
	@echo "Valid-until must be past 2033 or Play refuses the key."

.PHONY: android-key android-key-secrets android-key-copy android-key-info

# ---------------------------------------------------------------------
# An APK for a real phone
# ---------------------------------------------------------------------

## Which backend the APK talks to.
##
## **The default is staging, not localhost.** `10.0.2.2` is the
## emulator's route to this machine and means nothing on a phone: an
## APK built with it fails every request with a connection error, which
## reads as a broken app rather than a wrong address.
##
## Override for a backend running on this laptop, using the machine's
## LAN address — the phone must be on the same wifi:
##   make apk API=http://192.168.1.5:8000
API ?= https://api.shikkhokplus.nirmatabd.com

## Build a debug APK to sideload.
##
## Signed with Android's debug key, so it installs with no keystore and
## no password. **Not the artifact you ship**: R8 is off, so this build
## cannot surface a minification bug, and `make android-release-apk`
## exists for that.
##
## Usage: make apk
##        make apk API=http://192.168.1.5:8000
apk:
	@case "$(API)" in \
	  http://*|https://*) ;; \
	  *) echo "API must start with http:// or https:// — got '$(API)'"; exit 1 ;; \
	esac
	@echo "==> Building a debug APK against $(API)"
	@./gradlew :android:assembleDebug --no-daemon -PapiBaseUrl="$(API)"
	@echo ""
	@# **Asserted, because an unsigned APK will not install** and the
	@# phone's refusal says only "app not installed", which sends you
	@# looking at the phone rather than at the build.
	@#
	@# `apksigner`, not a META-INF grep: a debug APK is signed with
	@# APK Signature Scheme v2, which stores the signature OUTSIDE the
	@# zip entries, so a correctly signed APK has zero META-INF/*.RSA
	@# files. (An AAB is the opposite case and does carry them — which
	@# is why the release workflow greps and this does not.)
	@apksigner=$$(find $$ANDROID_HOME/build-tools \
	    /opt/homebrew/share/android-commandlinetools/build-tools \
	    $$HOME/Library/Android/sdk/build-tools \
	    -name apksigner 2>/dev/null | sort -r | head -1); \
	if [ -n "$$apksigner" ]; then \
	  "$$apksigner" verify android/build/outputs/apk/debug/android-debug.apk \
	    2>/dev/null \
	    && echo "Signed with the debug key." \
	    || { echo "NOT SIGNED — this will not install."; exit 1; }; \
	else \
	  echo "(apksigner not found; signature not checked)"; \
	fi
	@echo ""
	@ls -lh android/build/outputs/apk/debug/android-debug.apk | awk '{print "APK: " $$9 "  (" $$5 ")"}'
	@echo ""
	@echo "Install over USB:   make apk-install"
	@echo "Or copy that file to the phone and open it."
	@echo ""
	@echo "A sideloaded APK needs \"Install unknown apps\" allowed for"
	@echo "whichever app opens it — Files, Drive or your browser."

## Build and push to a USB-connected phone.
##
## `-r` reinstalls over an existing copy and keeps its data, so a
## second run does not make you sign in again.
##
## Usage: make apk-install
apk-install: apk
	@command -v adb >/dev/null 2>&1 || { \
	  echo "adb is not on PATH."; \
	  echo "Install platform-tools, or copy the APK to the phone by hand."; \
	  exit 1; }
	@test -n "$$(adb devices | sed -n '2,$$p' | grep -w device)" || { \
	  echo "No phone detected by adb."; \
	  echo ""; \
	  echo "On the phone: Settings -> About -> tap Build number seven"; \
	  echo "times, then Developer options -> USB debugging. Reconnect"; \
	  echo "and accept the prompt on the phone's screen."; \
	  exit 1; }
	@echo "==> Installing"
	@adb install -r android/build/outputs/apk/debug/android-debug.apk
	@echo ""
	@echo "Installed. Launching."
	@adb shell monkey -p com.shikkhokplus.app -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 || true

## Follow the app's log from a connected phone.
##
## Filtered to this app's own process, because an unfiltered logcat on
## a real phone is unreadable.
##
## Usage: make apk-log
apk-log:
	@command -v adb >/dev/null 2>&1 || { echo "adb is not on PATH."; exit 1; }
	@pid=$$(adb shell pidof com.shikkhokplus.app 2>/dev/null | tr -d '\r'); \
	if [ -z "$$pid" ]; then \
	  echo "The app is not running. Start it on the phone, then re-run."; \
	  exit 1; \
	fi; \
	echo "==> Logs for pid $$pid. Ctrl-C to stop."; \
	adb logcat --pid="$$pid"

## Build a RELEASE APK, signed with the upload key.
##
## **Use this to check what you actually ship.** R8 is on, so it
## catches the class of bug a debug build hides — a stripped
## serializer, a missing keep rule — and those surface only here.
##
## Needs the keystore password. A crash trace is obfuscated: read it
## with android/build/outputs/mapping/release/mapping.txt.
##
## Usage: make android-release-apk
android-release-apk:
	@test -f "$(KEYSTORE)" || { \
	  echo "No keystore at $(KEYSTORE). Run 'make android-key' first."; \
	  exit 1; }
	@case "$(API)" in \
	  https://*) ;; \
	  *) echo "A release build must use https — got '$(API)'."; \
	     echo "It carries phone numbers and OTPs over the public internet."; \
	     exit 1 ;; \
	esac
	@printf "Keystore password: "; \
	stty -echo; read pw; stty echo; echo ""; \
	ANDROID_KEYSTORE_PATH="$(KEYSTORE)" \
	ANDROID_KEYSTORE_PASSWORD="$$pw" \
	ANDROID_KEY_ALIAS="$(KEY_ALIAS)" \
	ANDROID_KEY_PASSWORD="$$pw" \
	./gradlew :android:assembleRelease --no-daemon \
	  -PapiBaseUrl="$(API)" \
	  -PversionName="$${VERSION:-0.0.0-local}" \
	  -PversionCode="$${CODE:-1}"
	@echo ""
	@ls -lh android/build/outputs/apk/release/*.apk 2>/dev/null | awk '{print "APK: " $$9 "  (" $$5 ")"}'

.PHONY: apk apk-install apk-log android-release-apk
