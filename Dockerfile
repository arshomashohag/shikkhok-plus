# The backend image.
#
# **Multi-stage, and the split is a security control rather than a size
# optimization.** The build stage carries a compiler and the full pip
# toolchain; the runtime stage carries neither, so a vulnerability in a
# build tool is not shipped to the host that serves children's data.
#
# The image is tagged with the commit SHA by the deploy workflow and
# `latest` is never deployed [team.md Deployment]. That is what makes a
# rollback "redeploy the previous tag" rather than "rebuild and hope",
# and it is also a supply-chain control: it makes the deployed artifact
# identifiable.
#
# **Migrations do not run here.** Alembic runs as a distinct, logged
# deploy step before this container serves traffic, never as a side
# effect of application start [team.md]. A container that migrates on
# boot migrates once per replica, races itself, and gives the operator
# no place to stop between the backup and the schema change.

# **3.12, pinned by digest, in both stages.** The project targets 3.12
# everywhere -- `requires-python`, Ruff, mypy, the CI interpreter and
# the lockfile header -- and this line had been bumped to 3.15 by a
# Dependabot base-image PR, so production ran an interpreter no test
# had ever run on [OPS-13]. The digest is the multi-arch index for
# `3.12-slim-bookworm` (read from the registry 2026-11-02), so arm64 and
# amd64 builds resolve the same release; Dependabot refreshes it weekly
# and `.github/dependabot.yml` refuses minor and major Python bumps.
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS build

# Fail the build on a non-zero exit anywhere in a pipeline, not just the
# last command. Without this a failed download followed by a successful
# tar reports success.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

WORKDIR /build

# gcc and the libpq headers are needed to build psycopg's C extension.
# They stay in THIS stage and never reach the runtime image.
RUN apt-get update \
    && apt-get install --no-install-recommends -y gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# **The hashed lockfile, and nothing resolved here.** This was
# `pip install '.[api]'`, a fresh resolve at build time: the image ran
# whatever versions PyPI served that day rather than the set CI tested
# and pip-audit scanned. `--require-hashes` installs exactly the pins in
# requirements.txt and refuses any artifact whose sha256 differs, which
# is what detects a substituted wheel [team: Deployment].
#
# The lockfile is compiled with `--extra dev --extra api`, so the dev
# tools (pytest, mypy, ruff, pip-audit, ...) are in this venv too. That
# is accepted deliberately: it is the exact set the suite ran against,
# and a separate api-only lock would be a second file to keep current
# with no CI check behind it yet.
#
# No `pip install --upgrade pip`: an unpinned upgrade is a resolve
# outside the lockfile, which is the thing this stage exists to stop.
COPY requirements.txt ./
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --require-hashes -r requirements.txt

# **The project itself is NOT pip-installed.** `pip install --no-deps .`
# would build it with hatchling fetched by build isolation -- unpinned
# and unhashed, the one dependency of the image outside the lockfile.
# The package is pure source with no entry points and no package data
# (`[tool.hatch.build.targets.wheel] packages = ["app"]`), so the
# runtime stage puts /srv on PYTHONPATH instead and imports it from
# there.


FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS runtime

# libpq5 is the RUNTIME library psycopg links against -- the -dev
# package from the build stage is not needed and is not installed.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libpq5 \
    && rm -rf /var/lib/apt/lists/*

# A non-root user. A container process running as root that is
# compromised owns the container; one running as `app` does not.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 app

COPY --from=build /venv /venv
WORKDIR /srv
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

USER app

ENV PATH="/venv/bin:$PATH" \
    PYTHONPATH=/srv \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# The health endpoint reports database connectivity and the applied
# migration revision, so an unhealthy container is one that cannot serve
# rather than one that merely started.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# Workers, plural, deliberately. team.md records that a single host
# still runs multiple Uvicorn workers, which is why the OTP rate-limit
# counters are datastore-backed rather than per-process -- a per-process
# dictionary passes every test and silently stops working here.
#
# **Forwarded headers are NOT trusted.** This was `--proxy-headers
# --forwarded-allow-ips "*"`, which believes an X-Forwarded-For from any
# peer -- and nginx appends to the client's own X-Forwarded-For rather
# than replacing it, so any caller could choose the IP the per-IP OTP
# ceiling counted against. The client address now arrives in
# X-Client-Address, which nginx always OVERWRITES from CloudFront's
# CloudFront-Viewer-Address, and the application reads it only when
# SHIKKHOKPLUS_TRUSTED_CLIENT_IP_HEADER names it.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--no-proxy-headers"]
