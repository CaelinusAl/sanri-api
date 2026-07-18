# SANRI API — Operations Manual

**Audience:** The person who runs this system in a non-dev environment  
**Companion evidence:** `releases/REP-001/`  
**Frozen tip for recovery security core:** `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab` (`pmp01a37-complete`)  
**Last updated:** 2026-07-18  

```text
Authority Level: Level 5 — Operations
Source of Truth: This manual for day-2 operations
Depends On: REP-001, Release Constitution, PMP-01 plan
```

**Hard rules**

1. Production migration / automatic linking are **DISABLED** until
   `PMP-01A-BLK-001` is resolved and the release gate is opened by Council.  
2. Never run recovery mutations without PostgreSQL (`DATABASE_URL` must be
   Postgres — do not rely on SQLite fallback in any shared environment).  
3. Never disable the append-only audit trigger in production without an
   incident ticket and dual approval.  
4. Never paste secrets into tickets, chat, or REP attachments.

---

## 1. What you are operating

| Component | How it runs today |
|---|---|
| API | FastAPI + uvicorn (`app.main:app`) |
| Container | `Dockerfile` → Python 3.12-slim, port `${PORT:-8000}` |
| Platform | Railway (`railway.json` → DOCKERFILE builder) |
| Database | PostgreSQL via `DATABASE_URL` (Supabase or managed PG) |
| Migrations | Alembic (`alembic.ini`, `migrations/`) |
| Recovery API | `/v1/recovery/*` (JWT reviewer role required) |

Liveness endpoints:

- `GET /health` → `{"status":"ok"}`  
- `GET /health/scheduler`  
- `GET /` → status  

There is **no** DB readiness probe and **no** `/metrics` endpoint at this tip.
Treat `/health` as process-up only.

---

## 2. Prerequisites (before any deploy)

### 2.1 Required environment variables

Minimum for a shared/staging API with recovery enabled:

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | **YES** | Must be `postgresql+psycopg2://...` (or `postgresql://...`) — **not** SQLite |
| `SUPABASE_JWT_SECRET` | **YES** | Server-only |
| `SUPABASE_JWT_AUDIENCE` | YES | Default `authenticated` |
| `SUPABASE_JWT_ISSUER` | YES | Project issuer URL |
| `RECOVERY_REVIEWER_ROLE` | YES | Default `recovery_reviewer` |
| `RECOVERY_ASSERTION_SIGNING_SECRET` | **YES** (non-empty) | Fail-closed at sign time if empty |
| `OPENAI_API_KEY` | if chat/AI used | Server-only |
| `SANR_ALLOWED_ORGNS` / CORS origins | recommended | See `.env.example` |

Full template: `.env.example`.

### 2.2 Pre-flight checklist

- [ ] `DATABASE_URL` points to the intended **non-prod** or approved DB  
- [ ] Signing secret set and stored in the platform secret store  
- [ ] JWT secret/issuer match the Auth project  
- [ ] Alembic current revision known (`alembic current`)  
- [ ] Backup taken if the DB already has data (see §5)  
- [ ] Release gate still treated as **CLOSED** (no production linking)  
- [ ] `_check_all.py` is **not** used in production (contains unsafe default URL pattern)

---

## 3. Deployment

### 3.1 Build

Platform builds from `Dockerfile`:

```dockerfile
# installs requirements, copies app/ + migrations/ + alembic.ini
# CMD: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

Local equivalent:

```bash
docker build -t sanri-api:local .
docker run --rm -p 8000:8000 --env-file .env sanri-api:local
```

### 3.2 Schema migrate (mandatory)

The app may call `Base.metadata.create_all` on startup for some models.
**Recovery case/audit tables (0006/0007) must be applied via Alembic.**

```bash
# from repo root, with DATABASE_URL set to Postgres
alembic current
alembic history
alembic upgrade head
alembic current   # expect 0007 / recovery_audit_events revision
```

Recovery-relevant revisions:

```text
0004 recovery_assertions
0005 recovery_links
0006 recovery_cases
0007 recovery_audit_events   ← tip schema for A.3.7
```

### 3.3 Post-deploy verify

```bash
curl -sS https://<host>/health
# optional: OpenAPI has /v1/recovery routes
curl -sS https://<host>/docs
```

Negative checks:

- Unauthenticated `POST /v1/recovery/...` → 401/403  
- Reviewer without role → rejected  
- Confirm `DATABASE_URL` is Postgres (not `sqlite:///./dev.db`)

