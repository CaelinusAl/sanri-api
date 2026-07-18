# PMP-01A-BLK-001 — Stream B: Architecture Integration

**Document type:** Design only (no implementation)  
**Blocker ID:** `PMP-01A-BLK-001`  
**Stream:** B — Architecture Integration  
**Depends on:** Stream A design (`VLIS-BCMP`)  
**Status:** `DESIGN_DRAFT`  
**Freeze tip:** `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab` / `pmp01a37-complete`  
**Last updated:** 2026-07-18  

```text
Authority Level: Design — does not change production behavior
Constraint: minimal future surface change; ZERO security-contract changes
Frozen: fail-closed · four-eyes · append-only audit · signed assertions ·
        transaction guarantees · idempotency · replay protection · EC-01..EC-12
Non-goals: production code · automatic linking · release gate OPEN ·
           PMP-01B/C · ad-hoc SQL · legacy HS256 re-enable
```

---

## 0. Stream naming (clarify)

| Stream | Focus | This document |
|---|---|---|
| **A** | VLIS trust / threat / MTC design | Filed (VLIS-BCMP) |
| **B — Architecture Integration** | How VLIS plugs into frozen A.3 with minimal seams | **This file** |
| **B2 — Containment / abuse review** | Hostile review of VLIS choke point + B2-L legacy routes | Filed: `PMP-01A-BLK-001-stream-b2-containment-abuse-review.md` |
| **C** | Implement wiring + e2e security tests | After A + B + B2 entry criteria |
| **D** | Council / REP resolution | After C evidence |

This milestone renames work to **Architecture Integration** because the
integration contract must be locked before any VLIS code lands. Original
containment work remains mandatory as **Stream B2**.

---

## 1. Executive Summary

Frozen A.3 already provides a complete recovery **execution** pipeline:

```text
create_case → submit_evidence → create_assertion (×2) → create_link → audit
```

What it lacks is a **verified meaning** for `evidence_hash`. Today
`submit_evidence` accepts a caller-supplied hash and advances
`EVIDENCE_PENDING → READY_FOR_REVIEW` with no server proof that the hash
represents an MTC-satisfying VLIS package.

**Integration strategy (recommended): Adjacent VLIS module + single choke point.**

1. Build VLIS-BCMP as a **new bounded context** beside Recovery Service.  
2. Do **not** rewrite four-eyes, assertion signing, link lifecycle, or state
   machine legality.  
3. Make `submit_evidence` the **only** integration seam: it may promote a case
   to `READY_FOR_REVIEW` only when the supplied `evidence_hash` equals a
   **server-sealed VLIS package hash** for that case with `mtc_pass=true`.  
4. Assertions, quorum, and links continue to bind to `case.evidence_hash`
   exactly as today — so once the hash is VLIS-backed, the rest of A.3
   enforces security unchanged.

| Question | Answer |
|---|---|
| Security contracts change? | **No** |
| State machine transitions change? | **No** (same edges; stronger preconditions) |
| New READY path outside recovery? | **No** |
| Automatic linking? | **Still DISABLED** |
| Production code in this milestone? | **No** |

---

## 2. Frozen Pipeline Inventory (as-is)

### 2.1 Components (do not redesign)

| Layer | Location (freeze tip) | Role |
|---|---|---|
| State machine | `app/domain/recovery.py` | Legal transitions / terminals |
| Assertion contract | `app/domain/assertion.py` | Signed fields, TTL, roles |
| Recovery Service | `app/application/recovery_service.py` | Mutations + TX + audit |
| Assertion store | `app/application/assertion_store.py` | Sign / quorum / revoke |
| Link store | `app/application/recovery_link_store.py` | Create / revoke links |
| Case store | `app/application/recovery_case_store.py` | Durable cases + ops |
| Audit store | `app/application/recovery_audit_store.py` | Append-only + allowlist |
| HTTP | `app/api/routes/recovery.py` | Thin transport |
| Schemas | `app/schemas/recovery.py` | Request/response shapes |

### 2.2 Case fields already available for VLIS binding

