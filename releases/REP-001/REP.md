# REP-001 — Release Evidence Package

**Package ID:** `REP-001`  
**Release train:** Alpha (security-core freeze — not production ship)  
**Status:** `BLOCKED`  
**Release Owner:** PMP-01 Program Governance  
**Evidence date:** 2026-07-18  
**Repository:** `sanri-api`  
**Repository revision:** `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab`  
**Freeze tag:** `pmp01a37-complete`  
**Release directory:** `releases/REP-001/`  
**Related assessment:** PMP-01A A.3.9 Release Readiness → **NO-GO**

```text
Authority Level: Level 5 — Operations
Owner: Release Owner / Release Council
Source of Truth: This REP for the tip above
Supersedes: None (first REP)
Depends On: Release Constitution, Governance Framework, SDS, SLS,
            docs/pmp-01-secure-migration-execution-plan.md
Referenced ADRs: docs/adr/README.md (bodies not yet in tip — see §10)
Lifecycle State: Operational evidence record
Last Reviewed: 2026-07-18
```

This document is the **single authoritative evidence pack** for the PMP-01A.3
security-core freeze (A.3.1–A.3.8). Missing evidence is a blocker, not an
implicit pass.

**Council decision (this pack):** `BLOCKED` — engineering security core is
evidence-ready; production release remains blocked by `PMP-01A-BLK-001` and
open governance items listed in §12–§13.

---

## 0. One-page verdict

| Question | Answer |
|---|---|
| Security core A.3.1–A.3.7 implemented? | **YES** |
| 91 A.3 unit/integration tests PASS? | **YES** (2026-07-18 reconfirm) |
| A.3.8 real PostgreSQL operational validation PASS? | **YES** (2026-07-18) |
| Architecture / security contract changed in A.3.8–A.3.9? | **NO / NO** |
| Release gate open? | **NO — CLOSED** |
| Automatic linking enabled? | **NO — DISABLED** |
| Production migration authorized? | **NO** |
| Remaining Critical technical/trust blocker? | **`PMP-01A-BLK-001`** |
| Final REP status | **`BLOCKED`** |

---

## 1. Scope and change inventory

### Release objective

Freeze and evidence the PMP-01A.3 Manual Recovery **security core**:

- A.3.1 Reviewer API  
- A.3.2 Signed Assertion Store  
- A.3.3 Four-eyes Approval  
- A.3.4 Recovery Link Lifecycle  
- A.3.5 Recovery UI (thin client)  
- A.3.6 Durable Case Ledger  
- A.3.7 Durable Append-only Audit Ledger  
- A.3.8 PostgreSQL Operational Validation (assessment)  
- A.3.9 Release Readiness Assessment (assessment — this pack)

### Included (user-visible / operator-visible)

- Reviewer-authenticated recovery API under `/v1/recovery/*`
- Thin recovery console (HTML) — display / start operations only
- Durable PostgreSQL tables for cases, operations, assertions, links, audit
- Append-only DB trigger on `v1_recovery_audit_events`

### Included (infrastructure / database)

| Revision | File | Purpose |
|---|---|---|
| 0004 | `migrations/versions/20260718_0004_recovery_assertions.py` | Signed assertions |
| 0005 | `migrations/versions/20260718_0005_recovery_links.py` | Recovery links |
| 0006 | `migrations/versions/20260718_0006_recovery_cases.py` | Durable case ledger |
| 0007 | `migrations/versions/20260718_0007_recovery_audit_events.py` | Append-only audit |

### Explicitly excluded

- Production identity migration / mapping writes  
- Automatic linking  
- Opening the release gate  
- PMP-01B Migration Engine and later packages  
- Resolution of `PMP-01A-BLK-001`  
- Architecture or security-contract changes in A.3.8 / A.3.9  

### Changed repositories

| Repo | Role in this REP |
|---|---|
| `sanri-api` @ `f7cc6b3` | **In scope** — evidence tip |
| `asksanri-mobile` | Out of scope for A.3 security core (client containment referenced in PMP-01A.1) |
| `asksanri-frontend` | PMP-01A.2 closed `NOT_VERIFIABLE` — not a PASS |

### Feature flags / rollout

| Flag / control | Value at tip | Notes |
|---|---|---|
| Release gate | `CLOSED` | Governance — not a runtime env flag |
| Automatic linking | `DISABLED` | No production writers at tip |
| `V1_CHAT_PERCENTAGE` | `0` (example) | Unrelated to recovery gate |
| `RECOVERY_REVIEWER_ROLE` | `recovery_reviewer` | Server-side role claim |
| `RECOVERY_ASSERTION_SIGNING_SECRET` | required non-empty for sign | Fail-closed if empty at sign time |

