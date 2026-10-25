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

FROM python:3.15-slim-bookworm AS build

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

COPY pyproject.toml README.md* ./
COPY app ./app

# Installed into a virtualenv so the whole dependency closure can be
# copied to the runtime stage as one directory.
RUN python -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --upgrade pip \
    && /venv/bin/pip install --no-cache-dir '.[api]'


FROM python:3.15-slim-bookworm AS runtime

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
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
