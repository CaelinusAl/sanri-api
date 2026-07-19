# PMP-01A-BLK-001 — Stream C Entry Gate Acceptance Pack

**Document type:** Formal acceptance package (no implementation)  
**Blocker ID:** `PMP-01A-BLK-001`  
**Package ID:** `PMP-01A-BLK-001-C-ENTRY-001`  
**Status:** `ENTRY_GATE_PENDING`  
**Freeze tip:** `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab` / `pmp01a37-complete`  
**Date:** 2026-07-19  
**L-06 addendum:** `docs/blockers/PMP-01A-BLK-001-l06-resolution-decision.md` (`DECISION_DRAFT`)

```text
NO CODE · NO ARCHITECTURE CHANGE · NO SECURITY CONTRACT CHANGE
BLK-001 remains OPEN · Release gate CLOSED · Automatic linking DISABLED
Stream C must not begin until status becomes ENTRY_GATE_ACCEPTED
No authority is pre-marked ACCEPT
```

**Depends on**

| Artifact | Path | Prior status |
|---|---|---|
| Stream A | `docs/blockers/PMP-01A-BLK-001-verified-legacy-identity-source-design.md` | COMPLETE (DESIGN_DRAFT) |
| Stream B | `docs/blockers/PMP-01A-BLK-001-stream-b-architecture-integration.md` | COMPLETE (DESIGN_DRAFT) |
| Stream B2 | `docs/blockers/PMP-01A-BLK-001-stream-b2-containment-abuse-review.md` | CONDITIONAL PASS |
| L-06 resolution | `docs/blockers/PMP-01A-BLK-001-l06-resolution-decision.md` | DECISION_DRAFT (signable prerequisite) |

---

## 1. Executive Summary

This pack freezes every decision required before Stream C (VLIS implementation +
choke-point guard + tests) may begin. It does **not** implement Stream C, does
**not** resolve BLK-001, and does **not** open the release gate.

**Recommended gate posture (pending signatures):** accept invariants I1–I12;
retain single `submit_evidence` choke point; **forbid MTC-M1L2 in v1**;
production flag OFF ⇒ READY forbidden; post-READY invalidation uses **existing
state-machine edges only**; B2-L legacy routes inventoried with containment
plan; privileged and attestor-key controls specified.

| Field | Value |
|---|---|
| **Gate status** | `ENTRY_GATE_PENDING` |
| **Stream C** | **Blocked** until `ENTRY_GATE_ACCEPTED` |
| **BLK-001** | **OPEN** |
| **Release gate** | **CLOSED** |
| **Automatic linking** | **DISABLED** |

To accept the gate, all four Approval Blocks (§15) must be signed with no
blocking dissent. Any blocking dissent ⇒ `ENTRY_GATE_REJECTED` until resolved.

---

## 2. Authority Decision Matrix

| # | Decision | Frozen value | Binding refs |
|---|---|---|---|
| D1 | Invariants I1–I12 | **ACCEPT ALL** (individual table §3) | B2 §3 |
| D2 | AC-01…AC-24 traceability | **COMPLETE** (§4) | B2 §4 |
| D3 | Production flag matrix | **FROZEN** (§6) | B2 D4 |
| D4 | MTC-M1L2 in v1 | **FORBIDDEN** (§5) | B2 AC-09 |
| D5 | B2-L inventory + plan | **FILED** (§7) | B2 residual |
| D5b | L-06 resolution | **RECOMMENDED Option C+B** — see L-06 decision doc; **unsigned** | `PMP-01A-BLK-001-l06-resolution-decision.md` |
| D6 | Post-READY demotion | **FROZEN** (§8) — existing edges only | B2 AC-12; `recovery.py` transitions |
| D7 | Privileged / break-glass | **FROZEN** (§9) | B2 D6 |
| D8 | Attestor-key compromise | **FROZEN** (§10) | B2 AC-10 |
| D9 | Stream C test-entry criteria | **FROZEN** (§11) | B2 §14 |
| D10 | NO-GO conditions | **FROZEN** (§12) | Standing order |