### Production traffic status

**Not authorized.** This REP does not ship production migration traffic.

---

## 2. Build and test results

### 2.1 A.3.1–A.3.7 suite (authoritative for this freeze)

**Command:**

```bash
python -m pytest \
  tests/test_pmp01a31_reviewer_api.py \
  tests/test_pmp01a32_assertion_store.py \
  tests/test_pmp01a33_four_eyes_workflow.py \
  tests/test_pmp01a34_recovery_link_lifecycle.py \
  tests/test_pmp01a35_recovery_ui_thin_client.py \
  tests/test_pmp01a36_durable_case_ledger.py \
  tests/test_pmp01a37_durable_audit_ledger.py \
  -q
```

**Result (2026-07-18, tip `f7cc6b3`, worktree `sanri-api-a37`):**  
`91 passed, 9 warnings in ~2.3s`

| File | Tests | Package |
|---|---:|---|
| `tests/test_pmp01a31_reviewer_api.py` | 14 | A.3.1 |
| `tests/test_pmp01a32_assertion_store.py` | 16 | A.3.2 |
| `tests/test_pmp01a33_four_eyes_workflow.py` | 9 | A.3.3 |
| `tests/test_pmp01a34_recovery_link_lifecycle.py` | 15 | A.3.4 |
| `tests/test_pmp01a35_recovery_ui_thin_client.py` | 8 | A.3.5 |
| `tests/test_pmp01a36_durable_case_ledger.py` | 12 | A.3.6 |
| `tests/test_pmp01a37_durable_audit_ledger.py` | 17 | A.3.7 |
| **Total** | **91** | |

| Area | Command | Result | Owner |
|---|---|---|---|
| Backend A.3 suite | command above | **91 PASS** | Engineering |
| Backend full pytest | `python -m pytest -q` | Not claimed as freeze gate (broader suite may include skips) | Engineering |
| Backend type/compile | not a freeze gate for A.3.9 | N/A this pack | — |
| Mobile / Web | out of A.3 security-core scope | N/A this pack | — |
| Pytest CI workflow | absent at tip (only `daily_stream.yml`) | **GAP** | Operations |

### 2.2 A.3.8 PostgreSQL operational validation

**Status:** `PASS`  
**Date:** 2026-07-18  
**Target:** local Docker PostgreSQL 15, DB `sanri_dryrun`, non-production  
**Tip:** `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab`  
**Detail annex:** `a38-postgresql-validation.md`

| Check | Result |
|---|---|
| Alembic 0006→0007→0006→0007 | PASS |
| Orphan objects after downgrade | PASS |
| Schema constraints + RLS | PASS |
| Append-only UPDATE/DELETE rejected | PASS |
| INSERT still valid | PASS |
| Audit-failure rollback (case/assertion/link/evidence) | PASS |
| Restart persistence | PASS |
| Concurrent identical `operation_key` | PASS (single winner) |
| Security redaction (allowlist detail) | PASS |
| Architecture / security contract | **NO CHANGE** |

**Known A.3.8 scope limits (accepted for freeze):**

1. Full Alembic from `0001` still needs Supabase (`vector`, `auth.users`) — cycle validated from stubbed base at **0006**.  
2. Live Supabase RLS with real JWT roles not re-run (`SUPABASE_RLS_RUN` opt-in).  
3. Concurrent pre-commit races may surface open-case conflict instead of soft replay; durability still single-winner.  
4. Append-only is DB-enforced for table owners; bypass only via superuser / trigger disable.

---

## 3. Commits (freeze lineage)

### 3.1 Tagged freeze points

| Tag | Commit | Subject |
|---|---|---|
| `pmp01a34-complete` | `5c9f653699d67ae6b79a613bb9ee1c5a05d28aff` | freeze PMP-01A.3.4 security core |
| `pmp01a35-complete` | `c3c9d6d107434b4bb1eea89f1b60385685585760` | thin Recovery UI over frozen A.3.4 core |
| `pmp01a36-complete` | `99ad3262dc44cdff9f066d306974430ae4e73c69` | durable case ledger for PMP-01A.3.6 |
| `pmp01a37-complete` | `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab` | durable append-only audit ledger for PMP-01A.3.7 |

**Evidence tip for this REP = `pmp01a37-complete` = `f7cc6b3`.**

### 3.2 PMP-01A execution commits (ordered, tip-ward)

