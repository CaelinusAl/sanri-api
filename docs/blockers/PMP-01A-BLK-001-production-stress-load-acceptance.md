# PMP-01A-BLK-001 — Production Stress / Load Acceptance

**Document type:** Acceptance criteria / test design (governance only)  
**Blocker ID:** `PMP-01A-BLK-001`  
**Package ID:** `PMP-01A-BLK-001-SLA-LOAD-001`  
**Status:** `ACCEPTANCE_DRAFT` — awaiting Operations + Security ACCEPT (unsigned)  
**Governance freeze:** `55fc4aa` / tag `pmp01a39-governance-freeze`  
**Date:** 2026-07-19  

```text
NO CODE · NO LOAD GENERATORS CHECKED IN · NO STREAM C · NO RELEASE GATE OPEN
Defines mandatory pre-production stress evidence for recovery core
Does not change A.3 security contracts · Does not enable Auto-Link
ENTRY_GATE remains PENDING · BLK-001 remains OPEN
```

**Frozen references**

| Artifact | Binding constraint preserved |
|---|---|
| A.3.1–A.3.7 | `operation_key` idempotency; single-TX mutations; append-only audit |
| Entry Gate I9 / I12 | Verify+READY+audit one TX; audit failure aborts mutation |
| Entry Gate AC-19…AC-21 | Audit suppression, partial TX, idempotency collision |
| EC-01, EC-05, EC-06 | Concurrent quorum, audit fail-closed, restart resume |
| Release Gate | **CLOSED** until Council + remaining blockers |

**Related:** Operations Manual §7 · REP-001 · A.3.8 PostgreSQL validation (functional, not load)

---

## 1. Purpose

Council Review asked:

> Which load tests are mandatory before production for the operation-key,
> transaction, and audit system — and what are the acceptance criteria?

A.3.8 proved **correctness on real PostgreSQL**. It did **not** prove behavior
under concurrent reviewer load, audit append pressure, or idempotent replay
storms. This document freezes the **minimum stress evidence** required before
any claim that manual recovery is **OPERATIONAL** in production.

**Scope:** Recovery security core only (`/v1/recovery/*`, case/ops/assertion/
link/audit ledgers). Not product chat QPS, not bilinc LLM throughput.

---

## 2. Systems under test

| System | Critical properties under load |
|---|---|
| **Operation-key plane** | Idempotent replay; conflict on rebinding; no double link / double READY |
| **Transaction plane** | Case row locks; single-winner quorum (EC-01); no partial READY without audit |
| **Audit plane** | Append-only; every successful mutation has audit row; audit fail ⇒ mutation abort (EC-05 / I12) |
| **VLIS choke (future Stream C)** | Seal→submit under revoke races (AC-11/14) — tests may be *specified* now, *executed* after Stream C |

---

## 3. Environments

| Env | Role |
|---|---|
| **staging-pg** | Production-shaped Postgres (same major version, append-only trigger ON) |
| **staging-app** | Image built from freeze tip + Stream C when ACCEPTED; flags prod-like |
| **Forbidden** | Production as first load target; shared DB with live users |

Data: synthetic reviewers + synthetic cases only. No production PII.

---

## 4. Mandatory test suites

### 4.1 Suite SLA-OK — Operation-key stress

**Objective:** Prove idempotency and conflict semantics under replay and collision.

| Test ID | Scenario | Load shape | Accept if |
|---|---|---|---|
| **SLA-OK-01** | Same `operation_key` + same payload replayed | 50 VUs × 20 replays on one case mutation | 100% responses identical success payload; `replayed: true` (or equiv); **exactly one** state transition / one link |
| **SLA-OK-02** | Same `operation_key` rebound to different `case_id` | 20 VUs mixed | 100% `operation_key_conflict` (or contract-equivalent); **zero** cross-case mutation |
| **SLA-OK-03** | Burst create-case with unique keys | 100 creates / 10s | All durable; no lost writes; unique keys unique in DB |
| **SLA-OK-04** | Restart mid-replay (EC-06) | Kill app mid SLA-OK-01 | After restart, replay converges to single prior result; no second link |

