# PMP-01A-BLK-001 — Migration Bridge Design

**Document type:** Technical design / decision (governance only)  
**Blocker ID:** `PMP-01A-BLK-001`  
**Package ID:** `PMP-01A-BLK-001-MIG-BRIDGE-001`  
**Status:** `DESIGN_DRAFT` — awaiting authority ACCEPT (unsigned)  
**Governance freeze:** `55fc4aa` / tag `pmp01a39-governance-freeze`  
**Date:** 2026-07-19  

```text
NO CODE · NO MIGRATION · NO STREAM C · NO AUTO-LINK
Does not change L-06 Option C+B · Does not reopen X-User-Id as authz
ENTRY_GATE remains PENDING · BLK-001 remains OPEN · Release Gate CLOSED
```

**Frozen references**

| Artifact | Binding constraint preserved |
|---|---|
| L-06 resolution | **Option C + B** — JWT sole authz; `LEGACY_X_USER_ID_AUTH` prod **OFF** |
| Entry Gate §7 L-06 | Containment before OPERATIONAL; parallel to Stream C allowed |
| ADR-011 / ADR-013 | Canonical Supabase identity; fail-closed legacy compatibility |
| Auto-Link | **DISABLED** until BLK-001 RESOLVED + separate approval |
| Recovery A.3 contracts | Unchanged |

**Related:**  
`PMP-01A-BLK-001-l06-resolution-decision.md` ·  
`PMP-01A-BLK-001-council-vlis-evidence-trust-decision.md` ·  
`docs/pmp-01-secure-migration-execution-plan.md`

---

## 1. Problem statement

Council Review asked:

> How do legacy clients move to the JWT-based system safely when `X-User-Id`
> must not be an authorization source? What is the bridge process, what closes
> it, and what are the risks?

**Migration Bridge** is the **compatibility + cutover program** that lets older
clients continue *non-privileged* operation while identity authority moves
entirely to canonical JWT — without minting verified legacy↔canonical links
outside manual recovery.

This is **not** PMP-01B Migration Engine. It does **not** write production
identity maps. It does **not** enable automatic linking.

---

## 2. Goals and non-goals

### 2.1 Goals

1. Define a safe path from header/legacy-token clients → Supabase JWT clients.  
2. Keep personalized data-plane access behind verified JWT only.  
3. Preserve anonymous / degraded UX where product requires it (`user_id=0`,
   no cross-user memory).  
4. Align with L-06 Option C+B without inventing a second trust model.  
5. State exit criteria that must pass before OPERATIONAL / release-gate
   reconsideration.

### 2.2 Non-goals

| Non-goal | Why |
|---|---|
| Batch SQL identity linking | Auto-Link DISABLED; BLK-001 |
| Re-enable legacy HS256 as ambient auth | Contained fail-closed (L-07) |
| Use `X-User-Id` as authz “during transition” in production | Violates Option C+B |
| VLIS / recovery contract changes | Stream A/B freeze |
| Stream C implementation | Entry Gate PENDING |
| Opening `V1_CHAT_PERCENTAGE` as identity substitute | Product ≠ trust |

---

## 3. Trust boundary (target)

```text
┌─────────────────────────────────────────────────────────────┐
│ UNTRUSTED CLIENT                                            │
│  Authorization: Bearer <Supabase access_token>  → TRUSTED   │
│  X-User-Id / client user_id / device_fp         → HINT ONLY │
│  (ignored for authz when LEGACY_X_USER_ID_AUTH=0)           │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ CANONICAL AUTHORITY                                         │
│  Verify JWT → principal = auth.users.id (UUID)              │
│  Optional: server map UUID → legacy integer AFTER VLIS link │
│  (map used for data read, never for authentication)         │
└────────────────────────────┬────────────────────────────────┘
                             │
          ┌──────────────────┴──────────────────┐
          ▼                                     ▼
┌──────────────────────┐            ┌──────────────────────────┐
│ Product data plane   │            │ Recovery zone (A.3)      │
│ memory / profile /   │            │ Reviewer JWT only        │
│ bilinc / matrix      │            │ VLIS → four-eyes → link  │
│ JWT required for     │            │ No X-User-Id ever        │
│ personalized R/W     │            │                          │
└──────────────────────┘            └──────────────────────────┘
```

