# Technology Stack — ShikkhokPlus

Full rescan, 2026-11-13, commit `cb20fd1`. Versions are the declared pins (`pyproject.toml`, `gradle/libs.versions.toml`, `web/package.json`); the resolved, hash-locked set lives in the lockfiles listed in `dependencies.md`.

## Languages and runtimes

| Surface | Language | Runtime / target | Evidence |
|---|---|---|---|
| Backend | Python 3.12 | `python:3.12-slim-bookworm` pinned by digest; `requires-python >=3.12`; Ruff `py312`; mypy `python_version = 3.12` | `Dockerfile:31,74`, `pyproject.toml` |
| Database | SQL (PostgreSQL 16) | RDS PostgreSQL 16, storage encrypted; local and test: PostgreSQL 16 container | `infra/modules/database/main.tf:88,95`, `docker-compose.yml`, testcontainers |
| Android | Kotlin 2.0.21 | AGP 8.7.3, `compileSdk`/`targetSdk` 36 (project.md mandate), namespace `com.shikkhokplus.app` | `gradle/libs.versions.toml`, `android/build.gradle.kts` |
| Web | TypeScript 5.9.3 | Node >= 20, React 19.3.1, Vite 7.3.7, PWA | `web/package.json` |
| Site | JavaScript (Node >= 22 build script) | static HTML output | `site/package.json` |
| Infrastructure | HCL (Terraform) | AWS | `infra/versions.tf` |

The local interpreter in this environment is Python 3.13; the container and CI run 3.12 (team.md environment note still applies).

## Backend frameworks and libraries (`pyproject.toml [api]`)

| Library | Version | Purpose |
|---|---|---|
| fastapi | 0.162.0 | HTTP framework, OpenAPI generation |
| pydantic | 2.14.2 | Wire models and validation |
| sqlalchemy | 2.1.6 | ORM, raw SQL with bound parameters |
| alembic | 1.20.1 | Migrations |
| psycopg[binary] | 3.3.6 | PostgreSQL driver |
| pyjwt | 2.15.1 | HS256 tokens |
| httpx | 0.28.1 | Outbound HTTP to the SMS gateway |
| uvicorn[standard] | 0.54.0 | ASGI server |
| cryptography | 50.0.2 | AES-256-GCM for authenticator secrets |

Standard library carries the rest of the security primitives: `hashlib.scrypt` for passwords, `hmac` for OTP and refresh-token digests, `secrets` for codes (`app/auth/passwords.py` imports `hashlib`, `hmac`, `secrets`; stored form `scrypt$N$r$p$salt$hash`, N=2^14, r=8, p=5).

## Backend tooling (`pyproject.toml [dev]`)

pytest 9.2.0, pytest-cov 7.1.0, hypothesis 6.170.13, testcontainers[postgres] 4.15.0, ruff 0.17.3, mypy 2.4.1, pip-tools 7.6.2 (lockfile), pip-audit 2.10.1 (CVE scan). Build backend: hatchling.

## Android libraries (`gradle/libs.versions.toml`)

| Library | Version | Purpose |
|---|---|---|
| Compose BOM | 2024.10.01 | UI |
| activity-compose / lifecycle-viewmodel-compose / navigation-compose | 1.9.3 / 2.8.7 / 2.8.5 | Activity, ViewModel, navigation |
| kotlinx-coroutines | 1.9.0 | Async |
| kotlinx-serialization | 1.7.3 | JSON (money as string only) |
| Ktor client (OkHttp engine) | 2.3.12 | HTTP (chosen over Retrofit to avoid KSP) |
| androidx.security:security-crypto | 1.1.0-alpha06 | EncryptedSharedPreferences for the refresh token |
| WorkManager | 2.9.1 | 15-minute unread check (admission note `android/sdk-admissions/workmanager.md`) |
| Robolectric | 4.14.1 | Compose UI tests on the JVM |
| spotless / ktlint / detekt | 6.25.0 / 1.5.0 / 1.23.7 | Format and static analysis |
| JaCoCo (Gradle plugin) | bundled | Kotlin coverage report and ratchet |

Security floors pin transitive test/tooling dependencies (netty, bouncycastle, guava, protobuf-java, commons-io) raised after a 2026-11-08 release-gate scan.

No Firebase Analytics, Crashlytics or ads SDK (project.md Forbidden); no `firebase` entry appears in `android/build.gradle.kts` or the version catalogue. FCM is used from the server side (`app/notifications/fcm.py`); how the client receives pushes was not traced this run.

## Web libraries (`web/package.json`)

Runtime: react 19.3.1, react-dom 19.3.1, react-router 7.18.5, qrcode-generator 2.0.4. Dev: vite 7.3.7, vite-plugin-pwa 1.3.0, workbox-window 7.4.1, vitest 4.1.12, Testing Library, jsdom 27.4.0, typescript 5.9.3, eslint 9.39.5 + typescript-eslint 8.72.1, prettier 3.9.10, openapi-typescript 7.13.0.

## Cloud and external services

| Service | Use | Evidence |
|---|---|---|
| AWS EC2 (instance refresh), CloudFront, ECR, RDS PostgreSQL 16, S3, SES, SSM Parameter Store, Lambda, Budgets | Hosting, CDN, images, database, static apps, email, secrets, seeder, cost guard | `infra/`, `deploy/README.md` |
| BulkSMSBD | SMS delivery of codes | `app/gateway/bulksmsbd.py` |
| Firebase Cloud Messaging | Push | `app/notifications/fcm.py` |
| GitHub Actions (OIDC to AWS) | CI and deploys | `.github/workflows/` |
| OWASP ZAP | API scan before promotion | `.github/workflows/security-scan.yml` |
| osv-scanner, pip-audit, ECR image scan, Syft | CVE annotation and release gate, Android SBOM | `check.yml`, `deploy.yml`, `release-android.yml` |
| Gitleaks | Secret scan on every push | `check.yml` |

## Relevance to the username intent

No new library is needed for a username column, a case-insensitive unique index, or a reserved-name table: PostgreSQL 16 supports functional unique indexes (`lower(username)`) and the project already stores canonical lowercase values with plain `UNIQUE` (`uq_account_email`). There is no `citext` extension in the migrations. Any new dependency must pass the forbidden-identifier admission check (project.md Mandated).