---

## 3. I1–I12 Acceptance Table

| ID | Invariant (summary) | Decision | Rationale |
|---|---|---|---|
| **I1** | READY via API requires active sealed package for **this** `case_id` | **ACCEPT** | Sole READY authority seam |
| **I2** | `evidence_hash` == active `package_hash` and identity tuple matches case | **ACCEPT** | Blocks forged/cross-identity hash |
| **I3** | `evidence_type` exactly `vlis_bcmp_mtc_v1` (enforcement on) | **ACCEPT** | No legacy evidence fallback |
| **I4** | `package_hash` is not a portable bearer token | **ACCEPT** | Blocks cross-case replay |
| **I5** | MTC server-only; distinct categories; no duplicate `source_id` slots | **ACCEPT** | Blocks inflation / double-count |
| **I6** | ≥1 valid server attestation in contributing set | **ACCEPT** | Stream A hard rule |
| **I7** | Medium/High attestations unexpired + non-revoked at seal **and** submit | **ACCEPT** | Stale-proof submit |
| **I8** | Revoke/supersede clears active seal; submit against inactive fails | **ACCEPT** | Revocation integrity |
| **I9** | Verify + READY transition + audit in **one TX** with row lock | **ACCEPT** | TOCTOU / partial failure |
| **I10** | Prod-shaped deploy + enforcement OFF ⇒ READY forbidden | **ACCEPT** | Flag fail-closed |
| **I11** | No non–Recovery-Service path sets evidence / READY / links | **ACCEPT** | Authority matrix |
| **I12** | Audit append failure aborts mutation (EC-05) | **ACCEPT** | Audit suppression |

**Aggregate:** **12 / 12 ACCEPT** (recommended).  
Rejecting any single invariant ⇒ gate **REJECTED** until redesign.

---

## 4. AC-01–AC-24 Traceability Matrix

Legend: **Inv** = invariant(s) · **Test** = Stream C required test ID ·
**Audit** = required event/code · **Ops** = operational control

