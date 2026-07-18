# PMP-01A-BLK-001 — Team Focus Brief

**Blocker ID:** `PMP-01A-BLK-001`  
**Title:** Verified Legacy Identity Source Missing  
**Severity:** Critical  
**Category:** Identity / Security  
**Status:** `OPEN`  
**Program status:** PMP-01A = `BLOCKED` · Release gate = `CLOSED`  
**Owner:** PMP-01 Program  
**Last updated:** 2026-07-18  
**Stream A design:** `docs/blockers/PMP-01A-BLK-001-verified-legacy-identity-source-design.md` (`DESIGN_DRAFT`)  
**Stream B design:** `docs/blockers/PMP-01A-BLK-001-stream-b-architecture-integration.md` (`DESIGN_DRAFT`)  
**Stream B2 review:** `docs/blockers/PMP-01A-BLK-001-stream-b2-containment-abuse-review.md` (`REVIEW_COMPLETE`)  
**Stream C entry gate:** `docs/blockers/PMP-01A-BLK-001-stream-c-entry-gate-acceptance-pack.md` (`ENTRY_GATE_PENDING`)  
**L-06 resolution:** `docs/blockers/PMP-01A-BLK-001-l06-resolution-decision.md` (`DECISION_DRAFT` — Option C+B recommended)

---

## Why the whole team focuses here now

| Track | State |
|---|---|
| A.3.1–A.3.7 security core engineering | **Complete** (91 tests PASS) |
| A.3.8 PostgreSQL operational validation | **PASS** |
| A.3.9 release readiness | **NO-GO** (assessment filed) |
| REP-001 | **Filed** — status `BLOCKED` |
| Operations Manual | **Filed** |
| Remaining Critical trust/technical stopper for release | **This blocker** |

Engineering for the recovery security core is done. Packaging (REP + Ops Manual)
is filed. **Do not start PMP-01B / PMP-01C.** Do not invent automatic linking.
All capacity goes to resolving `PMP-01A-BLK-001` under the criteria below.

---

## One-sentence problem

There is **no server-side verified legacy identity source** that can safely
prove “this Supabase user is that legacy account,” so production linking and
migration remain forbidden.

---

## What this blocker is (and is not)

| It is | It is not |
|---|---|
| A **trust-model** blocker | A missing Alembic migration |
| Why automatic linking stays DISABLED | Fixed by UI polish |
| Why release gate stays CLOSED | Fixed by more recovery API features |
| Required before PMP-01B/C | Resolved by client-sent `user_id` / email / device |

Email, display name, device, IP, fingerprint, default session, client
`legacy_user_id`, or unsigned/custom tokens are **not** identity proof.

---

## Official metadata

| Field | Value |
|---|---|
| Introduced | PMP-01A |
| Blocks | PMP-01B, PMP-01C, Context Engine, Project Engine, Production Migration |
| Security impact | Cross-user association and account takeover risk |
| Automatic linking | Must remain `DISABLED` until RESOLVED |
| Release gate | Must remain `CLOSED` until remaining open risks close |

Source: `docs/pmp-01-secure-migration-execution-plan.md`

---

## Resolution criteria (all required)

`PMP-01A-BLK-001` may be marked `RESOLVED` only when **all** of the following
are true:

1. **Server-side verified legacy identity source exists**  
2. **Client-controlled identity is authoritative in no flow**  
3. **Manual recovery policy is integrated into the execution flow**  
   (recovery core A.3.1–A.3.7 is the intended path — do not bypass with SQL)  
4. **Related security tests pass**  
5. **Approval, revoke, and audit implementation are verified**  
6. **Release Council accepts the blocker resolution** (recorded in REP +
   Governance Health Check)

Until then: no PMP-01B, no PMP-01C, no production mapping.

---

## Current trust model (evidence summary)

1. Canonical V1 Supabase JWT `sub` UUID — server-side verifiable.  
2. Legacy HS256 token path — decoder fail-closed; no active legacy session verifier.  
3. Some legacy routes still accept client-controlled signals (`user_id`,
   `X-User-Id`, `device_fp`, default session) — **unsafe as proof**.

Documented hotspots (from PMP plan; re-verify during work):

- `app/routes/events.py`  
- `app/routes/activity.py`  
- `app/routes/device.py`  
- `app/services/auth.py` (legacy decoder returns `None` by design)

---

## Team workstreams (only these)

### Stream A — Define the verified legacy source

**Goal:** Specify and implement (or integrate) a **server-side** proof that a
legacy account is the same person as a canonical V1 user.

Allowed directions (pick one Council-approved design; do not freestyle):

- Cryptographically verifiable legacy credential checked only on server  
- Out-of-band proof bound into manual recovery evidence + four-eyes  
- Provider-attested migration token with server verification  

Forbidden directions:

- Trust mobile/web `user_id` headers  
- “Email match = link”  
- Device fingerprint linking  
- Silent DB updates to `verified` / `linked`