| Field | Current use | VLIS use |
|---|---|---|
| `subject_user_id` | Canonical Supabase UUID | Binding target |
| `claimed_legacy_identity_ref` | Claimed legacy ref | Binding target |
| `evidence_hash` | Opaque hash for quorum | **= VLIS `package_hash`** |
| `evidence_type` | Free string | **= `vlis_bcmp_mtc_v1`** (normative) |
| `operation_key` | Idempotency | Unchanged |
| `state` / `state_version` | CAS | Unchanged |

### 2.3 Gap analysis (why integration is needed)

| Step | Frozen behavior | Gap vs VLIS-BCMP |
|---|---|---|
| `create_case` | DRAFT→EVIDENCE_PENDING; duplicate open blocked | OK — no change |
| `submit_evidence` | Accepts any hash → READY_FOR_REVIEW | **Missing MTC + binding + attestation seal** |
| `create_assertion` | Signs over `case.evidence_hash`; four-eyes | OK if hash is VLIS-backed |
| Quorum / EC-09 | Hash mismatch invalidates approvals | OK — package change regenerates hash |
| `create_link` | Requires APPROVED + quorum | OK — no VLIS logic needed |
| Audit | Append-only; detail allowlist | Needs **allowlist extensions** for VLIS codes (additive) |

**Single semantic hole:** evidence authority. Everything else is already correct
once evidence is server-sealed.

---

## 3. Integration Principles

1. **Adjacent, not invasive** — VLIS owns attestations/packages/MTC; Recovery
   owns case/assertion/link/audit authority.  
2. **One choke point** — only evidence acceptance consults VLIS.  
3. **Hash continuity** — `package_hash` ≡ `evidence_hash` ≡
   `evidence_reference_hash` on assertions.  
4. **Fail-closed defaults** — missing package, failed MTC, expired attestation,
   binding failure → no READY.  
5. **No client-computed trust** — clients may upload bytes; they never assign
   trust levels or forge attestations.  
6. **No new link authority** — only Recovery Service creates/revokes links.  
7. **Additive audit** — new event types / allowlist keys; never rewrite history.  
8. **Feature-flagged enablement** — until flag on, behavior stays as frozen
   (or stricter fail-closed in staging — see §10).  

---

## 4. Target Architecture

```text
                    ┌─────────────────────────────────────┐
                    │ Thin Recovery Console / Reviewer API │
                    └───────────────┬─────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
 ┌─────────────────┐    ┌────────────────────┐    ┌──────────────────┐
 │ VLIS Module     │    │ Recovery Service   │    │ Systems of Record│
 │ (NEW, adjacent) │    │ (FROZEN contracts) │    │ billing / IdP /  │
 │                 │    │                    │    │ legacy profile   │
 │ challenges      │    │ create_case        │    └────────▲─────────┘
 │ attestations    │───▶│ submit_evidence ◀──┼─ choke ────┘
 │ evidence items  │    │ create_assertion   │    (verify seal)
 │ package seal    │    │ create/revoke link │
 │ MTC evaluate    │    │ audit TX           │
 └─────────────────┘    └────────────────────┘
```

### 4.1 Responsibility split

| Concern | Owner |
|---|---|
| Issue / expire / revoke attestations | VLIS Attestation Issuer |
| Store evidence items + compute `package_hash` | VLIS Evidence Packager |
| Evaluate MTC + binding | VLIS MTC Gate |
| Persist sealed package record | VLIS Package Store |
| Case state transitions | Recovery Service (unchanged legality) |
| Sign assertions / four-eyes / links | Recovery Service (unchanged) |
| Append-only business audit | Recovery Audit (additive fields) |
| VLIS-specific audit trail | VLIS audit events **or** recovery audit with `vlis.*` actions |

### 4.2 Rejected integration shapes

| Shape | Why rejected |
|---|---|
| Embed MTC inside `create_assertion` | Too late — would allow READY without proof; reviewers see invalid queue |
| Client sends trust score into `evidence_type` | Client authority |
| Bypass `submit_evidence`; jump to APPROVED | Breaks state machine / four-eyes |
| Re-enable legacy JWT as evidence | A.3 non-goal |
| Auto-link when MTC-H1 passes | Automatic linking forbidden |
| Fork parallel “fast recovery” API | Dual authority; contract dilution |

---

## 5. The Choke Point: `submit_evidence`

### 5.1 Current contract (frozen, keep)

