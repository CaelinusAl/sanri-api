# PMP-01A-BLK-001 — Stream B2: Containment and Abuse-Case Review

**Document type:** Hostile design review (no implementation)  
**Blocker ID:** `PMP-01A-BLK-001`  
**Stream:** B2 — Containment and Abuse-Case Review  
**Review target:** Stream B VLIS integration (`submit_evidence` choke point)  
**Depends on:** Stream A (VLIS-BCMP) · Stream B (Architecture Integration)  
**Status:** `REVIEW_COMPLETE` — containment decisions locked for Stream C entry  
**Freeze tip:** `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab` / `pmp01a37-complete`  
**Last updated:** 2026-07-18  

```text
Authority Level: Design review — does not change production behavior
NO CODE · NO ARCHITECTURE CHANGE · NO SECURITY CONTRACT CHANGE
BLK-001 remains OPEN · Release gate CLOSED · Automatic linking DISABLED
```

**Scope note:** This review is the **VLIS integration hostility review**.
The original brief item “contain remaining client-authority legacy routes”
remains mandatory and is tracked here as **B2-L** (legacy route containment)
under Stream C entry criteria — not waived by this document.

---

## 1. Executive Summary

Stream B proposes that `submit_evidence` may advance a case to
`READY_FOR_REVIEW` only when a **server-sealed VLIS package** proves
hash match, normative `evidence_type`, MTC pass, binding pass, and valid
attestations. Everything after READY stays frozen.

**Containment verdict:** The single choke point is **necessary and sufficient
for API-path READY authority** only if the decisions in §3 are treated as
**hard invariants** (case-bound package identity, submit-time revalidation
inside one transaction, enforcement fail-closed, no legacy evidence fallback,
privileged-path controls). It is **not** sufficient alone against
compromised signing/attestor keys, direct DB/service-role abuse, or
uncontained legacy identity routes (B2-L).

This review does **not** resolve BLK-001, does not authorize Stream C
implementation start until §14 entry criteria are met, and does not open
the release gate.

| Question | Answer |
|---|---|
| Single choke point enough for READY via API? | **Yes, with locked invariants below** |
| Enough for whole-program containment? | **No — needs B2-L + privileged controls** |
| Architecture / contracts changed by this review? | **No** |
| Production code written? | **No** |
| BLK-001 status | **OPEN** |

---

## 2. Containment Verdict

### 2.1 Verdict statement

```text
CONDITIONAL PASS for Stream B integration shape
  — choke point retained (no architecture change)
  — additional HARD INVARIANTS required (specified here)
  — Stream C blocked until entry criteria (§14) acknowledged
```

### 2.2 What the choke point contains

| Contained (API path) | Not contained by choke point alone |
|---|---|
| Forged client `evidence_hash` without seal row | Stolen Recovery Service / attestor MAC key |
| Cross-case hash replay (if package is case-bound) | Direct SQL insert into cases/packages |
| Wrong `evidence_type` / MTC fail / binding fail | Legacy routes accepting client `user_id` (B2-L) |
| Stale attestations at submit (if revalidated) | Two colluding reviewers (four-eyes residual) |
| Flag-off bypass (if fail-closed rules locked) | Physical/ops compromise of DB backups |

### 2.3 Required decisions (locked by this review)

| # | Decision | Lock |
|---|---|---|
| D1 | Single choke point sufficiency | Sufficient for READY **API** authority iff invariants I1–I12 hold; insufficient as sole program control |
| D2 | Package identity / replay scope | Package is capability **only** for `(case_id, subject_user_id, legacy_ref, package_id)`; hash alone is not portable |
| D3 | Attestation freshness / revocation | Revalidate contributing set at **seal** and **submit**; revoke invalidates active package; post-READY revoke → EC-09-class demotion |
| D4 | Feature-flag fail-closed | In any environment claiming VLIS-backed recovery: enforcement **ON** required; OFF ⇒ READY forbidden (no legacy evidence fallback) |
| D5 | Transaction boundary | `assert_submittable` + case transition + audit = **one DB transaction** with row lock on active package |
| D6 | Direct-DB / privileged-role | No runbook minting; RLS deny; service-role only through app; alert on out-of-band writes |
| D7 | Stream C start gate | Only after §14 checklist accepted by Identity + Security Authority |