| AC | Abuse case | Inv | Test ID(s) | Audit | Ops control |
|---|---|---|---|---|---|
| AC-01 | Forged `package_hash` | I1,I2,I4 | `C-AC-01` | fail `vlis_hash_mismatch` / `vlis_package_required` | — |
| AC-02 | Replay package across cases | I1,I2,I4 | `C-AC-02` | `vlis_package_required` / `vlis_identity_mismatch` | Schema: hash not globally authoritative |
| AC-03 | Replay across users/legacy | I2,I4 | `C-AC-03` | `vlis_identity_mismatch` | Seal binds case identity |
| AC-04 | Substitution after inspection | I8 + EC-09 | `C-AC-04a` reseal demote; `C-AC-04b` assert rejects stale | `vlis.package_superseded`; `evidence_changed` | UI shows current hash |
| AC-05 | Stale/revoked attestations | I7,I8 | `C-AC-05a` expire pre-submit; `C-AC-05b` revoke pre-submit; `C-AC-05c` revoke post-READY | `vlis.attestation_revoked`; package invalidated | Attestation TTL policy |
| AC-06 | Split-package | I2,I5,I6 | `C-AC-06` | seal fail `vlis_item_case_mismatch` | — |
| AC-07 | Category inflation | I5 | `C-AC-07` | `vlis.mtc_evaluated` server trust only | Policy table change = break-glass |
| AC-08 | Duplicate source counted twice | I5 | `C-AC-08` | `vlis.mtc_evaluated` source set | — |
| AC-09 | Colluding low-trust / M1L2 | I5,I6 + §5 | `C-AC-09` M1L2 seal ⇒ `mtc_pass=false` | `vlis.mtc_evaluated` fail | **M1L2 FORBIDDEN v1** |
| AC-10 | Compromised server attestor | I11 + §10 | `C-AC-10` revoke-all drill (staging) | attestation revoke storm | KMS/rotation; §10 runbook |
| AC-11 | TOCTOU seal→submit | I7,I8,I9 | `C-AC-11` concurrent revoke vs submit | ordered audit | DB row locks; no replica authz |
| AC-12 | Expiry during review | I7,I8 + §8 | `C-AC-12a` READY demote; `C-AC-12b` AWAITING demote; `C-AC-12c` APPROVED→EXPIRED | `vlis_package_invalidated_during_review` | Review SLA < `valid_until` |
| AC-13 | Binding ambiguity | I2 | `C-AC-13` | `vlis_binding_failed` | Canonical legacy PK only |
| AC-14 | Race revoke vs submit | I8,I9 | `C-AC-14` | ordered revoke/submit | Same as AC-11 |
| AC-15 | Feature-flag bypass | I10 | `C-AC-15` | `vlis_enforcement_required` | Prod profile health gate |
| AC-16 | Legacy evidence-type fallback | I3,I10 | `C-AC-16` | `vlis_evidence_type_invalid` | No alternate READY types |
| AC-17 | Direct DB insertion | I11 + §9 | `C-AC-17` negative (no app path); ops drill | pgaudit / missing app chain | RLS; no SQL mint runbook |
| AC-18 | Service-role misuse | I11 + §9 | `C-AC-18` route inventory: no force-READY | gateway logs | Key never in client |
| AC-19 | Audit suppression | I9,I12 | `C-AC-19` | no READY row on audit fail | EC-05 regression suite |
| AC-20 | Partial TX failure | I9 | `C-AC-20` | single transition; idempotent replay | One DB session |
| AC-21 | Idempotency collision | I1 + A.3 ops | `C-AC-21` | `operation_key_conflict` | Keys scoped to case |
| AC-22 | Downgrade/rollback bypass | I10,I11 | `C-AC-22` health/manifest | deploy audit | Ops: disable READY if guard absent |
| AC-23 | Seal without server attestation | I5,I6 | `C-AC-23` | `vlis.mtc_evaluated` fail | — |
| AC-24 | VLIS mints link w/o four-eyes | Auth matrix | `C-AC-24` | no link without quorum | VLIS cannot call link create |

**Coverage rule:** Stream C may not claim test-complete unless every `C-AC-*`
ID above has an automated fail-closed test (ops drills marked for AC-10/17
may be staging runbooks with recorded evidence).

---

## 5. MTC-M1L2 Decision

| Field | Frozen decision |
|---|---|
| **Decision** | **FORBIDDEN in v1** |
| **Policy version** | `mtc_v1` |
| **Allowed MTC rules in v1** | `MTC-H1`, `MTC-M2` only |
| **Seal behavior** | Package whose only satisfying rule would be M1L2 ⇒ `mtc_pass=false` |
| **Submit behavior** | `vlis_mtc_failed` (P4) |
| **Rationale** | B2 AC-09 residual false-accept under compromised Medium + Low collusion is unacceptable for first production VLIS |
| **Reopening** | Requires new policy version (`mtc_v1.1+`), Security Authority approval, and REP addendum — not a silent flag |

Stream A text describing M1L2 remains historical design context; **v1
enforcement set is H1|M2 only** per this pack.

---

## 6. Production Feature-Flag Matrix

| Profile | `VLIS_EVIDENCE_ENFORCEMENT` | READY via `submit_evidence` | Notes |
|---|---|---|---|
| **production** | **ON** (required) | Choke-point P1–P7 + I1–I12 | Health check fails if OFF |
| **production** | OFF | **FORBIDDEN** — `vlis_enforcement_required` | **Not** accept-any-hash |
| **staging** | ON | Same as production | Acceptance tests |
| **staging-shadow** | ON + optional `VLIS_SHADOW_METRICS=1` | Still full enforce | Metrics only; no weak READY |
| **local/dev** | ON with test fixtures | Sealed test packages only | No prod data |
| **rollback build without guard** | N/A | Recovery READY path **disabled** | AC-22 |