### 3.4 Traffic / flags

| Control | Safe default |
|---|---|
| Automatic linking | **DISABLED** — do not enable |
| Release gate | **CLOSED** — Council only |
| `V1_CHAT_PERCENTAGE` | keep at approved value (often `0`) |
| `LEGACY_MEMORY_WRITE_ENABLED` | `false` unless exception approved |

---

## 4. Restart

### 4.1 Application restart

On Railway (or equivalent): restart the service from the platform UI/CLI.
The process is stateless relative to durable recovery data (Postgres holds state).

```bash
# platform-specific; example pattern
railway restart
# or redeploy same image
```

### 4.2 After restart — verify

1. `GET /health` returns ok  
2. `alembic current` still at expected revision (restart does not migrate)  
3. Spot-check: an existing recovery case still readable via reviewer API  
4. Confirm no accidental SQLite file appeared in the container filesystem

### 4.3 What restart does **not** do

- Does not roll back schema  
- Does not clear audit ledger  
- Does not revoke recovery links  
- Does not rotate secrets  

---

## 5. Backup

### 5.1 What must be backed up

| Asset | Why |
|---|---|
| PostgreSQL database | Cases, assertions, links, audit, V1 data |
| Platform env/secrets | JWT, signing secret, DB URL |
| Alembic revision id | Needed for restore compatibility |

### 5.2 Logical backup (Postgres)

Prefer the managed provider’s automated backups (Supabase / Railway Postgres).
Additionally, take a manual dump before schema changes:

```bash
# Example — adjust connection to your provider
pg_dump "$DATABASE_URL_FOR_PGDUMP" \
  --format=custom \
  --file="sanri-backup-$(date +%Y%m%d-%H%M%S).dump"
```

If `DATABASE_URL` uses `postgresql+psycopg2://`, strip the `+psycopg2` driver
suffix for `pg_dump` / `psql`.

### 5.3 Backup checklist

- [ ] Dump completes without error  
- [ ] File stored off-box (object storage / encrypted volume)  
- [ ] Record: timestamp, DB name, `alembic_version`, git tip/tag  
- [ ] Do **not** commit dumps to git  

### 5.4 Audit ledger note

`v1_recovery_audit_events` is append-only in normal operation. Backups are the
only legitimate bulk-copy path. Do not `DELETE`/`UPDATE` audit rows in prod.

---

## 6. Restore

### 6.1 Preconditions

- [ ] Incident or approved maintenance window  
- [ ] Target DB is the intended environment (never restore prod dump onto a
  shared scratch DB without renaming)  
- [ ] Application stopped or in maintenance (avoid writes during restore)  
- [ ] You know the Alembic revision that matches the dump  

### 6.2 Restore procedure (logical dump)

```bash
# 1. Stop writers (scale to 0 / maintenance mode)

# 2. Restore
pg_restore --clean --if-exists --no-owner --no-privileges \
  -d "$DATABASE_URL_FOR_PGDUMP" \
  sanri-backup-YYYYMMDD-HHMMSS.dump

# 3. Verify schema revision
alembic current

# 4. Start API
# 5. GET /health
# 6. Reviewer smoke: read an expected case id (if any)
```

### 6.3 Post-restore verification

| Check | Expected |
|---|---|
| `alembic current` | Matches backup record |
| Append-only trigger exists | `v1_recovery_audit_events_append_only_trg` |
| Sample `UPDATE` on audit table | Rejected |
| Recovery API auth | Still fail-closed without JWT |

### 6.4 If restore is partial / failed

1. Do not open traffic.  
2. Re-restore from last known good dump.  
3. Escalate — PMP-01E Rollback Engine is **not** implemented; restore is
   operator-driven.

---

## 7. Incident response

