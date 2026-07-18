# PMP-01A-BLK-001 — Verified Legacy Identity Source

**Document type:** Design only (no implementation)  
**Blocker ID:** `PMP-01A-BLK-001`  
**Title:** Verified Legacy Identity Source Missing  
**Status:** `DESIGN_DRAFT` — pending Identity + Security Authority approval  
**Program:** PMP-01A  
**Release decision context:** A.3.9 = **NO-GO**; REP-001 = **BLOCKED**  
**Engineering freeze tip:** `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab` / `pmp01a37-complete`  
**Related:** REP-001 · Operations Manual · A.3.1–A.3.9 contracts  
**Last updated:** 2026-07-18  

```text
Authority Level: Design — does not change production behavior
Owner: PMP-01 Program (Identity + Security Authority approval required)
Non-goals: production code, recovery/audit/assertion/link/case/reviewer edits
Frozen contracts preserved: fail-closed · four-eyes · append-only audit ·
  signed assertions · transaction guarantees · idempotency · replay protection
```

---

## 1. Executive Summary

Manual recovery engineering (A.3.1–A.3.7) is complete and evidence-ready.
Operations packaging (REP-001, Operations Manual) exists. Production remains
**NO-GO** because there is still no **server-side verified legacy identity
source** that can prove:

> “This authenticated Supabase principal is the rightful owner of that
> claimed legacy account.”

Without that proof, the recovery machinery can move cases through states, but
it cannot safely mint a `verified` / `linked` association. Automatic linking
stays **DISABLED**. Client-controlled signals (`user_id`, email match, device,
IP, fingerprint, unsigned tokens) remain **forbidden as authority**.

### Design decision (recommended)

Adopt **Bounded Composite Manual Proof (BCMP)** as the verified legacy
identity source:

1. Claimants present a **multi-source evidence package** bound to
   `claimed_legacy_identity_ref` and `subject_user_id` (Supabase UUID).
2. Each source has a published **trust level** (High / Medium / Low) and
   explicit prove / cannot-prove / attack-surface statements.
3. A **Minimum Trust Composition (MTC)** gate must pass **before** the case
   may enter `READY_FOR_REVIEW`.
4. Where a source can be checked by the server (billing row, challenge
   completion, org roster), the server emits a **server attestation** whose
   hash is included in `evidence_hash`. Reviewers never rely on client
   screenshots alone when a server check is available.
5. Only the frozen recovery path may create links:
   `reviewer JWT → signed assertions → four-eyes → link → durable audit`.
6. Automatic linking, legacy HS256 re-enablement, and ad-hoc SQL remain
   forbidden.

BCMP resolves Stream A of the blocker brief without weakening frozen security
contracts. Implementation (Streams B2–D) is **out of scope for this document**.
Architecture attachment to A.3 is specified in Stream B:
`docs/blockers/PMP-01A-BLK-001-stream-b-architecture-integration.md`.

| Question | Answer |
|---|---|
| Does this design open the release gate? | **No** |
| Does it enable automatic linking? | **No** |
| Does it modify frozen A.3 code? | **No** (design only) |
| Does it define how manual recovery becomes operational? | **Yes** |
| Who may mark BLK-001 `RESOLVED`? | Release Council after Streams B–D |

---

## 2. Threat Model

### 2.1 Assets

| Asset | Why it matters |
|---|---|
| Legacy user data (memories, history, premium state) | Cross-user association = account takeover of life history |
| Canonical V1 Supabase identity (`sub` UUID) | Sole production auth principal |
| Recovery case / assertion / link / audit ledgers | Integrity of every ownership decision |
| Reviewer principals and roles | Compromise enables false quorum |
| Evidence packages and attestations | Forged evidence → false approval |
| Signing keys for Recovery Service assertions | Forged assertions bypass human review |

### 2.2 Actors

| Actor | Capability |
|---|---|
| Honest legacy user | Lost access; wants rightful recovery |
| Impersonator | Tries to claim someone else’s legacy account |
| Compromised email/phone owner | Controls a channel but not the person |
| Malicious insider (single reviewer) | Tries to approve without second eye |
| Colluding reviewers | Two compromised reviewers |
| External attacker | Phishing, SIM swap, document forgery, replay |
| Compromised client app | Sends forged headers / “proof” payloads |
| Automated linking bug | Would silently map wrong users (must stay disabled) |

### 2.3 Threats and controls