**Fail if:** Any duplicate link for same identity pair; any second READY from replay; silent 200 with divergent state.

### 4.2 Suite SLA-TX — Transaction / concurrency stress

**Objective:** Prove single-winner and lock behavior under concurrent reviewers.

| Test ID | Scenario | Load shape | Accept if |
|---|---|---|---|
| **SLA-TX-01** | Two reviewers approve same case concurrently (EC-01) | 200 paired races | Exactly one `APPROVED`; loser `conflict_state` / idempotent; both attempts audited |
| **SLA-TX-02** | Concurrent evidence submit vs revoke/invalidation (AC-11/14 class) | 50 races | No READY with invalid package; ordered audit; fail-closed |
| **SLA-TX-03** | Concurrent link create for same pair | 50 races | ≤1 link; others conflict/idempotent |
| **SLA-TX-04** | Forced DB error after mutation before audit commit | Inject / fault | **Zero** committed mutation without audit (I12); client sees failure |
| **SLA-TX-05** | Long transaction hold (lock timeout) | 10 VUs hold row | No silent corruption; bounded wait; clear error; no stuck READY |

**Fail if:** Dual APPROVED; link without quorum; READY without audit row.

### 4.3 Suite SLA-AU — Audit ledger stress

**Objective:** Prove append-only audit keeps up and remains immutable under write load.

| Test ID | Scenario | Load shape | Accept if |
|---|---|---|---|
| **SLA-AU-01** | Sustained mutation rate | **≥ 20 successful recovery mutations/sec** for **15 minutes** (or max staging hardware allows — document actual; floor **5/s for 15 min** if hardware-limited) | Audit rows == successful mutations; p99 mutation latency **≤ 2s**; error rate **< 0.1%** excluding intentional conflicts |
| **SLA-AU-02** | Append-only enforcement under load | Parallel `UPDATE`/`DELETE` attempts on audit | 100% rejected by trigger/policy; mutations continue |
| **SLA-AU-03** | Audit volume continuity | After SLA-AU-01 | `count(audit) ≥ count(successful mutating ops)` for window; spot hash/chain integrity check if implemented |
| **SLA-AU-04** | Disk / connection saturation drill | Lower `max_connections` or fill logs (staging) | Fail-closed (5xx), **no** mute audit; Ops runbook exercised |

**Fail if:** Missing audit for success; successful UPDATE on audit rows; continued “success” when audit subsystem down.

### 4.4 Suite SLA-VL — VLIS-adjacent (execute after Stream C)

Specified now so Council sees the bar; **blocked on `ENTRY_GATE_ACCEPTED` + Stream C**.

| Test ID | Scenario | Accept if |
|---|---|---|
| **SLA-VL-01** | Concurrent seal invalidate vs `submit_evidence` | Matches AC-11/14; no READY on invalid package |
| **SLA-VL-02** | Idempotent submit with same package + operation_key under load | Single READY transition |
| **SLA-VL-03** | Flag OFF on prod-shaped profile under load | 100% `vlis_enforcement_required` / READY forbidden (I10) |

---

## 5. Performance budgets (acceptance numbers)

These are **gates**, not aspirational SLOs for product traffic.

| Metric | Budget | Applies |
|---|---|---|
| p50 recovery mutation latency | ≤ 300 ms | staging-pg local-region |
| p99 recovery mutation latency | ≤ 2000 ms | under SLA-AU-01 load |
| Idempotent replay overhead | ≤ +20% vs first success p99 | SLA-OK-01 |
| Conflict/error responses under intentional race | Correctness > latency | SLA-TX-* |
| Audit lag (commit to durable row) | Same TX — lag **0** by design | All |
| Data corruption / dual-link incidents | **0** | All suites |
| Duration of sustained test | ≥ 15 minutes continuous | SLA-AU-01 |
| Soak (optional but recommended) | 2 hours at 25% of SLA-AU-01 rate | Pre-OPERATIONAL |