**Forbidden semantics (explicit NO):**

- OFF = accept any hash  
- “Prefer VLIS but allow `manual_notes`”  
- Shadow mode that grants READY without seal  

**Normative `evidence_type` when enforcement applies:** `vlis_bcmp_mtc_v1` only.

---

## 7. B2-L Legacy Route Inventory and Containment Plan

### 7.1 Scope clarification

`READY_FOR_REVIEW` is **only** a recovery case state, advanced by
`POST /v1/recovery/cases/{id}/evidence`. No legacy product route sets that
enum directly.

B2-L therefore invents **equivalent-risk** paths: any route that could
(a) mint or imply verified legacy↔canonical association outside recovery,
(b) accept client-controlled identity as ownership authority, or
(c) bypass VLIS for link-like effects.

### 7.2 Inventory (freeze tip / current tree)

| ID | Surface | Identity signal | Current posture | Risk to BLK-001 | Containment plan | Owner | Due relative to OPERATIONAL |
|---|---|---|---|---|---|---|---|
| L-01 | `POST /v1/recovery/.../evidence` | Reviewer JWT + body hash | Open (pre-VLIS) | **Direct READY** | Stream C choke point | Recovery | **Before Stream C complete** |
| L-02 | `app/routes/activity.py` `/memory*` | Client `user_id` | **Fail-closed** 401 (`reject_unsafe_legacy_identity`) | Contained | Keep; regression `test_legacy_identity_containment` | Platform | Before OPERATIONAL |
| L-03 | `app/routes/device.py` `/device/register` | Client `user_id` | **Fail-closed** 401 | Contained | Keep + regression | Platform | Before OPERATIONAL |
| L-04 | `app/routes/events.py` | Canonical user via `get_current_user_id`; rejects client `user_id` / `mobile-default` | Contained (tests) | Low | Keep + regression | Platform | Before OPERATIONAL |
| L-05 | `app/storage.py` MemoryStore | Shared session ids | Rejects `mobile-default` / empty | Contained | Keep + regression | Platform | Before OPERATIONAL |
| L-06 | `bilinc_alani` + family (`memory_state`, `insights` fallback, `matrix_rol/yorum`) | **`X-User-Id` as self-auth** | **NOT fail-closed** | **High** data-plane; **does not** reach READY | **Option C+B** per `PMP-01A-BLK-001-l06-resolution-decision.md` (JWT sole authz; prod flag OFF) | Platform | Plan accept = entry-gate signable; **code + `L06-T*` before OPERATIONAL** |
| L-07 | `app/services/auth.py` legacy HS256 | Legacy token decode | Fail-closed (`None`) | Contained if stays disabled | Must not re-enable as trust source | Security | Continuous |
| L-08 | Identity link tables / dry-run | N/A | No public auto-link write (plan) | Auto-link must stay DISABLED | No public linking endpoint; no batch SQL | Recovery | Continuous |
| L-09 | `app/routes/shopier_purchases.py` | `device_fp` / email unlock binding | Device/email correlation for purchases | Medium — not READY, but ownership-adjacent | Must not feed VLIS as High/Medium without server attestation adapter rules; no identity link writes | Payments | Before OPERATIONAL |
| L-10 | `app/routes/subscription.py` | Optional auth user id | Partial auth patterns | Low–Med | Confirm no legacy int id authority for mapping | Billing | Before OPERATIONAL |
| L-11 | Admin routes (`admin*.py`) | Admin auth | Privileged | High if force-map exists | Inventory admin “link/verify user” actions; forbid silent verify; dual-control | Ops/Security | Before OPERATIONAL |
| L-12 | Mobile client legacy ask | Deep links / contained UX | Product containment (PMP-01A.1) | UX not READY | Keep fail-closed product messaging; no client-minted legacy proof | Mobile | Before release gate |