| ID | Threat | Control in this design |
|---|---|---|
| T-01 | Client asserts `legacy_user_id` as truth | Client claims are **claims only**; never authority. Server + MTC + four-eyes required. |
| T-02 | Email/device/IP/fingerprint auto-match | Forbidden as sole or automatic proof. May appear only as Low support evidence under MTC. |
| T-03 | Legacy HS256 token re-enabled as trust | Explicitly forbidden (A.3 non-goal). Decoder remains fail-closed. |
| T-04 | Screenshot / social forgery | Low trust; never alone. Prefer server attestations. Reviewer checklist + dual approval. |
| T-05 | SIM swap / mailbox takeover | Verified phone/email = Medium max; require second distinct Medium/High or additional Low set per MTC. |
| T-06 | Single-reviewer approval | Four-eyes mandatory; same principal cannot be both eyes. |
| T-07 | Evidence swap after first approval | EC-09: evidence hash change invalidates quorum. |
| T-08 | Replay of approve / link operations | `operation_key` idempotency; signed assertions; no second link for same pair. |
| T-09 | Link without audit | Transaction boundary: audit write failure → full rollback (EC-05). |
| T-10 | Colluding reviewers | Policy + sampling audits; revoke model; separation of duties for case create vs second eye; Council review of revoke rates. |
| T-11 | Privacy leak of government ID | Encrypted evidence store; hash-only in case ledger; retention + redaction tombstones. |
| T-12 | Duplicate open cases / race | EC-07 unique open case; EC-01 compare-and-set on state. |
| T-13 | Revoked link reuse | Append-only revoke; link create fails closed on `revoked_link` / conflict. |

### 2.4 Trust boundary diagram