Inputs: `case_id`, `reviewer_id`, `operation_key`, `evidence_hash`, `evidence_type`  
Effects (successful path from EVIDENCE_PENDING): set hash/type →
`READY_FOR_REVIEW` · idempotent on `operation_key` · EC-09 on hash change.

### 5.2 Additional preconditions (design — future impl)

When VLIS enforcement flag is **on**, `submit_evidence` succeeds only if
**all** hold:

| # | Precondition | Fail code (proposed) |
|---|---|---|
| P1 | Sealed VLIS package exists for `case_id` | `vlis_package_required` |
| P2 | `evidence_hash == package.package_hash` | `vlis_hash_mismatch` |
| P3 | `evidence_type == "vlis_bcmp_mtc_v1"` (exact) | `vlis_evidence_type_invalid` |
| P4 | `package.mtc_pass == true` under `mtc_v1` | `vlis_mtc_failed` |
| P5 | Binding check recorded pass for same subject + legacy_ref | `vlis_binding_failed` |
| P6 | Package not revoked; all contributing Medium/High attestations unexpired at seal time (and still unexpired at submit, or re-seal required) | `vlis_attestation_expired` |
| P7 | Package `subject_user_id` / `legacy_ref` match case fields | `vlis_identity_mismatch` |

On failure: **no state advance** (remain `EVIDENCE_PENDING` or prior
non-READY state per existing rules). Fail-closed.

### 5.3 What stays identical after the gate

Once READY:

- `create_assertion` still signs `evidence_reference_hash=case.evidence_hash`
- Four-eyes / EC-04 unchanged  
- Quorum still hash-scoped  
- EC-09 still fires if a new seal produces a new hash and is submitted  
- Link create/revoke unchanged  
- `POLICY_VERSION = "manual-recovery-a3-v1"` on assertions **unchanged**  
  (MTC version lives on the VLIS package + `evidence_type`, not by forking
  assertion policy)

### 5.4 EC-09 compatibility

```text
New evidence item / attestation revoke
        → package resealed → new package_hash
        → submit_evidence(new_hash)
        → case back toward EVIDENCE_PENDING then READY (existing logic)
        → prior approvals invalid for quorum (existing hash mismatch)
```

No new EC required; VLIS reseal is just a new hash source.

---

## 6. VLIS Module Design (logical — not implemented)

### 6.1 Logical stores

#### `vlis_attestations`

| Column (logical) | Notes |
|---|---|
| `attestation_id` | UUID PK |
| `case_id` | FK logical to recovery case |
| `source_id` | S1..S10 |
| `trust_level` | High \| Medium \| Low (server-assigned) |
| `subject_user_id` | Must match case |
| `legacy_ref` | Must match case |
| `content_hash` | Normalized payload hash |
| `issuer` | `system` |
| `expires_at` | Short TTL |
| `revoked_at` | Append-only revoke |
| `mac_or_signature` | Server integrity |
| `operation_key` | Idempotency |

#### `vlis_evidence_items`

| Column | Notes |
|---|---|
| `item_id` | UUID |
| `case_id` | |
| `source_id` | |
| `kind` | `server_attestation` \| `upload` \| `retrieved_record` |
| `attestation_id?` | Required if kind=server_attestation |
| `content_hash` | |
| `trust_level` | Server-assigned |
| `collected_at` | |

#### `vlis_packages`

| Column | Notes |
|---|---|
| `package_id` | UUID |
| `case_id` | Unique **active** seal per case (new seal supersedes) |
| `package_hash` | Canonical hash over items |
| `mtc_rule` | `H1` \| `M2` \| `M1L2` \| null |
| `mtc_pass` | boolean |
| `binding_pass` | boolean |
| `policy_version` | `mtc_v1` |
| `sealed_at` | |
| `superseded_at` | Prior seals retained append-only |
| `operation_key` | Idempotent seal |

Raw uploads (if any) live in a **separate encrypted blob store**; only hashes
enter these tables.

### 6.2 VLIS API surface (proposed, additive)

All reviewer-authenticated (same recovery reviewer JWT). Prefer nesting under
recovery to keep one console auth boundary:

```text
POST /v1/recovery/cases/{case_id}/vlis/challenges
POST /v1/recovery/cases/{case_id}/vlis/challenges/{id}/complete
POST /v1/recovery/cases/{case_id}/vlis/items          # register item / upload meta
POST /v1/recovery/cases/{case_id}/vlis/packages:seal  # compute hash + MTC
GET  /v1/recovery/cases/{case_id}/vlis/packages/active
POST /v1/recovery/cases/{case_id}/vlis/attestations/{id}/revoke
```