If staging hardware cannot meet the **20/s** target, Ops records measured max
sustainable rate ≥ **5/s**, still for 15 minutes, with **zero** correctness
failures — and Council must explicitly ACCEPT the lowered throughput floor.
Correctness budgets never lower.

---

## 6. Pass / Fail decision rule

```text
LOAD_ACCEPTANCE_PASS  ⟺
  all SLA-OK-* PASS
  ∧ all SLA-TX-* PASS
  ∧ all SLA-AU-* PASS
  ∧ (if Stream C merged) all SLA-VL-* PASS
  ∧ zero dual-link / dual-APPROVED / audit-missing incidents
  ∧ evidence pack attached to REP addendum

LOAD_ACCEPTANCE_FAIL  ⟺ any mandatory suite FAIL
LOAD_ACCEPTANCE_PENDING ⟺ not yet executed (current state)
```

**Current status:** `LOAD_ACCEPTANCE_PENDING`  
(No stress run is claimed by this document.)

---

## 7. Evidence package (required artifacts)

For each suite:

1. Command / scenario definition (script name + version, not necessarily in-repo yet).  
2. Staging tip SHA + image id + `alembic current`.  
3. Flag matrix (`VLIS_EVIDENCE_ENFORCEMENT`, `LEGACY_X_USER_ID_AUTH=0`).  
4. Raw summary: VUs, duration, RPS, p50/p99, error taxonomy.  
5. DB proof queries: link counts, APPROVED counts, audit counts, conflict counts.  
6. Redacted sample audit rows for success + conflict paths.  
7. Sign-off: Operations Owner + Security Authority.

Store under `releases/REP-001/` or successor REP as
`evidence/load-acceptance/` when executed — **not now**.

---

## 8. Relationship to other gates

| Gate | Load acceptance required? |
|---|---|
| Stream C coding start (`ENTRY_GATE_ACCEPTED`) | **No** |
| Stream C feature-complete | SLA-VL specs exist; execution after code |
| Manual recovery **OPERATIONAL** | **Yes** — SLA-OK + SLA-TX + SLA-AU PASS; SLA-VL if VLIS shipped |
| BLK-001 **RESOLVED** | **Yes** (as part of OPERATIONAL evidence) + Council |
| Release Gate OPEN | **Yes** plus remaining program blockers |
| Auto-Link enable | Out of scope; separate design |

---

## 9. Explicitly out of scope

- Chat / LLM / matrix generation load  
- CDN / mobile network chaos  
- Multi-region failover (document as future Ops)  
- Destructive prod drills  
- Changing append-only trigger or weakening I12 for speed  

---

## 10. Decision record (unsigned)

| # | Decision | Proposed freeze value |
|---|---|---|
| LA-1 | Mandatory suites before OPERATIONAL | SLA-OK, SLA-TX, SLA-AU |
| LA-2 | VLIS load suite | SLA-VL after Stream C; required before OPERATIONAL if VLIS in tip |
| LA-3 | Correctness floor | Zero dual-link / dual-APPROVED / missing audit |
| LA-4 | Throughput floor | 20/s × 15 min aspirational; ≥5/s × 15 min with explicit Ops ACCEPT |
| LA-5 | Latency floor | p99 ≤ 2s under sustained suite |
| LA-6 | Current state | `LOAD_ACCEPTANCE_PENDING` |

### Authority signatures (do not pre-fill)

| Authority | Decision | Name | Date |
|---|---|---|---|
| Operations Owner | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN | | |
| Security Authority | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN | | |
| Recovery System Owner | ☐ ACK · ☐ REJECT · ☐ ABSTAIN | | |
| Identity Authority | ☐ ACK (no identity weakening) · ☐ ABSTAIN | | |

---

## 11. Explicit non-claims

| Claim | Status |
|---|---|
| Load tests executed | **No** |
| LOAD_ACCEPTANCE_PASS | **No** |
| Production capacity certified | **No** |
| Release Gate OPEN | **No** |

---

## 12. Document control

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-19 | Initial Production Stress / Load Acceptance — `ACCEPTANCE_DRAFT` |