```text
┌─────────────────────────────────────────────────────────────┐
│ UNTRUSTED                                                     │
│  Mobile/Web client · Claimant uploads · Support tickets     │
│  Screenshots · Social posts · Client headers / device_fp    │
└───────────────────────────┬─────────────────────────────────┘
                            │ claims + raw evidence only
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ SERVER TRUST ZONE (VLIS + Recovery Service)                   │
│  · Issue / verify attestations for checkable sources          │
│  · Compute evidence_hash + MTC gate                           │
│  · Authenticate reviewers (JWT + role)                        │
│  · Sign assertions · Enforce four-eyes · Create/revoke links│
│  · Append-only audit (transactional)                          │
└───────────────────────────┬─────────────────────────────────┘
                            │ only after APPROVED + quorum
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ IDENTITY ASSOCIATION (durable)                                │
│  legacy_ref ↔ supabase_user_id  (single-active, revocable)  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Trust Model

### 3.1 Core axioms (immutable for this design)

1. **Canonical authority** is Supabase JWT `sub` (server-verified).  
2. **Legacy identity is never self-asserted as truth.**  
3. **Fail-closed:** ambiguous, incomplete, or conflicting evidence → no link.  
4. **Manual-recovery-only** for creating verified associations.  
5. **Automatic linking remains DISABLED** until a future, separately approved design (not this document).  
6. **Human reviewers decide under policy; machines enforce bounds.**  
7. **No ad-hoc DB path** may mint `verified` / `linked`.  

### 3.2 What “verified legacy identity source” means here

A **Verified Legacy Identity Source (VLIS)** is not a single database column.
It is the **composed, server-gated evidence + attestation system** that:

- binds proof materials to (`subject_user_id`, `claimed_legacy_identity_ref`),
- assigns trust levels per source,
- enforces Minimum Trust Composition,
- produces a stable `evidence_hash` for assertions,
- is consumable only by the frozen recovery workflow.

### 3.3 Roles

| Role | Trust function |
|---|---|
| Claimant | Provides claims and raw evidence; no authority |
| Attestation Issuer (server) | Verifies checkable sources; emits attestations |
| Primary Reviewer | First decision under MTC + checklist |
| Second Reviewer | Independent second decision (four-eyes) |
| Recovery Service | Signs assertions, enforces quorum, links, audit |
| System | Clock, expiry, append-only persistence |
| Release Council | Accepts BLK-001 resolution; opens gates later |

### 3.4 Authority separation (preserves A.3 matrix)

| Operation | Sole authority |
|---|---|
| Emit source attestation | Server Attestation Issuer |
| Case create / evidence accept | Reviewer API / Recovery Service |
| Assertion sign | Recovery Service only |
| Quorum / link create / revoke | Recovery Service |
| Audit write | System (same transaction as decision) |
| Mark BLK-001 RESOLVED | Release Council |

---

## 4. Identity Trust Matrix

Trust levels:

| Level | Meaning | May alone satisfy MTC? |
|---|---|---|
| **High** | Strong binding to legal or institutional identity of the person who owned the legacy account | Yes (1× High) |
| **Medium** | Strong binding to a channel or account capability historically associated with the legacy account | No alone — need composition |
| **Low** | Supportive / correlative; easily forged or transferred | Never alone |

### 4.1 Source catalog

#### S1 — Government identity (in-person or approved KYC vendor)

| Field | Definition |
|---|---|
| **Trust level** | **High** |
| **What it proves** | A natural person matching claimed legal identity presented acceptable government credential under controlled process |
| **What it cannot prove** | By itself that the person *used* that specific legacy account, unless name/identifiers are bound to legacy account records with documented match rules |
| **Attack surface** | Forged docs, deepfakes in remote KYC, vendor compromise, insider at KYC desk |
| **Required reviewer evidence** | Vendor/session attestation ID; match result to legacy profile fields; liveness/session status; no raw ID images in case notes |
| **Required audit evidence** | Attestation ID, vendor, policy_version, evidence_hash component, reviewer IDs, decision codes |
| **Operational note** | Prefer vendor hash + match code over storing full ID scans. Privacy §10 applies. |

#### S2 — Verified email (server challenge)

| Field | Definition |
|---|---|
| **Trust level** | **Medium** (only if challenge completed server-side against email historically stored on the legacy account) |
| **What it proves** | Control of an email address that the **server** confirms is recorded on the claimed legacy account |
| **What it cannot prove** | That the mailbox owner is the original human (shared inboxes, takeover) |
| **Attack surface** | Mailbox compromise, password reset chains, support email change fraud |
| **Required reviewer evidence** | Server attestation: `email_challenge_passed` + normalized email hash + legacy_ref binding + timestamp |
| **Required audit evidence** | Attestation ID, challenge_id, expiry, evidence_hash, no plaintext email in audit if policy requires hash-only |
| **Forbidden** | “Emails look the same” without server challenge; client-declared email |

#### S3 — Verified phone (server challenge)

| Field | Definition |
|---|---|
| **Trust level** | **Medium** (server OTP/challenge against phone on legacy record) |
| **What it proves** | Control of phone number bound on server to legacy account |
| **What it cannot prove** | Identity of the human (SIM swap, port-out) |
| **Attack surface** | SIM swap, SS7, recycled numbers |
| **Required reviewer evidence** | Server attestation `phone_challenge_passed` + phone hash + binding |
| **Required audit evidence** | Attestation ID, challenge_id, timestamps, evidence_hash |
| **Forbidden** | SMS screenshot as Medium; screenshots are Low support only |

#### S4 — Existing account ownership (canonical or legacy capability proof)

| Field | Definition |
|---|---|
| **Trust level** | **Medium** to **High** (see subtypes) |
| **Subtypes** | (a) **Medium:** prove control of *current* Supabase account (already true via JWT — necessary but not legacy ownership). (b) **Medium:** prove control of a still-reachable legacy secret that server can verify without re-enabling HS256 sessions as a general auth path — e.g. one-time migration challenge code previously issued and stored hashed. (c) **High:** hardware-backed recovery key previously enrolled server-side (see S6). |
| **What it proves** | Possession of a secret/capability the server associates with the account |
| **What it cannot prove** | Secret was not stolen |
| **Attack surface** | Credential stuffing, leaked recovery codes, malware |
| **Required reviewer evidence** | Server attestation of challenge success; never the raw secret |
| **Required audit evidence** | Challenge type, attestation ID, evidence_hash |
| **Forbidden** | Re-enabling legacy JWT decoder as ambient auth |

#### S5 — Historical login / session telemetry (server logs)

| Field | Definition |
|---|---|
| **Trust level** | **Low** (corroborative) |
| **What it proves** | Historical patterns consistent with claimant narrative (time zones, device classes, approximate geographies) |
| **What it cannot prove** | Ownership; attackers can study or mimic patterns |
| **Attack surface** | Log poisoning, over-fitting reviewer bias, privacy leakage |
| **Required reviewer evidence** | Redacted server-generated consistency report (pass/fail codes), not raw IP dumps in tickets |
| **Required audit evidence** | Report hash, generator version, evidence_hash |
| **Forbidden** | IP/device fingerprint as automatic link key |

#### S6 — Hardware key / enrolled authenticator

| Field | Definition |
|---|---|
| **Trust level** | **High** if previously enrolled to the legacy account on server; otherwise **N/A** |
| **What it proves** | Possession of authenticator bound to account |
| **What it cannot prove** | Key not shared/stolen |
| **Attack surface** | Lost key social-engineering, enrollment fraud at setup time |
| **Required reviewer evidence** | Server WebAuthn/assertion verification attestation |
| **Required audit evidence** | Credential ID (or hash), verification result, evidence_hash |
| **Note** | Likely rare for legacy SANRI cohort — include for completeness |

#### S7 — Payment history (billing system of record)

| Field | Definition |
|---|---|
| **Trust level** | **Medium** (server match of last4/expiry/processor customer ID or receipt token to legacy account) |
| **What it proves** | Claimant can prove knowledge/possession of payment artifacts that billing associates with legacy account |
| **What it cannot prove** | Shared family cards, stolen statements |
| **Attack surface** | Statement forgery (if not server-matched), support social engineering |
| **Required reviewer evidence** | Server attestation from billing lookup — not user-uploaded PDF alone |
| **Required audit evidence** | Billing attestation ID, match codes, evidence_hash (no full PAN) |
| **Forbidden** | Accepting only a screenshot of a bank app as Medium |

#### S8 — Support evidence (prior tickets, verified contact history)

| Field | Definition |
|---|---|
| **Trust level** | **Low** to **Medium** |
| **Medium only when** | Prior ticket already established identity under an older approved process **and** server can retrieve that ticket’s sealed outcome |
| **Otherwise** | **Low** (narrative support) |
| **What it proves** | Continuity of contact / prior sealed decision |
| **What it cannot prove** | Current ownership if prior process was weak |
| **Attack surface** | Ticket injection, compromised support tools, circular approval |
| **Required reviewer evidence** | Ticket IDs, sealed outcome codes, retrieval attestation |
| **Required audit evidence** | Ticket IDs, outcome codes, evidence_hash |
| **Forbidden** | Reviewer citing “I know this user” without artifacts |

#### S9 — Social proof

| Field | Definition |
|---|---|
| **Trust level** | **Low** |
| **What it proves** | Weak public association (handle continuity, old posts) |
| **What it cannot prove** | Account ownership in a security sense |
| **Attack surface** | Easy forgery, lookalike accounts |
| **Required reviewer evidence** | URLs + archival hashes; marked Low |
| **Required audit evidence** | Source URLs hash list, evidence_hash |
| **Forbidden** | Counting social proof as Medium/High under any policy version |

#### S10 — Organization records (employer / school / enterprise roster)

| Field | Definition |
|---|---|
| **Trust level** | **Medium** to **High** |
| **High when** | Authoritative org IdP / HR system attests employment + email that maps 1:1 to legacy enterprise account via server connector |
| **Medium when** | Manual letter / PDF from org without cryptographic/server connector |
| **What it proves** | Institutional association |
| **What it cannot prove** | Personal (non-enterprise) legacy accounts; shared seats |
| **Attack surface** | Forged letters, rogue HR contact, stale roster |
| **Required reviewer evidence** | Connector attestation or dual-verified org contact record |
| **Required audit evidence** | Org ID, attestation ID, evidence_hash |

### 4.2 Minimum Trust Composition (MTC) — policy v1 (proposed)

A case may move `EVIDENCE_PENDING → READY_FOR_REVIEW` only if **one** of:

| Rule ID | Composition |
|---|---|
| MTC-H1 | ≥ **1 High** source attestation/evidence item, **and** legacy_ref binding check passes |
| MTC-M2 | ≥ **2 Medium** sources from **distinct categories** (e.g. S2+S7, S3+S4b), **and** binding check |
| MTC-M1L2 | ≥ **1 Medium** + ≥ **2 Low** from distinct categories, **and** binding check |

Additional hard rules:

1. **S9 Social proof** never satisfies more than one Low slot.  
2. **S5 Historical login** never satisfies more than one Low slot.  
3. At least one item must be a **server attestation** (not purely claimant upload).  
4. Supabase JWT proof of *current* session is prerequisite for claimant actions but **does not count** as a Medium legacy source.  
5. Conflicting High/Medium attestations → fail-closed (`evidence_conflict`).  
6. Policy version `mtc_v1` is recorded on every assertion.

Future policy versions may tighten (never silently loosen) via governance; loosening requires Council.

---

## 5. Evidence Collection

### 5.1 Evidence package structure (logical)

```text
EvidencePackage
  case_id
  subject_user_id          # Supabase UUID (canonical)
  claimed_legacy_identity_ref
  policy_version           # e.g. mtc_v1
  items[]:
    source_id              # S1..S10
    trust_level            # High|Medium|Low
    kind                   # server_attestation | upload | retrieved_record
    attestation_id?        # required for server_attestation
    content_hash           # hash of normalized item payload
    collected_at
    collector              # system | reviewer_assist | claimant
  package_hash             # hash over canonical serialization of items[]