### 7.3 B2-L completion rule

| Claim | Requires |
|---|---|
| Stream C **implementation start** | This pack `ENTRY_GATE_ACCEPTED`; L-02…L-05 regressions remain green; **L-06 Option C+B decision accepted** (code may parallel) |
| Manual recovery **OPERATIONAL** | L-01 (VLIS) implemented + C tests green; **L-06.1–L-06.8 contained** + `L06-T01`…`T09` green; L-07…L-12 no open High |
| BLK-001 **RESOLVED** | OPERATIONAL evidence + Council; B2-L High items closed |

**L-06 family** is the primary open B2-L High item. Full inventory and
recommended resolution: `docs/blockers/PMP-01A-BLK-001-l06-resolution-decision.md`.  
**Exploitability lock:** cannot reach READY / mutate recovery; **can**
cross-user read/write memory & profile via header spoof.

---

## 8. Post-READY Demotion Contract

Uses **only existing** `ALLOWED_TRANSITIONS` (no contract change).

### 8.1 Trigger set

Package becomes invalid when any of:

- `now >= package.valid_until`
- contributing attestation revoked
- package superseded / active flag cleared
- binding re-check fails (defense-in-depth)

### 8.2 Demotion by current state

| Current state | Demotion target | Assertions | Link | Notes |
|---|---|---|---|---|
| `READY_FOR_REVIEW` | `EVIDENCE_PENDING` | Prior approvals invalid for quorum (hash/package authority broken; require reseal + new submit) | None | Allowed edge |
| `AWAITING_SECOND_APPROVAL` | `EVIDENCE_PENDING` | Same; first-eye approval cannot complete quorum on invalid package | None | Allowed edge |
| `APPROVED` | `EXPIRED` | Quorum unusable; **new case** required (EC-08) | None created | **Cannot** return to EVIDENCE_PENDING without contract change |
| `LINK_CREATED` | Do **not** silent-demote case to EVIDENCE_PENDING | — | If attestor compromise / fraud: **revoke link** → `REVOKED` (existing path) | Link consequences explicit |
| Terminal | No demotion | — | — | Appeals = new case |

### 8.3 Transaction semantics

```text
BEGIN
  LOCK case row + active package row
  If package invalid AND state in {READY, AWAITING_SECOND}:
       transition → EVIDENCE_PENDING
       audit vlis_package_invalidated_during_review
  If package invalid AND state == APPROVED:
       transition → EXPIRED
       audit vlis_package_invalidated_during_review
  If package invalid AND state == LINK_CREATED:
       do not auto-revoke in the expiry sweeper;
       fraud/attestor incident uses explicit revoke_recovery_link TX
  Audit write required or ROLLBACK
COMMIT
```

Checkpoints that must invoke validity: `get_case` (lazy), `create_assertion`,
`create_recovery_link` (fail closed if invalid; prefer explicit demotion TX).

### 8.4 Reviewer / assertion invalidation

- `create_assertion` fails if package invalid (`vlis_attestation_expired` /
  `vlis_package_invalidated`).  
- Existing signed assertions remain in append-only store but are **not valid
  for quorum** when package inactive or `valid_until` passed (additive validity
  predicate alongside hash match).  
- After demotion to `EVIDENCE_PENDING`, reseal + new `submit_evidence` required
  (new hash ⇒ classic EC-09 behavior for any lingering approvals).

### 8.5 Link consequences

| Situation | Action |
|---|---|
| Invalid package before link | No link; demote/expire as §8.2 |
| Fraud / attestor compromise after link | `revoke_recovery_link` → `REVOKED` |
| Routine TTL after successful link | Link lifecycle uses existing link expiry/revoke rules; package TTL does not silently delete audit |

### 8.6 Audit events (normative names)

| Event | When |
|---|---|
| `vlis_package_invalidated_during_review` | Demotion/expiry from READY/AWAITING/APPROVED |
| `vlis.attestation_revoked` | Attestation revoke |
| `vlis.package_superseded` | Reseal |
| `submit_evidence` / existing recovery events | Unchanged names where applicable |
| `assert_revoke_*` / link revoke | Existing A.3 |

