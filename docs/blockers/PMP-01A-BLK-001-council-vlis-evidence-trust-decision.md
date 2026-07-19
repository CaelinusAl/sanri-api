# PMP-01A-BLK-001 — Council Decision: Verified Legacy Identity Evidence & Trust

**Document type:** Council decision addendum (design / governance only)  
**Blocker ID:** `PMP-01A-BLK-001`  
**Package ID:** `PMP-01A-BLK-001-VLIS-TRUST-001`  
**Status:** `DECISION_DRAFT` — awaiting Council / authority ACCEPT (unsigned)  
**Governance freeze:** `55fc4aa` / tag `pmp01a39-governance-freeze`  
**Date:** 2026-07-19  

```text
NO CODE · NO MIGRATION · NO STREAM C · NO TRUST-MODEL REWRITE
Does not reopen MTC-M1L2 · Does not enable Auto-Link · Does not open Release Gate
ENTRY_GATE remains PENDING · BLK-001 remains OPEN
Supersedes nothing in Stream A/B/B2/Entry Pack — clarifies Council-facing choices
```

**Frozen references (must not be altered by this document)**

| Artifact | Binding constraint preserved |
|---|---|
| Stream A VLIS design | Source catalog S1–S10; trust High/Medium/Low; VLIS-BCMP |
| Entry Gate pack §5 | **v1 MTC rules = `MTC-H1` \| `MTC-M2` only**; **MTC-M1L2 FORBIDDEN** |
| Entry Gate pack I1–I12 | Unchanged |
| Auto-Link | **DISABLED** |
| Release Gate | **CLOSED** |

**Parent design:** `docs/blockers/PMP-01A-BLK-001-verified-legacy-identity-source-design.md`

---

## 1. Purpose

Council Review asked a concrete question Stream A answers in catalog form but
not as a **signable decision table**:

> Which evidence combinations verify a legacy user’s identity, and at what
> trust level?

This document freezes the **Council-facing answer** for v1 without changing
frozen MTC policy.

---

## 2. Normative trust levels (unchanged)

| Level | Meaning | Alone may satisfy MTC? |
|---|---|---|
| **High** | Strong binding to the person who owned the legacy account | Yes → `MTC-H1` |
| **Medium** | Strong binding to a channel/capability historically on that legacy account | No alone → need `MTC-M2` |
| **Low** | Corroborative only | Never alone; **not usable for v1 READY** under Entry Gate (M1L2 forbidden) |

**Hard rules (reaffirm Entry Gate + Stream A):**

1. Claimant uploads never self-assign trust level.  
2. ≥1 contributing item must be a **server attestation**.  
3. Supabase JWT proves *current* canonical session only — **not** a Medium legacy source.  
4. Client headers (`X-User-Id`, `user_id`, `device_fp`) are **never** evidence sources.  
5. Conflicting High/Medium attestations → fail-closed (`evidence_conflict`).  
6. Binding check to `claimed_legacy_identity_ref` is mandatory before MTC.

---

## 3. Source → trust level (Council quick table)

| ID | Source | Trust | Counts in v1 MTC? | Notes |
|---|---|---|---|---|
| S1 | Government ID / approved KYC | **High** | Yes (H1) | Needs documented name/id bind to legacy record |
| S2 | Verified email (server challenge vs legacy email) | **Medium** | Yes (M2 slot) | Client-declared email = forbidden |
| S3 | Verified phone (server challenge vs legacy phone) | **Medium** | Yes (M2 slot) | Screenshot OTP = Low only (not v1 READY path) |
| S4a | Current Supabase JWT session | — | **No** (prerequisite only) | Not legacy ownership |
| S4b | One-time server migration challenge (hashed capability) | **Medium** | Yes (M2 slot) | Must not re-enable ambient legacy HS256 auth |
| S4c / S6 | Hardware key enrolled on legacy account | **High** | Yes (H1) | Rare for cohort |
| S5 | Historical login / session telemetry | **Low** | **No** in v1 READY | Corroboration for reviewers only |
| S7 | Payment history (billing SoR attestation) | **Medium** | Yes (M2 slot) | PDF/screenshot alone = Low |
| S8 | Support ticket sealed prior outcome | **Medium** only if sealed server-retrievable; else **Low** | Medium → M2; Low → no | Circular “I know them” forbidden |
| S9 | Social proof | **Low** | **No** in v1 READY | Never inflate to Medium |
| S10 | Org IdP/HR connector | **High** (connector) / **Medium** (manual letter) | Yes | Enterprise accounts only |

---

## 4. Recommended evidence combinations (v1)

Only combinations that satisfy **`MTC-H1` or `MTC-M2`** are recommended for
production READY. Each row assumes binding check pass + ≥1 server attestation.

### 4.1 `MTC-H1` — single High (preferred when available)

| Combo ID | Composition | Confidence | Cohort fit | Residual risk |
|---|---|---|---|---|
| **H1-A** | S1 KYC + bind to legacy legal/profile fields | **Highest** | Users with legal name on file | KYC vendor compromise; deepfake remote KYC |
| **H1-B** | S6 / S4c hardware key previously enrolled | **Highest** | Enrolled subset only | Stolen authenticator |
| **H1-C** | S10 High org IdP attestation mapped 1:1 to legacy enterprise account | **High** | Enterprise cohort | Stale roster; shared seats |