```text
4409627 docs(pmp): record PMP-01A identity blocker
d16201c security(identity): contain untrusted legacy identity signals
580a2de docs(pmp): record PMP-01A execution gaps and release risks
9fc916d docs(pmp): record PMP-01A.1 containment evidence
413d463 docs(pmp): define PMP-01A.2 and PMP-01A.3 execution gates
e7c6830 docs(pmp): close PMP-01A.2 as not verifiable
b6500b1 docs(pmp): lock PMP-01A.3 operational contract before implementation
e26c37f docs(pmp): concretize PMP-01A.3 recovery contract
48b70d0 docs(pmp): mark PMP-01A.3 implementation-ready after edge-case review
5c9f653 feat(recovery): freeze PMP-01A.3.4 security core at pmp01a34-complete
c3c9d6d feat(recovery): add thin Recovery UI over frozen A.3.4 core
99ad326 feat(recovery): add durable case ledger for PMP-01A.3.6
f7cc6b3 feat(recovery): add durable append-only audit ledger for PMP-01A.3.7
```

A.3.8 and A.3.9 produced **no product commits** (assessment / validation only).

---

## 4. Tags

| Tag | Present on tip? | Meaning |
|---|---|---|
| `pmp01a34-complete` | ancestor | A.3.1–A.3.4 security core freeze |
| `pmp01a35-complete` | ancestor | A.3.5 thin UI |
| `pmp01a36-complete` | ancestor | A.3.6 durable cases |
| `pmp01a37-complete` | **YES (HEAD)** | A.3.7 durable audit — **REP tip** |

No production release tag (e.g. `v1.0.0`) is authorized by this pack.

---

## 5. Validations inventory

| ID | Type | Result | Evidence |
|---|---|---|---|
| V-A31 | Reviewer API / JWT identity | PASS | `test_pmp01a31_*` |
| V-A32 | Signed assertions + fail-closed signing | PASS | `test_pmp01a32_*` |
| V-A33 | Four-eyes quorum | PASS | `test_pmp01a33_*` |
| V-A34 | Recovery link lifecycle | PASS | `test_pmp01a34_*` |
| V-A35 | Thin client / no client authority | PASS | `test_pmp01a35_*` |
| V-A36 | Durable case ledger + restart idempotency | PASS | `test_pmp01a36_*` |
| V-A37 | Durable audit + TX rollback + redaction | PASS | `test_pmp01a37_*` |
| V-A38 | Real PostgreSQL ops validation | PASS | `a38-postgresql-validation.md` |
| V-A39 | Release readiness GO/NO-GO | **NO-GO** | A.3.9 assessment |
| V-A12 | Web event contract | `NOT_VERIFIABLE` | PMP plan A.2 record |

---

## 6. Authentication and ownership (recovery scope)

| Item | Result |
|---|---|
| Canonical identity for reviewers | Supabase JWT `sub` + role claim only |
| Client-supplied `reviewer_id` | Forbidden (`extra="forbid"`) |
| Unauthenticated recovery mutations | Rejected |
| Non-reviewer role | Rejected |
| Recovery table RLS | Deny `authenticated` (service-role path) |
| Automatic identity linking | DISABLED — no production writers |
| Cross-user legacy association via recovery | Not authorized pending BLK-001 |

Broader product auth/RLS matrix for full Alpha/Beta product release is
**not claimed** by this pack (see §12).

---

## 7. Security and trust

### Frozen security contracts (must not regress)

1. Reviewer identity from server-side JWT/role only  
2. Four-eyes quorum server-side  
3. Signed assertions durable  
4. Recovery cases durable  
5. Recovery links quorum-gated  
6. Token persistence hash-only; raw token once  
7. `operation_key` idempotency survives restart  
8. Audit failure → full rollback  
9. UI remains thin client  
10. Release gate remains CLOSED  
11. Automatic linking remains DISABLED  
12. `PMP-01A-BLK-001` remains unresolved until formal resolution  

### Findings for this tip

| Class | Finding | Disposition |
|---|---|---|
| P0 | `PMP-01A-BLK-001` verified legacy identity source missing | **Open — blocks GO** |
| P0 | Hardcoded DB URL default in `_check_all.py` | **Open — rotate/remove before deploy packaging** |
| P1 | SQLite fallback when `DATABASE_URL` unset | Accepted for local only; prod must set PG |
| P1 | Expire-path audit swallow (`except Exception: pass`) | Tracked residual |
| P1 | No pytest CI for 91-suite | Tracked residual |
| P2 | Docs status tables lag A.3.5–A.3.8 | Documentation debt |
| P2 | ADR bodies missing at tip (index only) | Documentation debt |

Any open P0 keeps this REP `BLOCKED`.

---

## 8. Performance and operations