Then existing:

```text
POST /v1/recovery/cases/{case_id}/evidence   # choke point verifies active package
```

Thin console may later display MTC status **read-only**; policy remains server-side.

### 6.3 Challenge adapters (systems of record)

| Adapter | Source | Output |
|---|---|---|
| Email challenge | Legacy profile email | Medium attestation S2 |
| Phone challenge | Legacy profile phone | Medium attestation S3 |
| Billing match | Payments SoR | Medium attestation S7 |
| Org connector | IdP/HR | Medium/High S10 |
| Capability challenge | One-time hashed legacy secret | Medium/High S4 |
| KYC vendor | External | High S1 |

Adapters **never** write identity links. They only emit attestations.

---

## 7. End-to-End Operational Sequence

```text
1) Reviewer creates case
   RecoveryService.create_case
   → EVIDENCE_PENDING
   (unchanged)

2) Collect VLIS materials while EVIDENCE_PENDING
   VLIS challenges / items / attestations
   → case state unchanged

3) Seal package
   VLIS.seal → package_hash, mtc_pass, binding_pass
   → audit vlis.mtc_evaluated / vlis.package_sealed
   → case state still EVIDENCE_PENDING

4) Submit evidence (choke point)
   RecoveryService.submit_evidence(
     evidence_hash=package_hash,
     evidence_type="vlis_bcmp_mtc_v1"
   )
   → verifies P1–P7
   → READY_FOR_REVIEW   (same transition as today)

5) Four-eyes assertions
   create_assertion ×2
   → AWAITING_SECOND_APPROVAL → APPROVED | REJECTED
   (unchanged; hash-scoped quorum)

6) Link
   create_recovery_link
   → LINK_CREATED + transactional audit
   (unchanged)

7) Revoke paths
   attestation revoke → may require reseal (new hash) → EC-09 behavior
   assertion/link revoke → existing A.3 paths
```

### 7.1 Happy path (compact)

```text
DRAFT → EVIDENCE_PENDING → [VLIS seal] → READY_FOR_REVIEW
     → AWAITING_SECOND_APPROVAL → APPROVED → LINK_CREATED
```

### 7.2 Fail-closed examples

| Situation | Result |
|---|---|
| Seal with `mtc_pass=false` | Cannot pass choke; stay EVIDENCE_PENDING |
| Submit hash ≠ active package | `vlis_hash_mismatch` |
| Submit without VLIS (flag on) | `vlis_package_required` |
| Attestation expires after seal, before submit | `vlis_attestation_expired` or force reseal |
| Evidence items added after READY | Reseal → new hash → EC-09 demotion path |
| Client forges attestation | MAC/signature fail; item rejected |

---

## 8. Minimal Future Change Set (when Stream C implements)

Design budget: **smallest possible touch to frozen Recovery Service**.

### 8.1 Allowed touches (future)

| Change | Scope | Contract impact |
|---|---|---|
| Guard at start of `submit_evidence` calling `VlisPackageStore.assert_submittable(...)` | ~one function call + error mapping | Preconditions only |
| Map new `RecoveryError` codes in `recovery.py` `_http_error` | HTTP layer | Additive |
| Extend `AUDIT_DETAIL_ALLOWLIST` with VLIS scalars | `mtc_rule`, `package_id`, `attestation_id`, `vlis_policy_version` | Additive allowlist |
| Optional audit actions `vlis_package_verified` on successful submit_evidence detail | Same TX | Additive |
| Feature flag `VLIS_EVIDENCE_ENFORCEMENT` | Config | Ops |

### 8.2 Forbidden touches

| Change | Why forbidden |
|---|---|
| Alter `ALLOWED_TRANSITIONS` | Contract change |
| Alter quorum rules / four-eyes identity checks | Contract change |
| Let VLIS call `create_recovery_link` | Authority matrix violation |
| Client-supplied `trust_level` | Trust model violation |
| Change assertion `POLICY_VERSION` constant as a silent fork | Confuses REP lineage; use package policy instead |
| Soft-fail MTC (warn but READY) | Breaks fail-closed |
| Write `verified`/`linked` outside link lifecycle | Blocker regression |