### 7.1 Severity guide

| Severity | Examples | First action |
|---|---|---|
| SEV-1 | Suspected cross-user association; secret leak; audit trigger disabled | Stop recovery writes; rotate secrets; page Security/Identity |
| SEV-2 | Recovery API 5xx; DB unavailable; migration stuck | Restart / failover DB; freeze deploys |
| SEV-3 | Single reviewer blocked; non-security bug | Ticket; no schema experiments in prod |

### 7.2 Immediate actions (any SEV-1/2)

1. **Contain** — disable traffic to recovery if needed (platform / reverse proxy).  
2. **Preserve** — do not drop tables; take a fresh backup if DB is still healthy.  
3. **Record** — timeline, tip SHA/tag, `alembic current`, error samples (redact secrets).  
4. **Decide** — restart vs restore vs schema rollback (see §8).  

### 7.3 Security-specific incidents

| Symptom | Likely area | Action |
|---|---|---|
| Client can set reviewer identity | Contract break | Block route; do not hotfix policy into client |
| Duplicate case / double link | Idempotency / race | Capture `operation_key`; inspect ops + audit tables |
| Audit row missing after success | TX boundary break | Treat as SEV-1; freeze recovery |
| Raw token in logs/audit detail | Redaction break | Rotate link; scrub logs; SEV-1 |
| Legacy client `user_id` accepted on old routes | BLK-001 / containment | Fail-closed those routes; do **not** “fix” with auto-link |

### 7.4 Contacts / ownership

| Area | Owner |
|---|---|
| Recovery security contracts | Security / Identity Authority |
| Deploy / DB / backups | Operations |
| BLK-001 trust model | PMP-01 Program (see blocker brief) |

---

## 8. Rollback

There are **three different rollbacks**. Do not confuse them.

### 8.A Application rollback (code)

Redeploy the previous known-good image/commit (e.g. prior tag).

```text
Preferred freeze tags:
  pmp01a37-complete  ← current security-core tip
  pmp01a36-complete
  pmp01a35-complete
  pmp01a34-complete
```

```bash
# example: redeploy image built from tag
git checkout pmp01a36-complete
# build + deploy via platform
```

**When:** bad app release, logic regression, not a data corruption event.

### 8.B Schema rollback (Alembic)

Only with backup + approval. Example: undo audit ledger migration:

```bash
alembic downgrade 20260718_0006_recovery_cases   # or revision id for 0006
# verifies in A.3.8: drops trigger, function, v1_recovery_audit_events
```

**Effects of 0007→0006:** audit table/trigger removed. Case ledger remains.  
**Do not** downgrade past a revision that still has required production data
without a restore plan.

Re-upgrade:

```bash
alembic upgrade head
```

### 8.C Data rollback (restore)

Use §6 Restore from dump. This is the only path that restores row contents.
PMP-01E automated rollback engine is **NOT_STARTED**.

### 8.D Rollback decision tree

```text
Bad deploy, DB healthy     → 8.A app rollback
Bad migration, backup OK   → stop traffic → 8.B or 8.C
Data corruption / unknown  → stop traffic → 8.C restore → verify → restart
Identity / linking incident→ stop linking (already disabled) → Security + BLK-001 owners
```

---

## 9. Day-2 recovery operator cheat sheet

| Task | Command / action |
|---|---|
| Is API up? | `curl /health` |
| Schema revision? | `alembic current` |
| Apply migrations | `alembic upgrade head` |
| Backup | `pg_dump` / provider snapshot |
| Restart | platform restart |
| Reviewer call | JWT with `recovery_reviewer` role → `/v1/recovery/*` |
| Forbidden | automatic linking, ad-hoc SQL to mark identities `verified` |

---

## 10. Related documents

| Doc | Path |
|---|---|
| REP-001 | `releases/REP-001/REP.md` |
| A.3.8 validation | `releases/REP-001/a38-postgresql-validation.md` |
| BLK-001 focus | `docs/blockers/PMP-01A-BLK-001.md` |
| PMP execution plan | `docs/pmp-01-secure-migration-execution-plan.md` |
| Env template | `.env.example` |