---

## 3. Required Invariants

These are **design locks** for Stream C. They do not change A.3 contracts;
they constrain VLIS + the choke-point guard.

| ID | Invariant |
|---|---|
| **I1** | READY via API requires active sealed package for **this** `case_id`. |
| **I2** | `evidence_hash` must equal active `package_hash` **and** that row’s identity tuple must equal the case tuple. |
| **I3** | `evidence_type` must equal exactly `vlis_bcmp_mtc_v1` when enforcement is on. No other type yields READY. |
| **I4** | `package_hash` is not a bearer token across cases, users, or legacy refs. |
| **I5** | MTC evaluation is server-only; trust levels are server-assigned; source categories are distinct; duplicate `source_id` cannot fill two slots. |
| **I6** | ≥1 contributing item must be a valid server attestation (Stream A MTC hard rule). |
| **I7** | Contributing Medium/High attestations must be non-revoked and unexpired at seal **and** at submit. |
| **I8** | Attestation revoke or package supersede clears `active` seal; submit against superseded/revoked package fails closed. |
| **I9** | Seal verification, state transition to READY, and recovery audit write occur in **one transaction**; any failure rolls back READY. |
| **I10** | Enforcement flag OFF in production-shaped deploy ⇒ `submit_evidence` cannot reach READY (fail-closed). |
| **I11** | No code path outside Recovery Service may set `evidence_hash` / advance READY / create links. |
| **I12** | Audit append failure aborts the business mutation (existing EC-05 extended to choke-point TX). |

---

## 4. Abuse-Case Matrix

Severity: **Critical** · **High** · **Medium** · **Low**

### AC-01 — Forged `package_hash`

| Field | Content |
|---|---|
| **Attack path** | Attacker/reviewer calls `submit_evidence` with a random or stolen hash string and `vlis_bcmp_mtc_v1`. |
| **Preconditions** | Enforcement on; no matching active package row (or row exists for another case). |
| **Expected containment** | Fail `vlis_package_required` / `vlis_hash_mismatch` / `vlis_identity_mismatch`. No READY. |
| **Required invariant** | I1, I2, I4 |
| **Audit evidence** | Failed submit attempt with reason code; no `submit_evidence` success to READY. |
| **Residual risk** | None on API path if I1–I2 enforced. |
| **Severity** | High (becomes Critical if enforcement off — see AC-16) |

### AC-02 — Replay of a valid package across cases

| Field | Content |
|---|---|
| **Attack path** | Seal package on Case A; submit same `package_hash` on Case B. |
| **Preconditions** | Two open/terminal cases; hash known. |
| **Expected containment** | Active package lookup is **by case_id**, not global hash index as authority. Case B has no active package with that identity → fail. Even if hash collides, I2 identity tuple check fails. |
| **Required invariant** | I1, I2, I4 |
| **Audit evidence** | `vlis_identity_mismatch` or `vlis_package_required` on Case B. |
| **Residual risk** | Accidental global unique index on hash alone could mislead operators — schema must not treat hash as globally authoritative. |
| **Severity** | Critical if mis-modeled; **contained** if case-bound |

### AC-03 — Replay across users or legacy identities

| Field | Content |
|---|---|
| **Attack path** | Package sealed for `(subject=U1, legacy=L1)` reused after case fields are… (cannot change on frozen case) or attacker creates Case B claiming L2 but copies hash from U1/L1 package. |
| **Preconditions** | Ability to create second case / know hash. |
| **Expected containment** | Package row stores subject + legacy_ref; P7 mismatch fails. Case open uniqueness (EC-07) limits parallel abuse. |
| **Required invariant** | I2, I4 |
| **Audit evidence** | `vlis_identity_mismatch` |
| **Residual risk** | If seal API allowed binding to different identity than case — must forbid at seal time too. |
| **Severity** | Critical if seal unbound; **contained** if seal+submit both bind |

