# PMP-01A-BLK-001 — L-06 Resolution Decision & Authority Review Preparation

**Document type:** Authority review preparation (no implementation)  
**Blocker ID:** `PMP-01A-BLK-001`  
**Related pack:** `PMP-01A-BLK-001-stream-c-entry-gate-acceptance-pack.md`  
**Item:** B2-L / **L-06** (`X-User-Id` client identity authority)  
**Status:** `DECISION_DRAFT` — awaiting authority ACCEPT/REJECT (no signatures recorded here)  
**Entry gate status:** remains **`ENTRY_GATE_PENDING`**  
**Date:** 2026-07-19  

```text
NO STREAM C CODE · NO FALSE APPROVALS · NO RECOVERY CONTRACT CHANGE
BLK-001 remains OPEN · Release gate CLOSED · Automatic linking DISABLED
Do not mark any authority as ACCEPT on their behalf
```

---

## 1. Executive Summary

L-06 was filed against `bilinc_alani` accepting `X-User-Id`. A full inventory
shows a **family** of routes that still treat a client-supplied header as
identity authority for memory, profile, premium checks, and related reads/writes.

**Critical finding for the recovery program:**

| Question | Answer |
|---|---|
| Can `X-User-Id` advance a recovery case to `READY_FOR_REVIEW`? | **No** |
| Can it create/mutate recovery cases, assertions, or links? | **No** |
| Can it bypass reviewer JWT on `/v1/recovery/*`? | **No** |
| Can it read/write another user’s memory/profile by spoofing the header? | **Yes** |
| Can it indirectly poison “who owns this legacy data” narratives used in VLIS evidence? | **Yes (indirect)** |
| Blocks Stream C coding start? | **No** — if authorities accept this resolution decision as the L-06 plan |
| Blocks OPERATIONAL / release gate / BLK-001 RESOLVED? | **Yes** until contained |

**Recommended decision:** **Option C** (JWT / canonical session is sole
authorization authority; `X-User-Id` is never authoritative), deployed with
**Option B** as a production kill-switch (`LEGACY_X_USER_ID_AUTH` default OFF
in production-shaped profiles). Option A alone is too abrupt for compatibility;
Option D alone is insufficient because bilinc already mutates account memory.

This document prepares signature-ready briefs. **No authority is marked ACCEPT.**
Entry gate remains **`ENTRY_GATE_PENDING`**.

---

## 2. L-06 Route Inventory

### 2.1 Helper: `parse_user_id` (`bilinc_alani.py`)

| Aspect | Detail |
|---|---|
| Read | `Header(None)` → `x_user_id` |
| Transform | Strips optional `X-User-Id:` prefix; `int()` parse |
| Trust | **Yes** — return value used as `user_id` |
| Authz | Effectively authenticates the caller as that integer user |
| Class | **authentication authority** (unsafe) |

### 2.2 Path table

