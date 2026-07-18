# Annex — A.3.8 PostgreSQL Operational Validation

**Milestone:** PMP-01A.3.8  
**Result:** `PASS`  
**Date:** 2026-07-18  
**Tip:** `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab`  
**Product code changes:** none  
**Baseline suite after validation:** 91 passed (SQLite A.3.1–A.3.7)

## Environment

| Item | Value |
|---|---|
| Engine | PostgreSQL 15 (Docker, local) |
| Database | `sanri_dryrun` |
| Host | `127.0.0.1:55432` |
| Classification | Non-production |

Early Alembic revisions stubbed as in A.3.6 dry-run; validated cycle starts at **0006**.

## Results

| Area | Result |
|---|---|
| Alembic 0006→0007→0006→0007 | PASS |
| Orphan objects after downgrade | PASS (0 tables / functions / triggers) |
| Schema constraints + RLS | PASS |
| Append-only UPDATE/DELETE | PASS (rejected) |
| INSERT still valid | PASS |
| Audit-failure rollback (case / assertion / link / evidence) | PASS |
| Restart persistence | PASS |
| Concurrent identical `operation_key` | PASS (1 case, 1 op, 1 audit) |
| Security redaction | PASS |
| Architecture / security contract | **NO CHANGE** |

## Schema checks

- `UNIQUE (case_id, operation_key, event_type)` → `v1_recovery_audit_events_case_op_type_uq`
- Partial uniques: `v1_recovery_cases_one_open_subject`, `v1_recovery_cases_one_open_legacy`
- FK: `v1_recovery_case_operations.case_id → v1_recovery_cases.case_id`
- NOT NULL on audit core columns; `detail` = jsonb; `state_version integer NOT NULL DEFAULT 0`
- RLS enabled; deny-all for `authenticated` on cases / operations / audit events

## Trigger checks

- `BEFORE UPDATE OR DELETE` → `v1_recovery_audit_events_append_only_trg`
- Function: `public.v1_recovery_audit_events_append_only()`
- Downgrade removes trigger + function; re-upgrade recreates both

## Remaining risks (accepted for A.3.8 freeze)

1. Full Alembic from `0001` still needs Supabase (`vector`, `auth.users`).  
2. Live Supabase RLS with real JWT roles not re-run.  
3. Concurrent pre-commit races may surface open-case conflict instead of soft replay.  
4. Append-only bypass only via superuser / trigger disable (ops control).