### AC-04 — Package substitution after reviewer inspection

| Field | Content |
|---|---|
| **Attack path** | Reviewer views package P1; attacker reseals to P2 (weaker/stronger) before/during second eye; or swaps hash on case without reseal. |
| **Preconditions** | Reseal privilege or DB write. |
| **Expected containment** | Reseal supersedes active package → new `package_hash`. If case already READY/AWAITING/APPROVED, submit of new hash triggers existing EC-09 demotion. Assertions bound to old hash lose quorum. Thin UI must show current hash. Direct case.hash write without package row fails next quorum/link consistency checks if guard revalidates — see also AC-18. |
| **Required invariant** | I8, EC-09; recommend **re-read active package hash** at `create_assertion` equals `case.evidence_hash` (additive check, not contract change). |
| **Audit evidence** | `vlis.package_superseded`, EC-09 `evidence_changed`, assertion attempts against stale hash. |
| **Residual risk** | Reviewer confusion if UI caches old MTC view — operational, not authz. |
| **Severity** | High |

### AC-05 — Stale or revoked attestations

| Field | Content |
|---|---|
| **Attack path** | Seal while attestations valid; wait until expiry or revoke attestation; submit or continue review. |
| **Preconditions** | TTL elapsed or revoke API/DB. |
| **Expected containment** | **Submit:** revalidate contributing set → `vlis_attestation_expired` / package inactive. **Revoke:** active package invalidated immediately; submit fails until reseal. **Post-READY revoke:** invalidate package + treat as evidence invalid → demote per EC-09-class path (case leaves APPROVED/review with hash authority broken). |
| **Required invariant** | I7, I8 |
| **Audit evidence** | `vlis.attestation_revoked`, `vlis.package_superseded`/`invalidated`, failed submit codes. |
| **Residual risk** | Clock skew — use server UTC only; skew residual Low. |
| **Severity** | High |

### AC-06 — Split-package attacks

| Field | Content |
|---|---|
| **Attack path** | Present High attestation from Case A’s materials mixed with Mediums from Case B in one seal; or seal over items not all bound to same identity. |
| **Preconditions** | Item registration bugs allowing cross-case item references. |
| **Expected containment** | Every item/attestation row **must** carry `case_id` + identity tuple; seal refuses foreign items; package_hash canonicalization includes only same-case items. |
| **Required invariant** | I2, I5, I6 |
| **Audit evidence** | Seal failure reason `vlis_item_case_mismatch` (additive code). |
| **Residual risk** | Implementation bug in canonicalization — must be tested in Stream C. |
| **Severity** | Critical if items are cross-case joinable |

### AC-07 — Category inflation to satisfy MTC

| Field | Content |
|---|---|
| **Attack path** | Client/reviewer labels social proof as Medium; or adapter returns inflated trust_level. |
| **Preconditions** | Trust level accepted from client or misconfigured adapter. |
| **Expected containment** | Trust level **server-assigned** from `source_id` policy table (S9 always Low, etc.). Client field ignored/forbidden. Adapter results mapped through fixed policy, not free strings. |
| **Required invariant** | I5 |
| **Audit evidence** | Seal records `source_id` + server `trust_level`; mismatch attempts dropped. |
| **Residual risk** | Malicious change to policy table in DB — privileged control (AC-19). |
| **Severity** | High |

### AC-08 — Duplicate source counted twice

| Field | Content |
|---|---|
| **Attack path** | Two email challenges or two “payment” uploads counted as two Mediums for MTC-M2. |
| **Preconditions** | MTC counts items not distinct categories. |
| **Expected containment** | MTC slots require **distinct `source_id` categories** (Stream A). Second item same `source_id` does not add a new slot. Optional: at most one contributing attestation per `source_id` per package. |
| **Required invariant** | I5 |
| **Audit evidence** | `vlis.mtc_evaluated` with rule + contributing source set. |
| **Residual risk** | Sub-typing tricks (S4a vs S4b) — treat S4 subtypes as one category unless policy explicitly splits. |
| **Severity** | High |

### AC-09 — Colluding low-trust sources