| Item | Status |
|---|---|
| Observability dashboards | Not present for recovery |
| Alert thresholds | Not defined |
| Kill-switch (release gate) | Governance CLOSED; not runtime env flag |
| Health | `GET /health`, `GET /health/scheduler` (liveness) |
| Operations Manual | `docs/operations/OPERATIONS-MANUAL.md` (REP-001 companion) |

Operations Authority: see companion manual; production GO still blocked.

---

## 9. Migration impact

| Item | Value |
|---|---|
| Production user-data migration performed | **no** |
| Dry-run / mapping | not performed for production |
| Schema migrations in tip | 0004–0007 recovery objects |
| Identity mapping writes | none (explicitly forbidden in migration headers) |
| Rollback impact | Alembic downgrade 0007→0006 validated in A.3.8; PMP-01E engine NOT_STARTED |

---

## 10. ADR and governance impact

| Item | Status |
|---|---|
| ADRs reviewed | Index `docs/adr/README.md` lists ADR-001…016 |
| ADR bodies at tip | **Missing** (documentation gap) |
| New ADRs required for A.3 freeze | None claimed in this pack |
| Release Constitution | Gate remains CLOSED — compliant |
| PMP-01A overall | `BLOCKED` |
| Manual recovery official status | Still documented `POLICY_DEFINED / NOT_OPERATIONAL` pending Council/REP closure of operational exit |

---

## 11. Rollback verification

| Item | Result |
|---|---|
| Procedure | See Operations Manual § Rollback |
| Alembic 0007→0006 rehearsal | PASS (A.3.8, local PG) |
| Data preservation (recovery tables) | Downgrade drops audit objects by design |
| PMP-01E Rollback Engine | NOT_STARTED |
| Production rollback rehearsal | **Not performed** |
| Operations Authority approval for prod rollback | **Not granted** |

---

## 12. Known risks

| Risk | Severity | Mitigation | Owner | Expiry |
|---|---|---|---|---|
| `PMP-01A-BLK-001` | P0 | Team focus brief; no PMP-01B until RESOLVED | PMP-01 | Until resolution review |
| Credentialized `_check_all.py` | P0 | Remove hardcoded default; rotate secret | Engineering | Before any deploy pack |
| Missing prod backup/restore rehearsal | P0→ops | Operations Manual + scheduled rehearsal | Operations | Before gate open |
| SQLite fallback in misconfigured prod | P1 | Require `DATABASE_URL` postgres in deploy checklist | Operations | Before gate open |
| A.3.8 not full 0001→head on Supabase | P1 | Cutover rehearsal on real project | Engineering | Before prod schema cutover |
| Expire audit swallow | P1 | Track fail-closed hardening | Engineering | Next hardening milestone |
| Docs lag | P2 | Refresh PMP status tables | Program | Next docs sync |

---

## 13. Release Council decision

| Role | Decision | Veto status | Evidence | Signed at |
|---|---|---|---|---|
| Security Authority | PENDING | Open P0: BLK-001 | This REP §7 | — |
| Identity Authority | PENDING | Open P0: BLK-001 | This REP §6–§7 | — |
| AI Quality Authority | N/A this pack | — | Recovery scope only | — |
| Product Authority | PENDING | Gate CLOSED | PMP plan | — |
| Architecture Authority | ACCEPT freeze tip | No arch change A.3.8/9 | Tip `f7cc6b3` | 2026-07-18 |
| Operations Authority | PENDING | Ops manual filed; prod GO blocked | OPERATIONS-MANUAL.md | — |

**Final decision:** `BLOCKED`  
**Unresolved vetoes:** `PMP-01A-BLK-001` (and credential hygiene for `_check_all.py`)  
**Post-release review date:** N/A — not released  
**Next program focus:** `docs/blockers/PMP-01A-BLK-001.md`

---

## 14. Artifact index

```text
releases/REP-001/
├── README.md
├── REP.md                          ← this file (authoritative index)
├── release-notes.md
├── a38-postgresql-validation.md
├── council-approval.md
└── (optional PDF export of REP.md)

docs/operations/OPERATIONS-MANUAL.md
docs/blockers/PMP-01A-BLK-001.md
```

Required template artifacts marked N/A for this security-core freeze:

| Artifact | Status |
|---|---|
| security-report.pdf | Covered by §7 + A.3 tests (markdown) |
| ai-quality-report.pdf | **N/A** — not in A.3 recovery scope |
| performance-report.pdf | **N/A** — not a performance release |
| rollback-report.pdf | Covered by §11 + A.3.8 + Operations Manual |
| migration-report.pdf | §9 — production migration **not performed** |

---

## 15. Expected diffs (A.3.8 / A.3.9)

```text
NO ARCHITECTURE CHANGE
NO SECURITY CONTRACT CHANGE
```