**Key rule:** Compatibility may accept a header as a **telemetry hint** or
**mismatch detector**; it must never select the authorized principal in
production-shaped profiles.

---

## 4. Compatibility modes

| Mode | Flag / profile | Principal source | Header role | Allowed in prod? |
|---|---|---|---|---|
| **M0 — Anonymous degraded** | Always | `user_id=0` / no account memory | Ignored | Yes (no cross-user R/W) |
| **M1 — JWT authoritative** | `LEGACY_X_USER_ID_AUTH=0` (prod default) | Supabase JWT `sub` | Ignored; optional mismatch audit | **Yes — target** |
| **M2 — Legacy header lab** | `LEGACY_X_USER_ID_AUTH=1` | Header (unsafe) | Authoritative | **No** in production |
| **M3 — Linked data resolve** | Post-VLIS link only | JWT principal; server loads linked legacy row | Ignored | Yes, after link exists |

Bridge work moves traffic **M2 → M1**, with **M0** as fallback for unauthenticated
ask, and **M3** only after manual recovery creates a verified link.

---

## 5. Bridge phases

Aligned with L-06 P0–P4; expanded for Council completeness.

| Phase | Name | Actions (design only now) | Gate impact |
|---|---|---|---|
| **B0** | Authority freeze | Accept this design + L-06 C+B + VLIS trust addendum | Makes Entry Gate signable; no code |
| **B1** | Client Authorization readiness | Mobile/web send Supabase Bearer on personalized routes; stop treating header as login | Product track |
| **B2** | Server Option C+B | Implement L-06.1–L-06.8 rules; tests `L06-T01`…`T09` | Required before OPERATIONAL |
| **B3** | Observability | Metrics: header-only attempts, JWT success, mismatch rate, 401 rate | Ops |
| **B4** | Cohort cutover | Percentage or build-number gates for JWT-required personalized paths; anonymous remains M0 | Product + Ops |
| **B5** | Header deprecation window | Continue ignore-header; document removal timeline for residual clients | Compatibility |
| **B6** | Bridge close | See §7 exit criteria | Prerequisite to claim “no client-controlled identity authority” |
| **B7** | Identity association (separate) | Manual recovery + VLIS only; Auto-Link stays DISABLED | BLK-001 resolution path — **not** this bridge |

**Sequencing vs Stream C:** B2 may run **in parallel** with Stream C after
`ENTRY_GATE_ACCEPTED`. B6+B7 completion is required before OPERATIONAL /
BLK-001 RESOLVED. Bridge close (B6) does **not** require every user linked
(B7); it requires no header authz.

---

## 6. How compatibility works without `X-User-Id` authority

### 6.1 Authenticated personalized request

```text
1. Client presents Authorization: Bearer <access_token>
2. Server verifies JWT (signature, exp, audience/project rules)
3. principal = JWT sub (UUID)
4. If X-User-Id present and maps to a different legacy id than any
   server-known binding for principal → audit legacy_x_user_id_mismatch;
   still authorize as principal only
5. Data access uses principal (+ optional post-link legacy row lookup)
```

### 6.2 Unauthenticated / anonymous ask

```text
1. No valid JWT
2. Allow only degraded ask (M0): no load/save of another user’s memory/profile
3. X-User-Id must not elevate to that user’s data plane
```

### 6.3 Residual old clients that only send `X-User-Id`

| Behavior under M1 (prod) | Result |
|---|---|
| Personalized memory/profile/matrix | **401 / fail-closed** |
| Anonymous ask (if product allows) | M0 only |
| Recovery APIs | Unaffected (never used header) |

**Compatibility message (product):** “Sign in required for saved memory.”  
**Not allowed:** silently serving another user’s memory via header.

### 6.4 Legacy integer → UUID relationship

| Mechanism | When allowed | Authz role |
|---|---|---|
| Verified recovery link (VLIS + four-eyes) | After BLK-001 path OPERATIONAL | **None** — mapping is authorization *input after* JWT, not a login method |
| Email/device heuristic | Never for authz or auto-link | Forbidden |
| Client-supplied integer | Never | Forbidden |

Until a verified link exists, a JWT user simply has **no** legacy row binding.
Product features that need legacy history must wait for recovery — not invent
bridge linking.