**Council recommendation:** Prefer **H1-A** as default High path when operationally available. H1-B/C are equivalent for MTC when attestations exist.

### 4.2 `MTC-M2` — two distinct Medium categories (primary mass path)

Distinct **categories** = distinct `source_id` families (e.g. S2 and S7), not
two challenges of the same source.

| Combo ID | Composition | Confidence | When to use | Residual risk |
|---|---|---|---|---|
| **M2-A** | S2 email + S7 payment | **High** | Paying users with email on legacy record | Mailbox takeover + shared family card |
| **M2-B** | S3 phone + S7 payment | **High** | Phone-on-file paying users | SIM swap + shared card |
| **M2-C** | S2 email + S4b migration challenge | **High** | Non-paying / no billing match | Mailbox takeover + stolen challenge |
| **M2-D** | S3 phone + S4b migration challenge | **High** | Same, phone-primary | SIM swap + stolen challenge |
| **M2-E** | S2 email + S3 phone | **Medium-High** | Both channels on legacy record | Dual-channel account takeover |
| **M2-F** | S7 payment + S4b migration challenge | **High** | Email/phone recycled or unavailable | Billing social-eng + stolen challenge |
| **M2-G** | S8 Medium sealed support + S2/S3/S7/S4b | **Medium** | Prior sealed identity case exists | Prior process weakness inherited |

**Council recommendation (default mass path):** **M2-A** (email + payment).  
Fallbacks in order: **M2-C** → **M2-B** → **M2-F** → **M2-E**.  
**M2-G** only when S8 truly Medium (sealed, server-retrievable).

### 4.3 Explicitly rejected for v1 READY

| Pattern | Why rejected |
|---|---|
| Any Low-only or Medium+Low (`MTC-M1L2`) | Entry Gate §5 **FORBIDDEN** |
| Email match without server challenge | Client/self assertion |
| Device fingerprint / IP / “same phone model” | Correlative; Low at best |
| JWT alone / header `X-User-Id` | Not legacy ownership; unsafe authority |
| Two email challenges counted as M2 | Same category — I5 / AC-08 |
| Screenshot gallery (OTP, bank, ID) without server SoR | Upload theater |
| Support narrative without sealed ticket attestation | S8 Low |

---

## 5. Confidence scoring (informational — does not replace MTC)

Reviewers may record a confidence label; **machines enforce MTC only**.

| Label | Meaning | Maps to |
|---|---|---|
| **C1** | Strong institutional / KYC / hardware | Typical H1-* |
| **C2** | Two independent Medium channels | Typical M2-A…F |
| **C3** | Borderline but MTC-pass (e.g. M2-G, M2-E under takeover suspicion) | Require reviewer notes; may REJECT despite MTC |
| **C0** | Below MTC or conflict | Stay `EVIDENCE_PENDING` / `REJECTED` |

Four-eyes may **REJECT** a C3 package even if MTC passes. They may **not**
APPROVE a package that fails MTC.

---

## 6. Binding & conflict rules (Council restatement)

Before READY:

1. `claimed_legacy_identity_ref` exists and is not already linked (else EC-11).  
2. No open duplicate case (EC-07).  
3. Every Medium/High identifier resolves to **that** legacy_ref.  
4. If email/phone/payment identifiers point to **different** legacy accounts →
   `evidence_conflict` fail-closed.  
5. Package `valid_until = min(contributing attestation expires_at)`.

---

## 7. Decision record (unsigned)

| # | Decision | Proposed freeze value |
|---|---|---|
| VT-1 | v1 READY compositions | Only §4.1 H1-* and §4.2 M2-* |
| VT-2 | Default mass path | **M2-A** (S2+S7) |
| VT-3 | Default High path | **H1-A** (S1) when available |
| VT-4 | Low sources in v1 READY | **Never** (M1L2 remains forbidden) |
| VT-5 | Client identity signals as evidence | **Never** |
| VT-6 | Confidence labels | Advisory only; cannot override MTC or four-eyes REJECT |

### Authority signatures (do not pre-fill)

| Authority | Decision | Name | Date | Notes |
|---|---|---|---|---|
| Identity Authority | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN | | | |
| Security Authority | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN | | | |
| Recovery System Owner | ☐ ACCEPT · ☐ REJECT · ☐ ABSTAIN | | | |
| Operations Owner | ☐ ACK (ops impact: attestation adapters) · ☐ ABSTAIN | | | |

**ACCEPT rule for this addendum:** Identity + Security both ACCEPT; Recovery
Owner ACCEPT or ACK no-contract-change; no REJECT.

This addendum **does not** by itself flip `ENTRY_GATE_ACCEPTED`. Entry Gate
§15 signatures remain the gate for Stream C start.

---

## 8. Explicit non-claims

| Claim | Status |
|---|---|
| Stream A design replaced | **No** |
| MTC-M1L2 reopened | **No** |
| Auto-Link enabled | **No** |
| BLK-001 RESOLVED | **No** |
| Implementation started | **No** |

---

## 9. Document control

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-19 | Council evidence/trust decision table — `DECISION_DRAFT` |