| ID | Location | Method / route | Read header? | Trusted as identity? | Converts to user? | Authz / data effect | Classification |
|---|---|---|---|---|---|---|---|
| **L-06.1** | `app/routes/bilinc_alani.py` | `POST /bilinc-alani/ask` | Yes | Yes (or anon `0`) | `parse_user_id(..., allow_anonymous=True)` | Calls `run_sanri` → **load/save `user_memory` + `user_profiles`**, premium check, daily limits, events | **authentication authority** + **legacy compatibility** |
| **L-06.2** | same | `POST /bilinc-alani/deepen/accept` | Yes | Yes (or anon) | same | Writes `Event` with `user_id` string | **authentication authority** (telemetry attribution) |
| **L-06.3** | same | `GET /bilinc-alani/memory` | Yes | **Required** | `parse_user_id` (no anon) | **SELECT** `user_memory` for that id (cross-user read if spoofed) | **authentication authority** |
| **L-06.4** | same | `GET /bilinc-alani/profile` | Yes | **Required** | same | **SELECT** `user_profiles` for that id | **authentication authority** |
| **L-06.5** | `app/services/sanri_orchestrator.py` `run_sanri` | (callee of L-06.1) | N/A | Inherits `user_id` | N/A | Memory/profile R/W; not recovery | **downstream of authority** |
| **L-06.6** | `app/routes/memory_state.py` | `GET/POST /memory-state*` | Yes (fallback) | Yes if no Bearer match | `return int(x_user_id)` **without DB proof** | Read/refresh memory state for spoofed id | **authentication authority** |
| **L-06.7** | `app/routes/insights.py` | insights routes via `get_current_user` | Yes (fallback) | Yes if JWT absent/fails path | Lookup `users.id = int(x_user_id)` | Returns that user’s insight data | **authentication authority** (comment claims “dev fallback” but **not gated**) |
| **L-06.8** | `app/routes/matrix_rol.py` | `POST .../yorum` | Yes (required) | Yes | `get_or_create_user(db, x_user_id)` via `external_id` | Premium/self checks; may set name/birth_date; LLM yorum | **authentication authority** + **legacy compatibility** |
| **L-06.9** | `app/routes/admin_premium.py` | `POST /admin/grant-premium` | Yes | As **target subject**, after `X-Admin-Secret` | `get_or_create_user` | Grants premium to named external id | **admin target selector** (not self-auth) — keep distinct |
| **L-06.10** | Mobile client | — | Grep: **no** `X-User-Id` in `asksanri-mobile` sources | N/A | N/A | Mobile may still hit legacy ask via other builds/deep links | **legacy compatibility / residual clients** |
| **L-06.11** | `/v1/recovery/*` | Reviewer API | **No** | N/A | Reviewer from JWT only | Cases/assertions/links | **out of L-06 attack surface** (already contained) |

### 2.3 Not in scope as self-auth (reclassified)

| ID | Why different |
|---|---|
| L-06.9 admin grant | Header selects **victim/subject** of an admin action; authority is `X-Admin-Secret`. Still needs dual-control/ops hygiene; not the same bug as anonymous self-spoof. |

---

## 3. Authority Boundary Analysis

```text
UNTRUSTED CLIENT
  │
  ├─ X-User-Id  ──► bilinc / memory-state / insights fallback / matrix_rol
  │                    └── currently AUTHORITATIVE for integer/external user
  │
  └─ (no header on recovery)
         │
         ▼
TRUSTED RECOVERY ZONE (frozen A.3)
  Reviewer JWT → cases → VLIS (future) → assertions → links
```

| Boundary | Current state |
|---|---|
| Recovery identity | Server reviewer JWT only — **intact** |
| Legacy ask / memory identity | Client header — **broken trust boundary** |
| Canonical V1 Supabase JWT | Used on some v1 routes; **not** required on L-06.1–L-06.8 |
| Cross-user data plane | `user_memory` / `user_profiles` keyed by integer `user_id` — **spoofable** |

---

## 4. Exploitability Assessment

| Capability | Reachable via L-06 family? | Notes |
|---|---|---|
| Reach `READY_FOR_REVIEW` | **No** | Only `submit_evidence` on recovery service |
| Influence VLIS evidence ownership directly | **No** (no VLIS yet); **indirect Yes** later if reviewers trust poisoned memory exports | Spoofed writes alter legacy data plane |
| Access another user’s data | **Yes** | L-06.3/4/6/7; L-06.1 loads/saves victim memory if id known/guessed |
| Create/mutate recovery state | **No** | No recovery imports/calls from bilinc |
| Bypass JWT on recovery | **No** | |
| Bypass JWT on bilinc/memory-state/insights/matrix | **Yes** | Header replaces auth |
| Cross-tenant / cross-user | **Yes** | Shared DB; id spoofing |
| Create verified identity link | **No** | Auto-link DISABLED; link API separate |