```

`evidence_hash` used by A.3 assertions **is** `package_hash` (or a keyed
derivative defined at implementation time — design requires stability and
EC-09 invalidation on change).

### 5.2 Collection principles

1. Prefer **server attestation** over uploads.  
2. Uploads are encrypted at rest; access is role-gated and audited.  
3. Reviewers see **decision-relevant fields** and redacted previews, not
   unnecessary PII.  
4. Claimant may not set `trust_level`; server/policy assigns it.  
5. Support staff may assist collection but **cannot** approve links.  
6. Every add/remove of an item recalculates `package_hash` and, if
   approvals exist, triggers EC-09 behavior.

### 5.3 Binding check (mandatory)

Before MTC evaluation, server verifies:

- `claimed_legacy_identity_ref` exists in legacy store (or sealed archive),
- account is not already linked (else EC-11 path),
- no non-terminal duplicate case (EC-07),
- each Medium/High item’s identifiers actually refer to **that** legacy_ref
  (not a different user).

Failure → remain `EVIDENCE_PENDING` or `REJECTED` with machine reason codes.

---

## 6. Verification Workflow

Integrates with frozen state machine; **does not alter** allowed transitions.

```text
Claimant authenticates (Supabase JWT)
        │
        ▼
Case DRAFT ──► EVIDENCE_PENDING
        │         │
        │         ├─ collect items / server challenges
        │         ├─ compute package_hash
        │         ├─ run binding check + MTC
        │         │
        │         ├─ FAIL ──► stay EVIDENCE_PENDING or REJECTED (fail-closed)
        │         │
        │         └─ PASS ──► READY_FOR_REVIEW
        │                       │
        │                       ▼
        │              Primary reviewer asserts APPROVE/REJECT
        │              (Recovery Service signs; evidence_reference_hash =
        │               package_hash; policy_version = mtc_v1)
        │                       │
        │                       ▼
        │              AWAITING_SECOND_APPROVAL
        │                       │
        │                       ▼
        │              Second distinct reviewer asserts
        │                       │
        │          ┌────────────┴────────────┐
        │          ▼                         ▼
        │      REJECTED                  APPROVED
        │                                   │
        │                                   ▼
        │                            LINK_CREATED
        │                         (transactional audit)
        │                                   │
        │                          REVOKED / CLOSED
