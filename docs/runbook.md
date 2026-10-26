# Runbook

## Backend (local)

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements.lock
.venv/bin/pip install -e '.[test]'
docker run -d --name meetsaathi-pg -e POSTGRES_PASSWORD=postgres_dev_only -e POSTGRES_DB=meetsaathi -p 55432:5432 pgvector/pgvector:pg16
MS_ENV=dev .venv/bin/python -m app.migrate            # creates ms_app / ms_worker roles and applies migrations
MS_ENV=dev .venv/bin/uvicorn app.main:app --port 8080  # dev runs the job worker inline (MS_RUN_INLINE_WORKER=true)
.venv/bin/python -m pytest -q                          # resets the dev database; do not run against a live development session
```

AWS production deployment and operational gaps: see [deployment.md](deployment.md).

Production runs the worker separately: `python -m app.workers.runner` (see `infra/docker-compose.yml`). With `MS_ENV=prod` the
process refuses to start with development secrets.

Health: `GET /v1/health` reports which providers are available (never secrets).

## Android

```bash
cd apps/android
# Use Java 21 (Gradle/Kotlin here do not support running on Java 25).
./gradlew :app:testDebugUnitTest :app:assembleDebug -Pmeetsaathi.apiBaseUrl=https://api.example
```

Debug builds default to `http://10.0.2.2:8080` (emulator → host). Release builds only allow HTTPS (network security config).

## iOS

```bash
cd apps/ios
swift test                     # MeetSaathiKit unit tests on macOS
xcodegen generate              # creates MeetSaathi.xcodeproj (needs Xcode + iOS SDK)
open MeetSaathi.xcodeproj
```

Set `MS_API_BASE_URL` per configuration in `project.yml`. Background mode `audio` lets an already-started, visible session continue
while locked; the app never starts capture in the background.

## Operations

- Jobs: `job_outbox` rows move `READY → LEASED → DONE`, retry with exponential backoff and become `DEAD` after `max_attempts`.
  Dead finalization moves the session to `FINALIZATION_RETRYABLE` (user can retry without re-recording); dead purges mark the
  deletion request `ACTION_REQUIRED`.
- Retention sweep runs every minute: un-kept EPHEMERAL sessions expire after 24 h; raw audio after its retention window.
- Deletion: access is revoked in the request transaction; `GET /v1/deletion-requests/{id}` reports `REQUESTED → IN_PROGRESS → COMPLETE`.