**Severity for BLK-001 program:** High for **data-plane integrity** and
**OPERATIONAL/RESOLVED** claims; **not** a direct READY bypass. Must be
resolved before any claim that “client-controlled identity is authoritative
in no flow.”

---

## 5. Containment Options

### Option A — Remove `X-User-Id` completely

| | |
|---|---|
| **Change** | Delete header parsing; require canonical auth everywhere; 401 otherwise |
| **Security** | Strongest cleanup |
| **Compatibility** | Breaks any residual client sending only the header (matrix_rol, older apps) |
| **Migration** | Hard cut; needs coordinated client release |
| **Rollback** | Revert deploy |
| **Prod release** | Only after clients migrated |

### Option B — Accept only behind explicit non-production flag

| | |
|---|---|
| **Change** | `LEGACY_X_USER_ID_AUTH=1` enables header auth; **default 0 in production** |
| **Security** | Strong in prod if flag discipline holds (see AC-15 lessons) |
| **Compatibility** | Dev/staging can keep old clients |
| **Migration** | Gradual |
| **Rollback** | Flip flag (emergency only with audit) |
| **Prod release** | Allowed only with flag **OFF** |

### Option C — Untrusted hint; authority only from JWT / canonical session

| | |
|---|---|
| **Change** | If header present, **ignore for authz** (or log-only mismatch). Principal = verified JWT/`get_current_user_id` (Supabase/canonical). Anonymous ask may remain `user_id=0` with **no** cross-user memory read/write |
| **Security** | Correct trust model; aligns with constitution |
| **Compatibility** | Clients may keep sending header harmlessly |
| **Migration** | Soft; clients add Authorization at leisure for personalized memory |
| **Rollback** | Feature flag to temporary B-behavior in non-prod only |
| **Prod release** | Yes, once implemented + tests green |

### Option D — Isolate legacy route; deny recovery/account mutations

| | |
|---|---|
| **Change** | Keep bilinc for ask text-only; deny memory/profile R/W and any recovery touch |
| **Security** | Partial — stops writes if enforced; reads may remain if not careful |
| **Compatibility** | Breaks personalized memory on legacy ask |
| **Migration** | Medium |
| **Rollback** | Re-enable writes behind C |
| **Alone** | **Insufficient** — L-06.3/4 still leak reads; matrix/insights/memory-state remain |

---

## 6. Recommended Decision

### 6.1 Choice

**Primary: Option C**  
**Deployment control: Option B** (`LEGACY_X_USER_ID_AUTH`, production default **OFF**)  
**Scope: L-06.1–L-06.8** (L-06.9 admin target header remains admin-secret-gated; separate hardening note)

### 6.2 Normative rules (for future implementation — not coded now)

1. Production-shaped profile: `LEGACY_X_USER_ID_AUTH=0`.  
2. When flag is 0: `X-User-Id` **must not** authorize any read/write of
   `user_memory`, `user_profiles`, memory-state, insights, or matrix user row.  
3. Personalized bilinc/memory/matrix requires canonical authenticated principal
   (Supabase JWT / approved server session) — same family as V1.  
4. Anonymous `/ask` may run only as `user_id=0` with **no** load/save of another
   user’s memory/profile.  
5. If header is sent with a valid JWT: ignore header for authz; optional audit
   if header mismatches JWT subject mapping.  
6. Recovery contracts unchanged; no bilinc→recovery coupling introduced.  
7. L-06.9: document that `X-User-Id` is subject id under admin secret; require
   admin audit log (ops), not self-auth.

### 6.3 Impacts

| Dimension | Impact |
|---|---|
| **Security** | Closes cross-user memory/profile spoof; satisfies “no client-controlled identity authority” for this family |
| **Compatibility** | Header may still be sent; personalized features need Authorization. Mobile workspace currently has no `X-User-Id` sends — lower breakage risk for current app tree |
| **Migration** | Parallel to Stream C allowed; **must complete before OPERATIONAL** |
| **Rollback** | Non-prod flag ON for emergency client testing only; prod ON = NO-GO |
| **Production release** | **Cannot** proceed (release gate / OPERATIONAL) until L-06.1–L-06.8 contained + tests green |
| **Stream C start** | **May** proceed after entry gate ACCEPT that includes this decision |