```

### 6.1 Server attestation workflow (checkable sources)

```text
Reviewer or claimant starts challenge for source Sx
        │
        ▼
Attestation Issuer validates against system of record
        │
        ├── fail ──► no attestation (fail-closed for that source)
        │
        └── success
                │
                ▼
        store attestation (id, source, legacy_ref,
          subject_user_id, expires_at, signature/MAC)
                │
                ▼
        include attestation_id + content_hash in package
```

Attestations are short-lived (proposal: ≤ 7 days; tighter for phone/email OTP:
≤ 24 hours). Expired attestations drop out of MTC.

### 6.2 Replay / idempotency

- All mutations keep A.3 `operation_key` semantics.  
- Challenge completion is idempotent on `challenge_id`.  
- Replaying evidence submit with same package_hash is a no-op success.  
- Different package_hash with prior approvals → EC-09.

---

## 7. Reviewer Decision Tree

```text
Start: case in READY_FOR_REVIEW or AWAITING_SECOND_APPROVAL
│
├─ Is reviewer JWT + role valid?
│    NO → deny (fail-closed)
│
├─ Is this the same principal as the other eye?
│    YES → four_eyes_conflict (EC-04)
│
├─ Is package_hash present and MTC still satisfied with non-expired items?
│    NO → return to EVIDENCE_PENDING / reject attempt
│
├─ Binding check still green? (not linked elsewhere, legacy_ref stable)
│    NO → REJECT or fail-closed conflict
│
├─ Any High/Medium conflict flags?
│    YES → REJECT (evidence_conflict) or request new evidence
│
├─ Checklist (all must be YES for APPROVE):
│    □ Claimed legacy_ref matches attestations
│    □ At least one server attestation unexpired
│    □ MTC rule ID recorded (H1 / M2 / M1L2)
│    □ No signs of SIM-swap / inbox takeover without compensating High
│    □ Rationale code selected (machine-readable)
│    □ No pressure to skip four-eyes
│
├─ Decision = REJECT? → sign reject assertion → terminal REJECTED
│
└─ Decision = APPROVE?
     ├─ First eye → AWAITING_SECOND_APPROVAL
     └─ Second eye + valid first → APPROVED → (link job) LINK_CREATED