### 8.3 What does **not** need changes

- `create_case`, `create_assertion`, `revoke_assertion`  
- `create_recovery_link`, `revoke_recovery_link`  
- `cancel_case`, expiry machinery  
- Durable case/link/assertion table shapes (VLIS tables are new)  
- Thin console security model (still no policy in HTML)  

---

## 9. Audit Integration

### 9.1 Recovery ledger (A.3.7) — additive

On successful choke-point submit, include allowlisted detail such as:

- `evidence_type` (already allowed) = `vlis_bcmp_mtc_v1`  
- `package_id`  
- `mtc_rule`  
- `vlis_policy_version`  

Action name can remain `submit_evidence` (existing) with richer detail, **or**
emit an additional append-only event `vlis_package_verified` in the same TX
if dual events are preferred for REP clarity.

### 9.2 VLIS ledger (recommended)

Separate append-only stream for package lifecycle:

| Event | When |
|---|---|
| `vlis.attestation_issued` | Challenge success |
| `vlis.attestation_revoked` | Explicit revoke |
| `vlis.item_added` | Item registered |
| `vlis.mtc_evaluated` | Pass/fail + rule |
| `vlis.package_sealed` | New package_hash |
| `vlis.package_superseded` | Reseal |

Same TX rules when a VLIS write is part of a recovery mutation that advances
state: recovery audit failure still rolls back business effect (EC-05).

### 9.3 Privacy

- No raw ID images, OTPs, PANs, or JWTs in audit detail (existing sanitize).  
- Attestation `content_hash` only.  
- Restricted blobs outside audit ledger.

---

## 10. Feature Flag & Migration of Behavior

| Flag | Off (default at freeze) | On |
|---|---|---|
| `VLIS_EVIDENCE_ENFORCEMENT` | Today's accept-any-hash behavior **or** staging-strict reject | Choke-point P1–P7 enforced |

**Recommendation for production enablement order:**

1. Deploy VLIS tables/APIs with enforcement **off** (shadow seal + metrics).  
2. Enable enforcement in staging → prove tests.  
3. Enable enforcement in production **before** any claim that manual recovery
   is OPERATIONAL.  
4. Never enable automatic linking as part of this flag.

Shadow mode (optional): accept hash but record whether VLIS would have passed;
does not authorize weaker security in prod once OPERATIONAL is claimed.

---

## 11. Reviewer UX Integration (thin client)

No policy in HTML (A.3.5 preserved).

Display-only additions later:

- Active package hash (short)  
- MTC rule + pass/fail  
- Attestation list (source_id, trust, expiry)  
- Binding pass/fail  

Actions still: create case → (VLIS assist endpoints) → submit evidence →
assert → link/revoke. Server remains authority.

---

## 12. Error Code Catalog (additive)

| Code | HTTP | Meaning |
|---|---|---|
| `vlis_package_required` | 409 | No active sealed package |
| `vlis_hash_mismatch` | 409 | evidence_hash ≠ package_hash |
| `vlis_evidence_type_invalid` | 400 | evidence_type not normative |
| `vlis_mtc_failed` | 409 | MTC not satisfied |
| `vlis_binding_failed` | 409 | Binding check failed |
| `vlis_attestation_expired` | 409 | Contributing attestation expired |
| `vlis_identity_mismatch` | 409 | Package identity ≠ case identity |
| `vlis_attestation_invalid` | 403 | Bad MAC / forged attestation |
| `vlis_seal_conflict` | 409 | CAS / concurrent seal |

Existing A.3 codes unchanged.

---

## 13. Security Contract Preservation Matrix

| Contract | Integration preservation |
|---|---|
| Fail-closed | Choke-point denies READY without seal/MTC/binding |
| Four-eyes | Untouched; still two distinct reviewers |
| Append-only audit | Additive events/keys only |
| Signed assertions | Still Recovery Service–signed over case hash |
| Transaction guarantees | VLIS verify + case persist + audit in same TX at submit |
| Idempotency | Existing `operation_key`; VLIS seal/challenge keys separate |
| Replay protection | Attestation TTL; package supersede; assertion TTL |
| EC-01..EC-12 | Remain normative; EC-09 covers reseal |
| Authority matrix | VLIS cannot create links or sign assertions |
| Automatic linking | Still DISABLED |

