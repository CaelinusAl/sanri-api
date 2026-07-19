# PMP-01A-BLK-001 — Council Review Completion Pack

**Document type:** Governance index (design / decision only)  
**Blocker ID:** `PMP-01A-BLK-001`  
**Package ID:** `PMP-01A-BLK-001-CRC-001`  
**Status:** `COUNCIL_GAPS_FILED` — three Council-missing fields documented; **unsigned**  
**Governance freeze:** `55fc4aa` / tag `pmp01a39-governance-freeze`  
**Date:** 2026-07-19  

```text
NO CODE · NO MIGRATION · NO PR · NO STREAM C
Does not change frozen Entry Gate decisions · Does not pre-mark ACCEPT
ENTRY_GATE = PENDING · BLK-001 = OPEN · Release Gate = CLOSED · Auto-Link = DISABLED
```

---

## 1. Why this pack exists

Governance freeze (`55fc4aa`, `pmp01a39-governance-freeze`) filed Streams A–C
entry design, B2, and L-06. During Council Review, **three fields** were still
insufficiently decision-ready for signature:

| # | Missing field | Completion artifact |
|---|---|---|
| 1 | Verified Legacy Identity Source — evidence combinations & trust levels | `PMP-01A-BLK-001-council-vlis-evidence-trust-decision.md` |
| 2 | Migration Bridge — JWT cutover without `X-User-Id` authz | `PMP-01A-BLK-001-migration-bridge-design.md` |
| 3 | Production Stress / Load Acceptance — operation-key / TX / audit | `PMP-01A-BLK-001-production-stress-load-acceptance.md` |

This index binds those artifacts to the freeze **without amending** I1–I12,
MTC-M1L2 forbidden, Option C+B, demotion edges, or flag matrix.

---

## 2. Status snapshot (unchanged by this pack)

| Gate | Status |
|---|---|
| Governance freeze | **Complete** (`55fc4aa` / `pmp01a39-governance-freeze`) |
| ENTRY_GATE | **`PENDING`** |
| BLK-001 | **`OPEN`** |
| Release Gate | **`CLOSED`** |
| Auto-Link | **`DISABLED`** |
| Stream C implementation | **Not started** |
| Load acceptance execution | **`PENDING`** (criteria only) |

---

## 3. Gap closure summary

### 3.1 Verified Legacy Identity Source

| Question | Answer (draft) |
|---|---|
| How is legacy identity verified? | Server attestations + MTC under VLIS-BCMP |
| v1 compositions | `MTC-H1` or `MTC-M2` only |
| Default mass path | **M2-A** = verified email (S2) + payment (S7) |
| Default High path | **H1-A** = KYC (S1) when available |
| Low / M1L2 | **Forbidden** for v1 READY (Entry Gate §5 preserved) |
| Client headers as proof | **Never** |

### 3.2 Migration Bridge

| Question | Answer (draft) |
|---|---|
| Authz without `X-User-Id`? | Canonical JWT only (L-06 Option C) |
| Prod flag | `LEGACY_X_USER_ID_AUTH=0` (Option B) |
| Compatibility | Header ignored; anonymous M0; personalized needs Bearer |
| Creates verified links? | **No** — recovery/VLIS only; Auto-Link DISABLED |
| Bridge CLOSED when | Criteria C1–C8 in Migration Bridge §7 |
| vs OPERATIONAL | Bridge close + VLIS + L06-T* required |

### 3.3 Production Stress / Load Acceptance

| Question | Answer (draft) |
|---|---|
| Mandatory suites | SLA-OK (operation-key), SLA-TX (transactions), SLA-AU (audit) |
| After Stream C | SLA-VL additionally |
| Hard fail | Dual-link, dual-APPROVED, missing audit |
| Throughput floor | 20/s × 15 min (or ≥5/s with Ops ACCEPT) |
| p99 | ≤ 2s under sustained suite |
| Current | Criteria filed; **not executed** |

---

## 4. Document set (authoritative paths)

### Freeze baseline (do not rewrite)

| Doc | Path |
|---|---|
| Focus brief | `docs/blockers/PMP-01A-BLK-001.md` |
| Stream A | `docs/blockers/PMP-01A-BLK-001-verified-legacy-identity-source-design.md` |
| Stream B | `docs/blockers/PMP-01A-BLK-001-stream-b-architecture-integration.md` |
| Stream B2 | `docs/blockers/PMP-01A-BLK-001-stream-b2-containment-abuse-review.md` |
| Entry Gate | `docs/blockers/PMP-01A-BLK-001-stream-c-entry-gate-acceptance-pack.md` |
| L-06 | `docs/blockers/PMP-01A-BLK-001-l06-resolution-decision.md` |

### Council completion (this filing)

| Doc | Path | Status |
|---|---|---|
| VLIS evidence/trust decision | `docs/blockers/PMP-01A-BLK-001-council-vlis-evidence-trust-decision.md` | `DECISION_DRAFT` |
| Migration Bridge | `docs/blockers/PMP-01A-BLK-001-migration-bridge-design.md` | `DESIGN_DRAFT` |
| Load acceptance | `docs/blockers/PMP-01A-BLK-001-production-stress-load-acceptance.md` | `ACCEPTANCE_DRAFT` |
| This index | `docs/blockers/PMP-01A-BLK-001-council-review-completion-pack.md` | `COUNCIL_GAPS_FILED` |

---

## 5. What Council / authorities should do next

1. Review and sign the three completion artifacts (§3).  
2. Separately complete Entry Gate §15 + L-06 signatures → `ENTRY_GATE_ACCEPTED`.  
3. Only then start Stream C (VLIS wire-up) and parallel L-06 code track.  
4. Execute load suites before OPERATIONAL; attach evidence to REP.  
5. Do **not** treat this pack as Entry Gate ACCEPT or BLK-001 RESOLVED.

---

## 6. Standing order (reaffirmed)

```text
Until BLK-001 is RESOLVED with Council acceptance:
  — Release gate stays CLOSED
  — Automatic linking stays DISABLED
  — No PMP-01B / PMP-01C start
  — No ad-hoc production identity SQL
  — No Stream C implementation while ENTRY_GATE_PENDING or REJECTED
  — No production X-User-Id authorization
```

---

## 7. Document control

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-19 | File three Council gap docs; index only — gates unchanged |