| Field | Content |
|---|---|
| **Attack path** | Combine social + historical login + weak support narrative to hit MTC-M1L2 with one weak Medium (e.g. SIM-swapped phone). |
| **Preconditions** | MTC-M1L2 allowed; Medium channel compromised. |
| **Expected containment** | Stream A hard rules: S5/S9 at most one Low each; ≥1 server attestation; phone/email are Medium max. **Residual accepted:** M1L2 is weaker than H1 — mitigate with fraud signals, sampling, and reviewer checklist (not choke-point alone). Consider Stream C policy option: disallow M1L2 for production v1 (policy tighten, not architecture change). |
| **Required invariant** | I5, I6; four-eyes unchanged |
| **Audit evidence** | `mtc_rule=M1L2` visible for sampling audits. |
| **Residual risk** | **Medium** residual false-accept under M1L2 — product/security may forbid M1L2 at v1. |
| **Severity** | Medium (policy), High if M1L2 unrestricted in prod |

### AC-10 — Compromised server attestor

| Field | Content |
|---|---|
| **Attack path** | Attacker obtains attestation MAC/signing key or compromises challenge adapter to mint Medium/High attestations. |
| **Preconditions** | Key leak or adapter RCE. |
| **Expected containment** | Choke point **cannot** stop this alone. Controls: key isolation/HSM or KMS, rotation, dual-control for key access, adapter allowlist, anomaly rates, attestation revoke-all on incident, four-eyes still required for link. |
| **Required invariant** | I11 for link path; privileged controls §10 |
| **Audit evidence** | Attestation volume spikes; incident revoke storm. |
| **Residual risk** | **High** residual — accepted with ops controls; out of choke-point scope. |
| **Severity** | Critical (impact), containment = ops + four-eyes |

### AC-11 — TOCTOU between sealing and `submit_evidence`

| Field | Content |
|---|---|
| **Attack path** | Seal valid package; revoke attestation or supersede package before submit commits; submit still sees old snapshot. |
| **Preconditions** | Check-then-act without locking. |
| **Expected containment** | Submit TX: `SELECT … FOR UPDATE` active package row → revalidate attestations → transition → audit → commit. Revoke/supersede contending TX waits or fails. |
| **Required invariant** | I7, I8, I9 |
| **Audit evidence** | Serialization failures / failed submit after revoke. |
| **Residual risk** | Low if row locks used; High if verify is cache/read-replica stale. |
| **Severity** | Critical if unlocked; **contained** with I9 |

### AC-12 — Expiry during review (after READY)

| Field | Content |
|---|---|
| **Attack path** | Package submitted; attestations expire while waiting for second eye or before link. |
| **Preconditions** | Long review; short attestation TTL. |
| **Expected containment** | **Locked rule:** each sealed package carries `valid_until = min(contributing attestation expires_at)`. After READY, `get_case` / `create_assertion` / `create_link` must fail closed if `now >= package.valid_until` **or** any contributing attestation revoked — demote via EC-09-class path (`EVIDENCE_PENDING` / reject link). This is an **additive guard** on existing methods, not a state-machine rewrite. |
| **Required invariant** | I7, I8; additive post-READY validity check |
| **Audit evidence** | `vlis_package_expired_during_review`, demotion audit. |
| **Residual risk** | Operational pressure to lengthen TTL — policy governance. |
| **Severity** | High |

### AC-13 — Binding ambiguity

| Field | Content |
|---|---|
| **Attack path** | Legacy ref aliases (`"42"` vs `"0042"`), email case variance, merged accounts, multiple legacy rows sharing contact channels. |
| **Preconditions** | Non-canonical identifiers. |
| **Expected containment** | Canonicalization rules at seal: stable legacy primary key only; contact challenges bind to that PK’s stored contacts; ambiguous match → `vlis_binding_failed`. No “best effort” fuzzy link. |
| **Required invariant** | I2 |
| **Audit evidence** | Binding fail codes; no READY. |
| **Residual risk** | Dirty legacy data → false reject (availability), not false accept — accepted. |
| **Severity** | High (false accept if fuzzy); contained by canonical PK |