---

## 14. Test Plan Outline (for Stream C — not run now)

### 14.1 Unit / integration (future)

1. Seal with MTC-H1/M2/M1L2 → submit → READY.  
2. Seal with mtc_pass=false → submit rejected; state unchanged.  
3. Hash mismatch → rejected.  
4. Wrong evidence_type → rejected.  
5. Expired attestation → rejected or reseal required.  
6. Reseal after first approval → EC-09 demotion; new assertions required.  
7. Four-eyes still rejects same reviewer.  
8. Audit failure on submit rolls back READY transition.  
9. Idempotent submit with same operation_key.  
10. VLIS cannot be used to call link create without APPROVED quorum.  
11. Flag off vs on behavior matrix.  
12. Negative: client-supplied trust_level ignored/rejected.

### 14.2 Regression

Full A.3.1–A.3.7 suite must remain green with enforcement off; with
enforcement on, update evidence fixtures to use sealed packages.

---

## 15. Risk Analysis (integration-specific)

| Risk | Mitigation |
|---|---|
| Scope creep rewriting RecoveryService | Choke-point-only rule in §8 |
| Dual evidence authorities (old free hash + VLIS) | Flag on = VLIS exclusive for READY |
| Package store out of TX with case update | Same DB session/TX at submit |
| Reviewers bypass VLIS via direct hash | Enforcement makes bypass fail |
| Confusion with Stream B2 containment | Explicit naming in §0; both required |
| Premature OPERATIONAL claim | OPERATIONAL only after flag on + tests + Council |

---

## 16. Open Questions

| # | Question | Default |
|---|---|---|
| IQ1 | VLIS audit in recovery ledger vs separate table? | Separate `vlis_*` events + recovery detail on submit |
| IQ2 | Shadow mode in production before enforce? | Yes, short window; no OPERATIONAL claim during shadow |
| IQ3 | Who may call VLIS challenge APIs — reviewer only or claimant too? | Reviewer-orchestrated v1; claimant later behind authz design |
| IQ4 | Exact canonical serialization for `package_hash`? | Spec in Stream C; must be stable + tested |
| IQ5 | Is `evidence_type` enum frozen to one value? | Yes for v1: `vlis_bcmp_mtc_v1` only when flag on |

---

## 17. Recommended Decision

**Adopt Adjacent VLIS + `submit_evidence` choke-point integration.**

- Stream A defines *what counts as proof* (MTC / sources).  
- Stream B (this doc) defines *where it attaches* without contract changes.  
- Stream B2 still closes client-authority routes.  
- Stream C implements the module + one guard + tests.  
- Stream D is Council/`RESOLVED`.

### Success criteria for *this* design

- [x] Frozen pipeline mapped  
- [x] Single integration seam identified  
- [x] Minimal future change set listed  
- [x] Forbidden changes listed  
- [x] Sequences for happy/fail paths  
- [x] Audit / flag / error model  
- [x] Contract preservation matrix  
- [x] No production code modified  

### Explicit non-claims

- BLK-001 is **not** RESOLVED  
- Manual recovery is **not** yet OPERATIONAL  
- Release gate remains **CLOSED**  

---

## 18. Document control

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-18 | Initial Stream B Architecture Integration DESIGN_DRAFT |

**Approval needed:** Identity Authority · Security Authority · Recovery Service
owner (inform)  

**Next:** Authority approval → Stream B2 containment design/impl planning →
Stream C implementation plan (still gated).

---

## Appendix A — Mapping to Stream A artifacts

| Stream A concept | Integration binding |
|---|---|
| EvidencePackage.package_hash | `v1_recovery_cases.evidence_hash` |
| MTC pass | `vlis_packages.mtc_pass` checked at choke point |
| Server attestation | `vlis_attestations` row referenced by items |
| Reviewer decision tree | Unchanged; operates only after READY |
| Revocation of attestation | Supersede package → EC-09 via new hash |

## Appendix B — Standing order

```text
Until BLK-001 is RESOLVED with Council acceptance:
  — Release gate stays CLOSED
  — Automatic linking stays DISABLED
  — No PMP-01B / PMP-01C start
  — No ad-hoc production identity SQL
  — No production code from this design milestone
  — No security-contract edits disguised as “integration”
```