### 6.4 Required tests (future — naming locked)

| Test ID | Assert |
|---|---|
| `L06-T01` | `GET /bilinc-alani/memory` without JWT → 401 (flag OFF) |
| `L06-T02` | `GET /bilinc-alani/profile` without JWT → 401 |
| `L06-T03` | `POST /bilinc-alani/ask` with spoofed `X-User-Id` and no JWT does not read/write that user’s memory |
| `L06-T04` | With JWT for U1 + `X-User-Id: U2`, memory ops affect **U1 only** |
| `L06-T05` | `/memory-state` rejects header-only auth when flag OFF |
| `L06-T06` | `/insights` rejects header-only auth when flag OFF |
| `L06-T07` | `matrix_rol/yorum` rejects header-only auth when flag OFF |
| `L06-T08` | Recovery `submit_evidence` still independent (no header influence) |
| `L06-T09` | Flag ON only in non-prod profile tests; prod config matrix forbids ON |

### 6.5 Required audit events (future)

| Event | When |
|---|---|
| `legacy_x_user_id_rejected` | Header presented but ignored/rejected under flag OFF |
| `legacy_x_user_id_mismatch` | Header present and disagrees with JWT principal |
| `legacy_x_user_id_flag_changed` | Ops config change (who/when/old/new) |

---

## 7. Compatibility and Migration Plan

| Phase | Action | Gate impact |
|---|---|---|
| P0 | Authorities accept this decision (docs only) | Makes entry pack **signable** |
| P1 | Implement Option C+B for L-06.1–L-06.8 (separate from Stream C VLIS or parallel track) | Not Stream C VLIS code |
| P2 | Tests `L06-T01`…`T09` green | Required before OPERATIONAL |
| P3 | Confirm mobile/web send Authorization for personalized paths | Product |
| P4 | Keep `LEGACY_X_USER_ID_AUTH=0` in production | Release prerequisite |

**Rollback path:** Revert P1 deploy; do **not** enable flag in production as
substitute for fix.

---

## 8. Authority Decision Matrix Update (L-06)

| Field | Value |
|---|---|
| **L-06 resolution prerequisite** | Authorities accept **Option C + B** (or record a written alternate) in this document’s approval section |
| **Blocks Stream C coding?** | **No**, once entry gate ACCEPT includes this prerequisite |
| **Blocks OPERATIONAL / BLK-001 RESOLVED?** | **Yes**, until L-06.1–L-06.8 implemented + `L06-T*` green |
| **Evidence each authority must review** | This file §§2–6; bilinc_alani.py; memory_state.py; insights.py; matrix_rol.py `/yorum`; recovery.py (negative: no header) |

### ACCEPT vs REJECT guidance

| Authority | ACCEPT if… | REJECT if… |
|---|---|---|
| **Identity** | Agrees JWT/canonical sole authz; header never maps users | Wants header to remain production auth; or Option A hard-cut without migration |
| **Security** | Agrees exploitability (no READY bypass, yes cross-user data); accepts C+B; prod flag OFF | Believes residual header auth in prod is acceptable; or wants Stream C blocked until L-06 code lands |
| **Recovery Owner** | Confirms no recovery contract change; L-06 parallel track OK | Requires bilinc changes inside recovery service / contract edits |
| **Operations** | Accepts flag matrix + audit events + no prod flag ON | Cannot operate health gate for `LEGACY_X_USER_ID_AUTH` |

---

## 9. Authority Review Briefs

### 9.1 Identity Authority

**Ask:** Accept L-06 resolution **Option C + B** as the identity model for
legacy ask/memory/matrix/insights paths.

**You must verify**