### AC-14 — Race between revoke and submit

| Field | Content |
|---|---|
| **Attack path** | Concurrent `attestation_revoke` and `submit_evidence`. |
| **Preconditions** | Parallel reviewers/ops. |
| **Expected containment** | Same as AC-11: row lock on active package + attestation rows; revoke sets package inactive in TX; submit either sees inactive and fails or completes first then revoke triggers post-READY invalidation path. |
| **Required invariant** | I8, I9 |
| **Audit evidence** | Ordering visible in append-only log. |
| **Residual risk** | Low with TX locks. |
| **Severity** | High without locks; contained with I9 |

### AC-15 — Feature-flag bypass

| Field | Content |
|---|---|
| **Attack path** | Deploy with `VLIS_EVIDENCE_ENFORCEMENT=off` to restore accept-any-hash READY; or toggle flag mid-incident. |
| **Preconditions** | Config access. |
| **Expected containment** | **D4 lock:** In production-shaped environments, OFF means READY **forbidden** (not “legacy open”). Shadow mode, if any, must not be available in production config profiles. Flag changes audited. |
| **Required invariant** | I10 |
| **Audit evidence** | Config change audit; all submits fail with `vlis_enforcement_required` when OFF in prod profile. |
| **Residual risk** | Ops mis-profile a deploy as non-prod — release checklist item. |
| **Severity** | Critical |

### AC-16 — Fallback to legacy evidence types

| Field | Content |
|---|---|
| **Attack path** | Submit `evidence_type=manual_notes` / `support_screenshot` / empty with arbitrary hash when enforcement “partial”. |
| **Preconditions** | Soft allowlist or flag semantics “prefer VLIS”. |
| **Expected containment** | **No fallback.** Only `vlis_bcmp_mtc_v1` yields READY when VLIS is the recovery evidence system. Other types → `vlis_evidence_type_invalid`. |
| **Required invariant** | I3, I10 |
| **Audit evidence** | Reject codes. |
| **Residual risk** | None if I3 absolute. |
| **Severity** | Critical if fallback exists |

### AC-17 — Direct DB insertion

| Field | Content |
|---|---|
| **Attack path** | INSERT/UPDATE `v1_recovery_cases` to READY with fake hash; or insert fake `vlis_packages` row. |
| **Preconditions** | SQL access / service role. |
| **Expected containment** | Choke point bypassed. Controls: RLS deny for `authenticated`; no human service-role for routine ops; break-glass dual-control; DB triggers optional to reject READY without matching package (defense-in-depth); anomaly alerts; forever forbidden as recovery path in ops manual. |
| **Required invariant** | I11; §10 |
| **Audit evidence** | Postgres logs / pgaudit; missing app audit chain is itself a signal. |
| **Residual risk** | **High** against malicious DBA — accepted; Council/ops. |
| **Severity** | Critical |

### AC-18 — Service-role misuse

| Field | Content |
|---|---|
| **Attack path** | App misuses service role in a debug endpoint; CI job writes packages; shared key in mobile app. |
| **Preconditions** | Key exposure or unsafe endpoint. |
| **Expected containment** | Service role only on server Recovery/VLIS paths; never in client; no admin “force READY” API; key rotation; separate keys per env. |
| **Required invariant** | I11 |
| **Audit evidence** | Gateway logs; absent force APIs in route inventory. |
| **Residual risk** | Medium (process). |
| **Severity** | Critical if client-exposed |

### AC-19 — Audit suppression

| Field | Content |
|---|---|
| **Attack path** | Advance READY while skipping audit write; or strip allowlist fields; or disable audit writer in tests left on in prod. |
| **Preconditions** | EC-05 regression / config. |
| **Expected containment** | Existing EC-05: audit failure rolls back mutation. Choke-point TX must include audit. No “best-effort audit” for READY. |
| **Required invariant** | I9, I12 |
| **Audit evidence** | N/A on success path — failure leaves no READY row. |
| **Residual risk** | Low if tests assert rollback. |
| **Severity** | Critical if suppressed |

### AC-20 — Partial transaction failure