```

### 7.1 Reviewer responsibilities

| Duty | Detail |
|---|---|
| Independence | No dual-role on same case |
| Evidence fidelity | Approve only against current `package_hash` |
| Least privilege | No production SQL; no manual `verified` flags |
| Rationale quality | Use codes; free text minimized and non-authoritative |
| Escalation | Suspected fraud → REJECT + security incident path |
| Privacy | Do not export ID images to personal channels |
| Second eye duty | Re-validate MTC; do not rubber-stamp |

### 7.2 What reviewers must never do

- Treat client headers as proof  
- Approve on social proof alone  
- Share raw secrets / OTPs in rationale  
- Ask engineering to “just link it in the DB”  
- Reopen terminal cases (appeals = new case)

---

## 8. Evidence Requirements (normative checklist)

### 8.1 Per-case minimum (before READY_FOR_REVIEW)

| Requirement | Mandatory |
|---|---|
| Authenticated `subject_user_id` | Yes |
| Existing `claimed_legacy_identity_ref` | Yes |
| Binding check pass | Yes |
| MTC satisfied under `mtc_v1` | Yes |
| ≥ 1 server attestation | Yes |
| `package_hash` computed | Yes |
| No open duplicate case | Yes |
| Not already linked / not revoked-conflict | Yes |

### 8.2 Per-approval assertion (already frozen; VLIS bindings)

| Field | VLIS expectation |
|---|---|
| `evidence_reference_hash` | Equals current `package_hash` |
| `policy_version` | Includes MTC version (`mtc_v1`) |
| `asserted_legacy_user_id` / ref | Must match case claim |
| `asserted_supabase_user_id` | Must match case subject |
| `signature` | Recovery Service only |
| `operation_key` | Idempotent |

### 8.3 Per-link audit (frozen + VLIS tags)

Audit event must allow reconstruction of:

- who approved (two reviewer IDs),
- which MTC rule fired,
- which attestation IDs were in force,
- `package_hash`,
- link id / revoke state,
- policy versions.

---

## 9. Failure Modes

| Mode | Detection | System behavior |
|---|---|---|
| MTC not met | Gate | Stay `EVIDENCE_PENDING` |
| Attestation expired | Gate / review | Drop from MTC; may demote case |
| Evidence changed after approve | Hash mismatch | EC-09 → re-review |
| Four-eyes conflict | Same reviewer | EC-04 reject attempt |
| Audit write fail | TX error | EC-05 rollback |
| Identity conflict | Link table | EC-11 fail-closed |
| Duplicate open case | Constraint | EC-07 reject |
| Suspected fraud mid-review | Reviewer / signals | REJECT + incident |
| Reviewer key/account compromise | Security | Revoke reviewer role; reopen risk assessment; revoke tainted links |
| Billing/IdP outage | Dependency | Fail-closed on that source; do not skip MTC |
| Partial upload corruption | Hash verify | Reject item |

All uncertain states **fail closed** (no link).

---

## 10. Privacy Model

### 10.1 Principles

1. **Data minimization:** collect only fields needed for MTC.  
2. **Hash-first audit:** ledgers store hashes and codes; raw PII in gated store.  
3. **Separation:** evidence blob store ≠ case ledger ≠ audit ledger.  
4. **Retention:** raw government ID / KYC media retained only as short as legal
   and fraud-review require; then cryptographic tombstone in audit.  
5. **Reviewer access:** just-in-time, audited, dual-control for High media.  
6. **Claimant rights:** export/delete requests must not break append-only audit
   integrity (tombstones allowed; history deletion forbidden).  
7. **No training use:** recovery evidence is not ML training data.

### 10.2 Classification

| Data | Class | Storage |
|---|---|---|
| Government ID images | Restricted | Encrypted blob; short TTL |
| Email/phone plaintext | Sensitive | Prefer hash + attestation |
| Payment PAN | Prohibited in VLIS | Use processor tokens / last4 via billing only |
| Social URLs | Internal | Hash + URL list |
| Reviewer rationale codes | Internal | Audit ledger |
| package_hash / attestation IDs | Internal | Case + assertion + audit |

---

## 11. Revocation Model

### 11.1 Objects that can be revoked

| Object | Effect |
|---|---|
| Source attestation | Removed from MTC; may invalidate in-flight quorum (EC-09-like) |
| Reviewer assertion | A.3 assertion `revoked_at`; quorum recalculated |
| Recovery link | A.3 link revoke → case `REVOKED`; association unusable |
| Reviewer role | Prevents new assertions; historical signatures remain for audit |
| Entire evidence package | New package_hash required; prior approvals invalid |

### 11.2 Revocation triggers

- Fraud confirmed  
- Account takeover of email/phone used in MTC  
- Duplicate rightful claimant (conflict)  
- Legal request  
- Attestation issuer key compromise  
- Reviewer collusion discovery  

### 11.3 Properties

- Append-only; no hard-delete of revoke events  
- Revoked link cannot be reused (EC-11)  
- Appeals = **new case** + new `operation_key`  
- Emergency revoke: dual-control recommended (security + recovery lead)

---

## 12. Audit Requirements

Preserves A.3.7 append-only ledger; VLIS adds required event types
(design-level; implementation later):

| Event | When |
|---|---|
| `vlis.attestation_issued` | Server attestation created |
| `vlis.attestation_expired` | TTL passed / marked expired |
| `vlis.attestation_revoked` | Explicit revoke |
| `vlis.mtc_evaluated` | Pass/fail + rule ID + package_hash |
| `vlis.binding_check` | Pass/fail codes |
| `vlis.evidence_item_added` | Item hash + source_id |
| `recovery.*` | Existing A.3 case/assertion/link events |

Integrity rules:

- Missing audit write aborts business TX (EC-05).  
- Audit is append-only (DB trigger remains).  
- Redaction = tombstone hash, never silent delete.  
- REP samples (redacted) required before Council resolution.

---

## 13. Migration Strategy

VLIS enables **identity association** via manual recovery. It does **not**
authorize PMP-01B data migration by itself.

```text
Phase 0  Design approval (this document)          ← current
Phase 1  Attestation + MTC + evidence APIs (impl) — future
Phase 2  Stream B containment of client-authority paths
Phase 3  Stream C wire VLIS into recovery-only path
Phase 4  Security tests + redacted REP evidence
Phase 5  Council: BLK-001 RESOLVED
Phase 6  Only then reconsider release gate / PMP-01B
```

Migration of user content remains governed by PMP-01B and still requires:

- 0 cross-user association in rehearsal,
- consent rules,
- rollback strategy (PMP-01E / ops restore).

**Identity link ≠ data migration.** Linking is a prerequisite, not a substitute.

---

## 14. Rollout Strategy

| Stage | Population | Linking | Notes |
|---|---|---|---|
| R0 | None | Disabled | Design + dry-run fixtures only |
| R1 | Internal dogfood accounts | Manual recovery only | Shadow MTC metrics |
| R2 | Invited cohort (N small) | Manual recovery only | Fraud review weekly |
| R3 | Broader support-driven recovery | Manual recovery only | SLOs on case age |
| R∞ | Automatic linking | **Still forbidden** unless separate design + Council | Not in scope |

Rollout **does not** flip `V1_CHAT_PERCENTAGE` or product migration flags.
Those remain separate release decisions.

Kill switch: disable attestation issuance and/or case→READY transition via
config; open cases fail closed to `EVIDENCE_PENDING` / expire.

---

## 15. Operational Flow

End-to-end for operators (aligns with Operations Manual; recovery-specific):

1. **Intake** — Claimant opens request (authenticated). Support may help gather
   materials but cannot approve.  
2. **Challenges** — Operator/system triggers email/phone/billing/org checks;
   server stores attestations.  
3. **Package seal** — System computes `package_hash`, evaluates MTC.  
4. **Review queue** — Primary reviewer works checklist; signs approve/reject.  
5. **Four-eyes** — Second reviewer independently decides.  
6. **Link** — Recovery Service creates link inside TX with audit.  
7. **Notify** — Claimant informed; no silent data move.  
8. **Monitor** — Fraud sampling; revoke path ready.  
9. **Incident** — Suspected false link → emergency revoke + Council note.

On-call rules:

- Prefer revoke + new case over “fixing” rows.  
- Never bypass MTC during incidents.  
- DEPLOY/RESTORE procedures remain in Operations Manual; identity emergencies
  escalate to Security Authority.

---

## 16. Risk Analysis

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Insufficient High sources for legacy cohort | High | Recovery backlog | MTC-M2 / M1L2 paths; billing + verified contact |
| SIM swap defeats phone Medium | Medium | False Medium | Require second distinct Medium/High; fraud signals |
| Reviewer rubber-stamping | Medium | False links | Sampling audits; metrics; dual control |
| Privacy breach of KYC media | Low–Med | Legal/trust | Minimization, TTL, dual-control access |
| Scope creep into automatic linking | Medium | Critical security regression | Explicit non-goal; gate stays closed |
| Implementing before containment (Stream B) | Medium | Client authority bypass | Phase order enforced |
| Colluding reviewers | Low | Critical | Role hygiene; anomaly detection; revoke |
| Design approved but tests weak | Medium | False RESOLVED | Council requires REP security tests |

Residual risk acceptance: Manual recovery will be slower than automatic
linking. That is intentional.

---

## 17. Open Questions

| # | Question | Needed from | Default if unanswered |
|---|---|---|---|
| Q1 | Which KYC/government path is legally available in TR/target markets? | Legal + Product | Defer S1 High; rely on MTC-M2 |
| Q2 | Does legacy DB reliably store email/phone for challenge binding? | Data audit | If sparse, prioritize S7 payment + S8 sealed tickets |
| Q3 | Is there any previously enrolled WebAuthn/hardware key cohort? | Eng inventory | Assume no; S6 optional |
| Q4 | Billing processor: can we attest last4/customer_id server-side? | Payments | If no, S7 drops to Low uploads (hurts MTC) |
| Q5 | Retention periods for Restricted evidence? | Legal | Design assumes short TTL + tombstone |
| Q6 | Should case creator be allowed as primary reviewer? | Security Authority | Keep A.3 default (allowed primary, forbidden second) |
| Q7 | Fraud SLO: max cases/day per reviewer? | Ops | Set before R2 |
| Q8 | Cross-border claimants without local ID? | Product | Document alternate MTC-M2 path |
| Q9 | Language of rationale codes (TR/EN)? | Ops | Bilingual code table |
| Q10 | Will Stream B containment ship in same release train as VLIS impl? | Program | **Must** precede or accompany Stream C |

---

## 18. Recommended Architecture

### 18.1 Name

**VLIS-BCMP** — Verified Legacy Identity Source via Bounded Composite Manual Proof.

### 18.2 Why this option (vs alternatives)

| Option | Verdict |
|---|---|
| Re-enable legacy HS256 as ambient auth | **Rejected** — A.3 non-goal; widens attack surface |
| Email/device automatic match | **Rejected** — explicitly forbidden |
| Provider migration token only | **Deferred** — useful later; no provider token exists today |
| Pure reviewer discretion without MTC | **Rejected** — weakens fail-closed; unreviewable |
| **BCMP (recommended)** | **Accepted for design** — uses frozen recovery path; adds server attestations + MTC |

### 18.3 Logical components (future implementation map — not built now)

```text
┌────────────────┐   ┌─────────────────────┐   ┌──────────────────┐
│ Challenge APIs │──▶│ Attestation Issuer  │──▶│ Evidence Packager│
└────────────────┘   └─────────────────────┘   └────────┬─────────┘
                                                         │ package_hash
                                                         ▼
                                              ┌──────────────────────┐
                                              │ MTC Gate             │
                                              └──────────┬───────────┘
                                                         │
                                                         ▼
                                              ┌──────────────────────┐
                                              │ Frozen Recovery Core │
                                              │ (A.3.1–A.3.7)        │
                                              └──────────────────────┘