---

## 9. Privileged-Role and Break-Glass Controls

### 9.1 Service-role permissions

| Allowed | Forbidden |
|---|---|
| Recovery Service + VLIS server paths using service role to RW recovery/vlis tables | Client apps shipping service role |
| Migrations via controlled CI/CD | Ad-hoc `psql` minting READY / packages / links |
| Read-only diagnostics with redaction | `force_ready`, `force_link`, `set_verified` APIs |

### 9.2 Direct DB mutation prevention

1. RLS deny-all for `authenticated` on recovery + vlis tables (A.3 pattern).  
2. No operator runbook that INSERTs READY or `vlis_packages.mtc_pass=true`.  
3. Optional defense-in-depth DB constraint/trigger (Stream C may add): reject
   case `state='READY_FOR_REVIEW'` without matching active package — **additive**,
   not a contract change.  
4. pgaudit / equivalent on break-glass sessions.

### 9.3 Break-glass process

| Step | Requirement |
|---|---|
| Trigger | Sev-1 identity incident only |
| Approvers | Security Authority **and** Recovery System Owner (two humans) |
| Actions allowed | Revoke links; revoke attestations; disable recovery READY (flag/health); rotate keys |
| Actions forbidden | Mint READY; mint links; set verified via SQL; disable audit |
| Record | Incident ticket + Council note within 5 business days |
| Audit | Every break-glass session logged |

### 9.4 Approval and audit requirements

Config changes to `VLIS_EVIDENCE_ENFORCEMENT` in production require Operations
Owner + Security Authority acknowledgment; emit ops audit (who/when/old/new).

---

## 10. Attestor-Key Compromise Runbook Requirements

Stream C must ship a runbook (doc) satisfying:

| Step | Requirement |
|---|---|
| 1 Detect | Attestation volume anomaly / KMS alert / adapter compromise |
| 2 Contain | Disable challenge adapters; set enforcement health fail if needed |
| 3 Rotate | Attestation MAC/signing keys via secrets manager; invalidate old key verify |
| 4 Revoke | Bulk-revoke attestations signed under compromised key material |
| 5 Invalidate packages | Clear active seals referencing revoked attestations |
| 6 Cases in flight | Apply §8 demotion/expiry |
| 7 Links | Fraud review queue; revoke confirmed-bad links (four-eyes/ops dual-control) |
| 8 Communicate | Security Authority + Recovery Owner + Council note |
| 9 Resume | New key live; staging drill evidence; production re-enable adapters |
| 10 Evidence | Attach redacted timeline to REP addendum |

**Choke point alone does not mitigate AC-10** — this runbook is mandatory ops
control in the AC-10 trace row.

---

## 11. Stream C Entry Criteria

Stream C **may begin** only when **all** are true:

1. This pack status is **`ENTRY_GATE_ACCEPTED`** (all §15 blocks signed).  
2. I1–I12 accepted with no open rejects (§3).  
3. AC-01…AC-24 mapped to tests/audit/ops (§4) accepted.  
4. MTC-M1L2 = **FORBIDDEN** in v1 (§5) accepted (or formal written override
   signed by Security Authority — none in this pack).  
5. Production flag matrix (§6) accepted.  
6. B2-L inventory (§7) accepted; **L-06 Option C+B** accepted via
   `PMP-01A-BLK-001-l06-resolution-decision.md` (or written alternate).  
7. Post-READY demotion contract (§8) accepted.  
8. Privileged/break-glass (§9) and attestor-key runbook requirements (§10)
   accepted.  
9. NO-GO list (§12) acknowledged; includes prod `LEGACY_X_USER_ID_AUTH=ON`.  
10. Standing order unchanged: BLK-001 OPEN; gate CLOSED; auto-link DISABLED;
    no accept-any-hash READY; **no false authority ACCEPT marks**.