| Field | Content |
|---|---|
| **Attack path** | Package marked used / case READY committed but audit or package lock fails mid-way; retry doubles effects. |
| **Preconditions** | Split TX between VLIS and Recovery. |
| **Expected containment** | Single TX (I9). Idempotent `operation_key` on submit. No “package consumed” side effect outside that TX. |
| **Required invariant** | I9; A.3 idempotency |
| **Audit evidence** | Replay returns prior result; one READY transition. |
| **Residual risk** | Low. |
| **Severity** | High if split TX |

### AC-21 — Idempotency collision

| Field | Content |
|---|---|
| **Attack path** | Reuse `operation_key` from Case A submit on Case B; or reuse seal key across packages. |
| **Preconditions** | Key reuse. |
| **Expected containment** | Existing `operation_key_conflict` when rebound to different case. VLIS seal keys scoped to `case_id`. Submit replay returns same case only. |
| **Required invariant** | A.3 ops map; I1 |
| **Audit evidence** | `operation_key_conflict` |
| **Residual risk** | Low. |
| **Severity** | Medium |

### AC-22 — Downgrade or rollback bypass

| Field | Content |
|---|---|
| **Attack path** | Redeploy build without VLIS guard; restore DB backup from pre-VLIS; migrate down tables but keep recovery open. |
| **Preconditions** | Ops rollback. |
| **Expected containment** | Release/ops rule: recovery READY path disabled unless guard present and enforcement on. Schema down-migration that drops `vlis_*` must coincide with recovery evidence API disable. REP/ops manual standing order. |
| **Required invariant** | I10, I11 |
| **Audit evidence** | Deploy manifest includes guard version; health check “vlis_enforcement=on”. |
| **Residual risk** | Medium (process discipline). |
| **Severity** | Critical if ignored |

### AC-23 — Seal without server attestation (MTC cheat)

| Field | Content |
|---|---|
| **Attack path** | Upload-only package claims MTC via inflated Lows. |
| **Preconditions** | I6 not enforced at seal. |
| **Expected containment** | Seal sets `mtc_pass=false` without server attestation; submit fails P4. |
| **Required invariant** | I5, I6 |
| **Audit evidence** | `vlis.mtc_evaluated` fail. |
| **Residual risk** | None. |
| **Severity** | High |

### AC-24 — Reviewer self-service without four-eyes (out of scope but checked)

| Field | Content |
|---|---|
| **Attack path** | Use VLIS to somehow mint link without second eye. |
| **Preconditions** | VLIS wrongly calls link API. |
| **Expected containment** | Authority matrix: VLIS cannot create links. Frozen A.3 four-eyes unchanged. |
| **Required invariant** | Stream B forbidden touches |
| **Audit evidence** | No link without quorum. |
| **Residual risk** | Colluding reviewers — residual Medium. |
| **Severity** | Critical if VLIS can link; else N/A |

---

## 5. Replay and Binding Rules (D2)

### 5.1 Package identity tuple

A sealed package is identified and authorized only as:

```text
PackageAuthority =
  (package_id, case_id, subject_user_id, claimed_legacy_identity_ref, package_hash)
```

`package_hash` is a **integrity digest**, not a portable capability.

### 5.2 Replay scope

| Replay attempt | Result |
|---|---|
| Same case, same hash, same `operation_key` | Idempotent success (A.3) |
| Same case, same hash, new `operation_key` | Allowed no-op or reject duplicate per existing persist rules — must not double-transition illegally |
| Different `case_id`, same hash | **Deny** |
| Same case after identity fields disagree with package | **Deny** (impossible if case immutable; defend anyway) |
| Superseded package_hash | **Deny** |

### 5.3 Binding rules

1. Legacy identifier = canonical primary key from legacy SoR (no aliases).  
2. Contact/payment/org challenges must resolve to that same PK.  
3. Ambiguity → fail closed (`vlis_binding_failed`).  
4. Binding check results are stored on the package at seal and re-checked at submit.

---

## 6. Expiry and Revocation Rules (D3)