**Exit artifact:** short design note + threat model + test list (attach to REP).  
**Filed:** `docs/blockers/PMP-01A-BLK-001-verified-legacy-identity-source-design.md`  
(Recommended architecture: **VLIS-BCMP** — Bounded Composite Manual Proof.  
Awaiting Identity + Security Authority approval before any implementation.)

### Stream B — Architecture Integration

**Goal:** Design how VLIS-BCMP attaches to the frozen A.3 recovery pipeline
with **minimal surface change** and **no security-contract changes**.

**Exit artifact:** integration design (choke point, ownership split, flags,
additive audit, forbidden touches).

**Filed:** `docs/blockers/PMP-01A-BLK-001-stream-b-architecture-integration.md`  
(Recommended: **Adjacent VLIS + `submit_evidence` choke-point**.  
Awaiting Identity + Security Authority approval before any implementation.)

### Stream B2 — Containment and Abuse-Case Review

**Goal:** Hostile review of VLIS choke-point integration; lock invariants,
replay/binding/expiry/flag/TX/privileged controls; define Stream C entry gate.
Also retain **B2-L**: contain remaining client-authority legacy routes before
any OPERATIONAL claim.

**Exit artifact:** abuse-case matrix + decisions D1–D7 + Stream C entry criteria.

**Filed:** `docs/blockers/PMP-01A-BLK-001-stream-b2-containment-abuse-review.md`  
(**Verdict:** CONDITIONAL PASS — choke point retained; I1–I12 required;  
Stream C blocked until authorities accept entry criteria.)

### Stream C — Wire proof into manual recovery only

**Goal:** Implement Stream A+B design under B2 invariants: VLIS module +
choke-point guard so the only way to create a verified identity association
is the recovery flow (reviewer JWT → VLIS seal → evidence → assertions →
four-eyes → link → durable audit).

**Exit artifact:** end-to-end security tests + audit evidence samples (redacted).  
**Entry pack:** `docs/blockers/PMP-01A-BLK-001-stream-c-entry-gate-acceptance-pack.md`  
**Entry status:** `ENTRY_GATE_PENDING` — Stream C must not start until
`ENTRY_GATE_ACCEPTED` (four authority signatures).

### Stream D — Council resolution package

**Goal:** Update REP-001 (or REP-002) with resolution evidence; get signatures.

**Exit artifact:** Council decision `RESOLVED` recorded; only then reconsider
release-gate / PMP-01B readiness.

---

## Explicit non-goals (do not work on these yet)

- PMP-01B Migration Engine  
- PMP-01C Resource Migration  
- PMP-01E Rollback Engine implementation (ops restore is enough for now)  
- New recovery features beyond what BLK-001 resolution requires  
- Opening `V1_CHAT_PERCENTAGE` / product rollout as a substitute for identity proof  
- Automatic linking flags or batch link scripts  

---

## Definition of done (team)

- [x] Stream A design drafted (`DESIGN_DRAFT` — VLIS-BCMP)  
- [x] Stream B architecture integration drafted (`DESIGN_DRAFT` — choke-point)  
- [x] Stream B2 containment / abuse-case review filed (`REVIEW_COMPLETE`)  
- [x] Stream C Entry Gate Acceptance Pack filed (`ENTRY_GATE_PENDING`)  
- [x] L-06 resolution decision filed (`DECISION_DRAFT` — recommend Option C+B)  
- [ ] L-06 decision + entry gate signed by named authorities (no false ACCEPT)  
- [ ] Entry gate `ENTRY_GATE_ACCEPTED`  
- [ ] L-06.1–L-06.8 contained + `L06-T*` green before OPERATIONAL  
- [ ] Stream C implementation + recovery-only path green  
- [ ] No client-controlled identity remains authoritative  
- [ ] Security tests for resolution criteria green  
- [ ] REP updated; Council marks BLK-001 `RESOLVED`  
- [ ] Program status snapshot updated (gate still follows Council — not auto-OPEN)

---

## Related evidence

| Artifact | Path |
|---|---|
| Stream A design (VLIS-BCMP) | `docs/blockers/PMP-01A-BLK-001-verified-legacy-identity-source-design.md` |
| Stream B architecture integration | `docs/blockers/PMP-01A-BLK-001-stream-b-architecture-integration.md` |
| Stream B2 containment / abuse review | `docs/blockers/PMP-01A-BLK-001-stream-b2-containment-abuse-review.md` |
| Stream C entry gate acceptance pack | `docs/blockers/PMP-01A-BLK-001-stream-c-entry-gate-acceptance-pack.md` |
| L-06 resolution decision | `docs/blockers/PMP-01A-BLK-001-l06-resolution-decision.md` |
| REP-001 | `releases/REP-001/REP.md` |
| Operations Manual | `docs/operations/OPERATIONS-MANUAL.md` |
| PMP execution plan (blocker section) | `docs/pmp-01-secure-migration-execution-plan.md` |
| Freeze tip | `pmp01a37-complete` / `f7cc6b3` |

---

## Standing order

```text
Until BLK-001 is RESOLVED with Council acceptance:
  — Release gate stays CLOSED
  — Automatic linking stays DISABLED
  — No PMP-01B / PMP-01C start
  — No ad-hoc production identity SQL
```