1. Inventory §2 covers all known `X-User-Id` self-auth paths.  
2. Recommendation does not grant header any authz role in production.  
3. Anonymous ask cannot become another user via header.  
4. Admin grant (L-06.9) correctly classified as subject selector.

**ACCEPT means:** Identity boundary for L-06 family is frozen as JWT-only
authority; implementation may proceed on the L-06 track.  
**REJECT means:** Propose alternate option (A/B/C/D) in writing.

**Signature:** ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN — Name ____ Date ____  
*(Do not pre-fill)*

---

### 9.2 Security Authority

**Ask:** Accept exploitability assessment and containment choice; confirm
Stream C may start without waiting for L-06 code, but OPERATIONAL cannot.

**You must verify**

1. No path from `X-User-Id` to READY/link.  
2. Cross-user memory/profile risk is acknowledged as High.  
3. Option C+B + tests `L06-T01`…`T09` are sufficient containment targets.  
4. Prod `LEGACY_X_USER_ID_AUTH=ON` remains a NO-GO.

**ACCEPT means:** Security accepts residual until P2; no false closure of
BLK-001.  
**REJECT means:** Require L-06 code before Stream C, or different option.

**Signature:** ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN — Name ____ Date ____  

---

### 9.3 Recovery System Owner

**Ask:** Confirm recovery freeze untouched; L-06 work stays outside A.3
contracts; entry gate may be signed with L-06 as parallel prerequisite to
OPERATIONAL.

**You must verify**

1. `/v1/recovery/*` does not read `X-User-Id`.  
2. Demotion/flag/MTC decisions in entry pack unchanged by L-06.  
3. No request to weaken four-eyes/audit to “make up for” bilinc risk.

**ACCEPT means:** Recovery owner OK with parallel L-06 track.  
**REJECT means:** Sequencing objection (e.g. L-06 before any Stream C PR).

**Signature:** ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN — Name ____ Date ____  

---

### 9.4 Operations Owner

**Ask:** Accept flag `LEGACY_X_USER_ID_AUTH` (prod default OFF), audit events,
and health/release checklist items.

**You must verify**

1. Prod profile cannot ship with flag ON.  
2. Break-glass does not include “turn header auth on in prod.”  
3. Rollback path is revert deploy, not prod flag ON.

**ACCEPT means:** Ops can enforce flag/health.  
**REJECT means:** Ops cannot support the control plane as specified.

**Signature:** ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN — Name ____ Date ____  

---

## 10. Updated Entry-Gate Status

| Item | Status |
|---|---|
| Stream C Entry Gate | **`ENTRY_GATE_PENDING`** (unchanged) |
| L-06 Resolution Decision | **`DECISION_DRAFT`** — this document |
| Authority ACCEPT marks in this repo | **None** (no false approvals) |
| BLK-001 | **OPEN** |
| Stream C implementation | **Must not start** until entry gate `ENTRY_GATE_ACCEPTED` |
| L-06 implementation | Separate track; **required before OPERATIONAL** |

**Signability:** The entry gate pack is **signable** once reviewers use this
L-06 decision as the resolved prerequisite for §7 B2-L / L-06 (plan accepted).
Signing the entry gate still requires the four blocks in the entry pack; this
file adds four L-06-specific briefs that may be signed together with or
immediately before those blocks.

---

## 11. Explicit Non-Claims

| Claim | Status |
|---|---|
| Stream C coded | **No** |
| L-06 contained in production | **No** |
| Any authority ACCEPT recorded | **No** |
| Entry gate ACCEPTED | **No** (`PENDING`) |
| BLK-001 RESOLVED | **No** |
| Recovery contracts changed | **No** |

---

## 12. Document control

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-19 | L-06 inventory, options, recommended C+B, authority briefs |

**Next:** Named authorities review and sign §9 (and entry pack §15). No
implementation until entry gate ACCEPT; L-06 code track per §7 plan.