| Event | Effect on active package | Effect on case |
|---|---|---|
| Attestation expires before submit | Package not submittable | Stay EVIDENCE_PENDING |
| Attestation revoked before submit | Invalidate active package | Stay EVIDENCE_PENDING |
| Attestation expires/revoked after READY, before quorum/link | Package `valid_until` / revoke invalidation | Demote (EC-09-class); approvals for old hash unusable |
| Package superseded (reseal) | Prior hash inactive | EC-09 if case was in review/approved |
| Assertion revoke | A.3 EC-02 | Unchanged |
| Link revoke | A.3 | Unchanged |

**Freshness checkpoints:** seal · submit · (additive) assertion · (additive) link-create.

**TTL guidance (policy, not architecture):** email/phone OTP attestations ≤ 24h;
package `valid_until` ≤ min(contributors); case TTL remains A.3 (72h) — whichever
comes first wins for validity.

---

## 7. Feature-Flag Rules (D4)

| Environment profile | `VLIS_EVIDENCE_ENFORCEMENT` | READY behavior |
|---|---|---|
| Production | **Must be ON** | Choke-point P1–P7 |
| Production | OFF | **READY forbidden** (`vlis_enforcement_required`) — not legacy open |
| Staging | ON for acceptance | Same as prod |
| Staging shadow (optional) | Explicit shadow flag ≠ enforcement off | May log would-fail; must not READY on weak path |
| Local/dev | May use test seals | Fixtures only |

**Forbidden flag semantics:** “off = accept any hash” in any profile that can
touch production data.

---

## 8. Transaction Requirements (D5)

```text
BEGIN
  LOCK active vlis_package for case_id (FOR UPDATE)
  Revalidate: identity, mtc_pass, hash, evidence_type, attestations, valid_until
  FAIL → ROLLBACK (no case mutation)
  Apply submit_evidence state transition (existing rules)
  Write recovery audit (and optional vlis_package_verified)
  COMMIT
```

- No read-replica for authorization reads.  
- No “verify in VLIS service HTTP call outside TX” without 2PC — prefer same DB
  session.  
- Partial failure ⇒ no READY (I9, I12).

---

## 9. Privileged-Role Controls (D6)

| Control | Requirement |
|---|---|
| RLS | `authenticated` deny-all on recovery + vlis tables (as A.3 cases) |
| Service role | Server-only; never shipped to clients |
| Force-READY API | **Must not exist** |
| SQL runbooks | May diagnose; must not mint READY/links; standing order |
| Break-glass | Dual-control + incident ticket + post-facto Council note |
| Key material | Attestation MAC/signing keys in secrets manager; rotation drill |
| Deploy health | Fail deploy/health if enforcement off in prod profile |
| B2-L | Legacy client-authority routes inventoried and fail-closed before OPERATIONAL claim |

---

## 10. Audit Requirements

Minimum evidence for hostile cases:

| Action | Must record |
|---|---|
| Seal | package_id, package_hash, mtc_rule, mtc_pass, binding_pass, source set |
| Submit success | package_id, evidence_type, mtc_rule, actor, operation_key |
| Submit fail | reason code (vlis_*) |
| Attestation revoke | attestation_id, package invalidation |
| Package supersede | old_hash, new_hash |
| Post-READY expiry demotion | package_id, from_state, to_state |
| Flag/config change | who/when/old/new (ops audit) |

Suppression ⇒ mutation abort (I12). Redaction rules from Stream A privacy model
unchanged.

---

## 11. Residual Risks

| Risk | Level | Disposition |
|---|---|---|
| Colluding reviewers | Medium | Accepted; sampling + revoke |
| Compromised attestor key | High | Ops/KMS; not choke-point-solvable |
| Malicious DBA / direct SQL | High | Process + monitoring; accepted residual |
| MTC-M1L2 false accept | Medium–High | Recommend forbid M1L2 in prod v1 policy |
| Dirty legacy data false reject | Medium | Availability tradeoff; fail closed |
| Rollback/redeploy without guard | Medium | Ops checklist / health gate |
| UI stale package view | Low | Read-only refresh |
| B2-L legacy routes still open | High | **Must close before OPERATIONAL** |

---