---

## 7. Bridge closure criteria

The Migration Bridge may be marked **CLOSED** only when **all** are true:

| # | Criterion | Evidence |
|---|---|---|
| C1 | Production `LEGACY_X_USER_ID_AUTH=0` | Config snapshot + health gate |
| C2 | `L06-T01`…`T09` green on production-shaped staging | CI / test report |
| C3 | L-02…L-05 legacy containment regressions green | Existing suite |
| C4 | Personalized routes require JWT; header-only → 401 | Staging drill + prod canaries |
| C5 | Header-only personalized error rate accepted by Ops (no SEV from cutover) | B3 metrics window (recommend ≥7 days or N builds) |
| C6 | No production path treats `X-User-Id` / client `user_id` as authz | Route inventory sign-off |
| C7 | Recovery still JWT-only; Auto-Link DISABLED | Negative tests + flag audit |
| C8 | Mobile/web release notes document sign-in for memory | Product artifact |

**CLOSED ≠ BLK-001 RESOLVED.**  
Bridge CLOSED means data-plane client authority is gone.  
BLK-001 RESOLVED additionally requires VLIS OPERATIONAL + Council (Stream D).

---

## 8. Risks and mitigations

| ID | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Residual clients lose personalized memory abruptly | Med | B4 staged cutover; clear UX; M0 ask retained |
| R2 | Ops enables `LEGACY_X_USER_ID_AUTH` in prod under pressure | **High** | Health NO-GO if ON; Entry Gate / Ops brief; change audit |
| R3 | “Temporary” header trust for VIP users | **High** | Forbidden; use recovery / support under dual-control, not header |
| R4 | Bridge confused with auto-link → silent SQL maps | **Critical** | Standing order; no batch link; Auto-Link DISABLED |
| R5 | JWT stolen session continues access | Med | Short access TTL; refresh rotation; revoke sessions on SEV-1 |
| R6 | Mismatch header ignored → attackers probe IDs | Low | Rate-limit; audit `legacy_x_user_id_rejected`; no oracle on existence if avoidable |
| R7 | Poisoned legacy memory from pre-containment spoof | High (historical) | VLIS must not treat raw memory export as Medium/High without server attestation; reviewers warned (L-06 exploitability) |
| R8 | Parallel Stream C + B2 races attention | Med | Separate tracks; OPERATIONAL blocked until both complete |
| R9 | Web/PMP-01A.2 not verifiable clients | Med | Treat as residual; same M1 rules; do not special-case weak clients |

---

## 9. Rollback

| Situation | Action | Forbidden |
|---|---|---|
| B2 deploy bug | Redeploy previous app image | Turning prod header auth ON as “fix” |
| Client not ready | Keep M0; delay B4 percentage | Re-authorizing header in prod |
| Suspected cross-user access | SEV-1: freeze personalized legacy routes; preserve audit | Auto-link to “repair” accounts |

---

## 10. Decision record (unsigned)

| # | Decision | Proposed freeze value |
|---|---|---|
| MB-1 | Production authz principal | Canonical JWT only (Option C) |
| MB-2 | Production header auth | Forbidden (Option B flag OFF) |
| MB-3 | Bridge vs Auto-Link | Bridge never creates verified links |
| MB-4 | Legacy data after link | Server-side resolve only (M3); JWT still required |
| MB-5 | Stream C sequencing | Parallel after Entry Gate ACCEPT; OPERATIONAL waits for B6 + VLIS |
| MB-6 | Closure | §7 C1–C8 |

### Authority signatures (do not pre-fill)

| Authority | Decision | Name | Date |
|---|---|---|---|
| Identity Authority | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN | | |
| Security Authority | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN | | |
| Recovery System Owner | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN | | |
| Operations Owner | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN | | |

---

## 11. Explicit non-claims

| Claim | Status |
|---|---|
| L-06 code shipped | **No** |
| Bridge CLOSED | **No** |
| Users migrated / linked | **No** |
| Auto-Link enabled | **No** |
| PMP-01B started | **No** |
| ENTRY_GATE_ACCEPTED | **No** (`PENDING`) |

---

## 12. Document control

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-19 | Initial Migration Bridge design — `DESIGN_DRAFT` |