**Stream C implementation scope (reminder — not started by this pack):**

- VLIS tables/APIs + seal/MTC  
- `submit_evidence` choke-point guard  
- Post-READY validity checks per §8  
- Automated `C-AC-*` tests  
- Flag/health behavior  
- Runbooks (attestor key, break-glass) as docs  

**Not in Stream C start:** release gate OPEN, auto-link, PMP-01B/C, BLK-001
RESOLVED.

---

## 12. NO-GO Conditions

Any of the following keeps or returns the gate to **REJECTED** / blocks Stream C
continue / blocks OPERATIONAL:

| ID | NO-GO condition |
|---|---|
| NG-01 | Any of I1–I12 rejected without approved replacement |
| NG-02 | Production semantics OFF = accept-any-hash |
| NG-03 | M1L2 enabled in v1 without Security Authority override + REP |
| NG-04 | Force-READY / force-link API introduced |
| NG-05 | VLIS can create recovery links or sign assertions |
| NG-06 | Legacy HS256 re-enabled as trust source |
| NG-07 | Automatic linking enabled |
| NG-08 | Ad-hoc SQL declared as recovery path |
| NG-09 | Audit best-effort (EC-05 weakened) |
| NG-10 | L-06.1–L-06.8 still header-authoritative **and** team claims OPERATIONAL |
| NG-10b | Production `LEGACY_X_USER_ID_AUTH=ON` |
| NG-11 | Stream C starts while this pack is `PENDING` or `REJECTED` |
| NG-12 | Release gate OPEN before Council BLK-001 RESOLVED |
| NG-13 | Security contract / state-machine edits disguised as “integration” |
| NG-14 | Rollback removes guard while READY remains enabled |

---

## 13. Stream C Test-Entry Criteria (pre-coding checklist)

Before first Stream C implementation PR:

- [ ] Gate status `ENTRY_GATE_ACCEPTED`  
- [ ] Test plan lists every `C-AC-*` ID from §4  
- [ ] Fixtures strategy for sealed packages (no accept-any-hash in CI prod profile)  
- [ ] Flag matrix encoded in test env matrix  
- [ ] Demotion cases for READY / AWAITING / APPROVED→EXPIRED specified  
- [ ] Regression suite A.3.1–A.3.7 remains mandatory green  
- [ ] L-02…L-05 containment tests remain mandatory green  
- [ ] No PR modifies `ALLOWED_TRANSITIONS` or four-eyes quorum rules  

---

## 14. Status Outcome

| Status | Meaning |
|---|---|
| `ENTRY_GATE_ACCEPTED` | All §15 blocks signed; Stream C may begin under this pack |
| `ENTRY_GATE_REJECTED` | Blocking dissent; Stream C must not begin; revise pack |
| `ENTRY_GATE_PENDING` | **Current** — awaiting signatures |

**Current package status: `ENTRY_GATE_PENDING`**

---

## 15. Approval Blocks

### 15.1 Identity Authority

| Field | Value |
|---|---|
| Role | Identity Authority |
| Decision | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN |
| Scope acknowledged | I1–I12; M1L2 FORBIDDEN v1; B2-L; **L-06 Option C+B**; binding rules |
| Evidence to review | Entry pack §§3–8; **L-06 decision §§2–6, brief §9.1** |
| ACCEPT if | JWT/canonical sole authz for L-06.1–L-06.8; header never production authority |
| REJECT if | Header must remain prod auth; or unresolved L-06 option |
| Name | ______________________________ |
| Date | __________ |
| Signature / recorded ack | ______________________________ |
| Blocking notes | |

### 15.2 Security Authority