## 12. Choke-Point Sufficiency (D1 detail)

**Sufficient when:**

- Attack arrives through Recovery HTTP API, and  
- Invariants I1–I12 are implemented as specified, and  
- Enforcement fail-closed (D4), and  
- Post-READY validity checks (AC-12) are included in Stream C scope.

**Insufficient when:**

- Privileged DB/key compromise, or  
- Legacy identity routes remain client-authoritative (B2-L), or  
- Flag/rollback reopens accept-any-hash.

**Architecture decision:** **Retain single choke point** (no architecture
change). Do **not** add a second READY path. Strengthen with invariants and
B2-L — not with parallel authorities.

---

## 13. What Must Be Proven Before Stream C May Start (D7)

Stream C (implementation) may start only when Identity + Security Authority
acknowledge:

1. Stream A VLIS-BCMP design accepted (or explicitly accepted with listed deltas).  
2. Stream B choke-point integration accepted.  
3. **This B2 review** accepted, including invariants I1–I12 and decisions D1–D6.  
4. Prod flag semantics locked: OFF ⇒ READY forbidden (no legacy fallback).  
5. Package identity = case-bound tuple (not portable hash).  
6. TX boundary = single transaction with row lock (AC-11/14).  
7. Post-READY expiry/revoke demotion in Stream C scope (AC-12).  
8. MTC counting rules: distinct categories; no client trust; ≥1 server attestation.  
9. Policy call on M1L2: allowed with sampling **or** forbidden in v1 (explicit).  
10. B2-L plan committed: legacy client-authority route inventory + fail-closed
    work scheduled before any OPERATIONAL / Council RESOLVED claim.  
11. No production code proceeds under “temporary accept-any-hash”.  
12. Standing order unchanged: gate CLOSED, auto-link DISABLED, BLK-001 OPEN.

---

## 14. Stream C Entry Criteria (checklist)

- [ ] Authorities signed acceptance of A + B + B2 (this doc)  
- [ ] I1–I12 copied into Stream C implementation plan as acceptance tests  
- [ ] Abuse cases AC-01…AC-24 mapped to named tests (fail-closed asserts)  
- [ ] Feature-flag matrix implemented as specified in §7  
- [ ] Privileged-role controls §9 reflected in ops manual addendum (doc-only OK)  
- [ ] B2-L legacy route inventory started (may complete in parallel with C, but
      **OPERATIONAL claim waits for B2-L green**)  
- [ ] Explicit non-goals restated: no auto-link, no contract edits, no force-READY  

**Until then: Stream C must not start.**

---

## 15. Explicit Non-Claims

| Claim | Status |
|---|---|
| BLK-001 RESOLVED | **No** |
| Manual recovery OPERATIONAL | **No** |
| Release gate OPEN | **No** |
| Automatic linking enabled | **No** |
| Architecture changed | **No** |
| Security contracts changed | **No** |
| Production code landed | **No** |

---

## 16. Document control

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-18 | Hostile containment review complete; decisions D1–D7 locked |

**Approvers needed:** Identity Authority · Security Authority · (inform) Recovery
Service owner · (inform) Release Council  

**Next:** Authority acceptance → Stream C implementation plan under these
invariants (still no contract changes).

---

## Appendix A — Severity summary

| Severity | Abuse cases |
|---|---|
| Critical (if uncontained) | AC-02, AC-03, AC-06, AC-10, AC-11, AC-15, AC-16, AC-17, AC-18, AC-19, AC-22, AC-24 |
| High | AC-01, AC-04, AC-05, AC-07, AC-08, AC-12, AC-13, AC-14, AC-20, AC-23 |
| Medium | AC-09, AC-21 |
| Process / residual | Attestor key, DBA, M1L2, B2-L |

## Appendix B — Standing order

```text
Until BLK-001 is RESOLVED with Council acceptance:
  — Release gate stays CLOSED
  — Automatic linking stays DISABLED
  — No PMP-01B / PMP-01C start
  — No ad-hoc production identity SQL
  — No production code from this review milestone
  — No accept-any-hash READY path in production-shaped deploys
```