```

### 18.4 Contract preservation checklist

| Frozen contract | How VLIS-BCMP preserves it |
|---|---|
| Fail-closed | MTC fail / binding fail / dependency outage → no READY / no link |
| Four-eyes | Unchanged quorum; VLIS only feeds evidence |
| Append-only audit | New event types append; no rewrites |
| Signed assertions | Still Recovery Service–signed; hash binds to package |
| Transaction guarantees | Link/decision still single TX with audit |
| Idempotency | `operation_key` + challenge_id + package_hash replay rules |
| Replay protection | Short-lived attestations; assertion expiry; no link reuse |

### 18.5 Explicit non-goals (reaffirmed)

- Production code in this milestone  
- Automatic linking  
- PMP-01B/C start  
- Release gate OPEN as a side effect  
- Client-signed assertions  
- Ad-hoc SQL recovery  
- Weakening EC-01…EC-12  

### 18.6 Success criteria for *this design document*

- [x] Trust model defined  
- [x] Threat model defined  
- [x] Identity sources with High/Medium/Low  
- [x] Evidence collection model  
- [x] Verification workflow bound to A.3 states  
- [x] Reviewer responsibilities + decision tree  
- [x] Failure modes  
- [x] Revocation model  
- [x] Privacy model  
- [x] Audit requirements  
- [x] Migration strategy  
- [x] Rollout strategy  
- [x] Frozen contracts preserved  

### 18.7 Success criteria for later BLK-001 RESOLVED (not claimed now)

Per execution plan — all required:

1. Server-side VLIS exists (implementation of this design)  
2. Client-controlled identity authoritative in no flow  
3. Manual recovery policy integrated in execution flow  
4. Related security tests pass  
5. Approval, revoke, audit verified  
6. Release Council acceptance recorded in REP + Governance Health Check  

---

## 19. Document control

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-18 | Initial DESIGN_DRAFT for Stream A |

**Approval needed from:** Identity Authority · Security Authority · (inform)
Release Council  

**Next artifact after approval:** implementation plan for Streams B–C (still
must not bypass freeze process); security test list; REP addendum.

---

## Appendix A — Source quick reference

| ID | Source | Trust |
|---|---|---|
| S1 | Government identity | High |
| S2 | Verified email (server challenge) | Medium |
| S3 | Verified phone (server challenge) | Medium |
| S4 | Existing account ownership / capability | Medium–High |
| S5 | Historical login telemetry | Low |
| S6 | Hardware key (pre-enrolled) | High |
| S7 | Payment history (billing attestation) | Medium |
| S8 | Support evidence | Low–Medium |
| S9 | Social proof | Low |
| S10 | Organization records | Medium–High |

## Appendix B — Mapping to blocker brief streams

| Stream | This document |
|---|---|
| A — Define verified legacy source | **Satisfied at design level** (pending Authority approval) |
| B — Contain client-authority paths | Not done here — prerequisite for RESOLVED |
| C — Wire proof into manual recovery only | Not done here — follows approval |
| D — Council resolution package | Not done here — follows B+C evidence |

## Appendix C — Standing order (unchanged)

```text
Until BLK-001 is RESOLVED with Council acceptance:
  — Release gate stays CLOSED
  — Automatic linking stays DISABLED
  — No PMP-01B / PMP-01C start
  — No ad-hoc production identity SQL
  — No production code from this design milestone
```