| Field | Value |
|---|---|
| Role | Security Authority |
| Decision | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN |
| Scope acknowledged | AC trace; flags; demotion; attestor-key; NO-GO; **L-06 exploitability** |
| Evidence to review | Entry pack §§4–6,12; **L-06 decision §§4–6, brief §9.2** |
| ACCEPT if | No READY bypass via header; cross-user data risk accepted with C+B; OPERATIONAL blocked until `L06-T*` |
| REJECT if | Wants Stream C blocked until L-06 code lands; or accepts prod header auth |
| Name | ______________________________ |
| Date | __________ |
| Signature / recorded ack | ______________________________ |
| Blocking notes | |

### 15.3 Recovery System Owner

| Field | Value |
|---|---|
| Role | Recovery System Owner |
| Decision | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN |
| Scope acknowledged | Choke point; TX; demotion; no contract change; **L-06 parallel track** |
| Evidence to review | Entry pack §§8,11; recovery routes (no `X-User-Id`); **L-06 brief §9.3** |
| ACCEPT if | Recovery freeze untouched; L-06 outside A.3; parallel OK |
| REJECT if | Requires L-06 inside recovery contracts or blocks all Stream C until L-06 ships |
| Name | ______________________________ |
| Date | __________ |
| Signature / recorded ack | ______________________________ |
| Blocking notes | |

### 15.4 Operations Owner

| Field | Value |
|---|---|
| Role | Operations Owner |
| Decision | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN |
| Scope acknowledged | VLIS flag/health; break-glass; **`LEGACY_X_USER_ID_AUTH` prod OFF**; runbooks |
| Evidence to review | Entry pack §§6,9,12; **L-06 decision §§6–7, brief §9.4** |
| ACCEPT if | Can enforce both enforcement flags; no prod header-auth break-glass |
| REJECT if | Cannot operate health/config controls as specified |
| Name | ______________________________ |
| Date | __________ |
| Signature / recorded ack | ______________________________ |
| Blocking notes | |

### 15.5 Acceptance rule

```text
ENTRY_GATE_ACCEPTED  ⟺  all four blocks = ACCEPT (no REJECT)
ENTRY_GATE_REJECTED  ⟺  any block = REJECT
ENTRY_GATE_PENDING   ⟺  otherwise
```

Abstain counts as non-accept ⇒ pack remains `PENDING`.

---

## 16. Explicit Non-Claims

| Claim | Status |
|---|---|
| Stream C started | **No** |
| Production code written for VLIS | **No** |
| Architecture changed | **No** |
| Security contracts changed | **No** |
| BLK-001 RESOLVED | **No** |
| Manual recovery OPERATIONAL | **No** |
| Release gate OPEN | **No** |
| Automatic linking enabled | **No** |
| Entry gate accepted | **No** (`PENDING`) |

---

## 17. Document control

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-19 | Initial Entry Gate Acceptance Pack — `ENTRY_GATE_PENDING` |
| 1.0a | 2026-07-19 | Non-normative pointer: Council gap docs filed under `PMP-01A-BLK-001-council-review-completion-pack.md` — **does not** change D1–D10, I1–I12, or gate status |

**Next action:** Obtain §15 signatures (and Council completion artifact
signatures as applicable). On full ACCEPT, flip status to
`ENTRY_GATE_ACCEPTED` via recorded amendment (no code). Only then open Stream C
implementation planning/PRs.

---

## Appendix A — Standing order

```text
Until BLK-001 is RESOLVED with Council acceptance:
  — Release gate stays CLOSED
  — Automatic linking stays DISABLED
  — No PMP-01B / PMP-01C start
  — No ad-hoc production identity SQL
  — No Stream C implementation while ENTRY_GATE_PENDING or REJECTED
  — No accept-any-hash READY path in production-shaped deploys
```

## Appendix B — Quick reference: demotion edges

```text
READY_FOR_REVIEW ----------→ EVIDENCE_PENDING   (package invalid)
AWAITING_SECOND_APPROVAL --→ EVIDENCE_PENDING   (package invalid)
APPROVED ------------------→ EXPIRED            (package invalid; new case)
LINK_CREATED --------------→ REVOKED            (explicit link revoke only)
```
