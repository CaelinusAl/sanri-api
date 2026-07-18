# Release Evidence Pack (REP)

**Release:** `x.y.z`  
**Train:** Alpha / Beta / RC / 1.0  
**Status:** DRAFT / IN REVIEW / BLOCKED / READY / APPROVED / RELEASED /
ROLLED BACK  
**Release Owner:**  
**Evidence date:**  
**Repository revision:**  
**Release directory:** `releases/x.y.z/`

## Constitutional Metadata

```text
Authority Level: Level 5 — Operations
Owner: Release Owner / Release Council
Source of Truth: Release Evidence Pack for this version
Supersedes: None
Depends On: Release Constitution, Governance Framework, SDS, SLS
Referenced ADRs:
Related Standards: Security & Trust Standard, Engineering Handbook
Lifecycle State: Operational
Last Reviewed:
```

This document is the authoritative evidence record for one SANRI release.
Missing evidence is a blocker, not an implicit pass.

## Release evidence directory

Every release must have a versioned evidence directory:

```text
releases/
└── x.y.z/
    ├── release-notes.md
    ├── REP.md
    ├── security-report.pdf
    ├── ai-quality-report.pdf
    ├── performance-report.pdf
    ├── rollback-report.pdf
    ├── migration-report.pdf
    └── council-approval.md
```

`REP.md` is the index and authoritative decision record. The attached reports
are immutable evidence artifacts; replacing one requires a new revision,
reason, owner, and Council review.

Required artifacts may explicitly contain `not applicable` with an owner and
reason. An absent artifact is not an implicit pass.

## 1. Scope and change inventory

- Release objective:
- Included user-visible changes:
- Included infrastructure/database changes:
- Explicitly excluded changes:
- Changed repositories:
- Changed files or migration identifiers:
- Feature flags and rollout percentages:
- Production traffic status:

## 2. Build and test results

| Area | Command or pipeline | Result | Evidence link | Owner |
|---|---|---|---|---|
| Backend tests |  |  |  |  |
| Backend type/compile check |  |  |  |  |
| Mobile tests |  |  |  |  |
| Mobile type-check |  |  |  |  |
| Mobile lint |  |  |  |  |
| Web tests |  |  |  |  |
| Web build |  |  |  |  |
| Web lint |  |  |  |  |
| Integration tests |  |  |  |  |

## 3. Authentication and ownership

- Canonical identity:
- Registration result:
- Login result:
- Refresh result:
- Session restoration result:
- Logout result:
- Expired-token result:
- Revoked-token result:
- `/v1/me` result:
- Live RLS environment:
- Test User A:
- Test User B:
- Service-role context:
- Cross-user read/write/delete results:
- Nested relation and foreign-key results:
- Tables without complete ownership enforcement:

## 4. Memory and consent

- Proposed memory behavior:
- Approved memory behavior:
- Rejected memory behavior:
- Deleted memory behavior:
- Cross-user memory behavior:
- Automatic memory writes:
- Consent test report:

## 5. AI Quality Gate

| Gate | Result | Evidence | Owner |
|---|---|---|---|
| Correct intent and mode |  |  |  |
| Output format |  |  |  |
| No unnecessary poetry |  |  |  |
| Memory relevance |  |  |  |
| No hallucinated memory |  |  |  |
| Prompt injection resistance |  |  |  |
| Sensitive-content behavior |  |  |  |
| Provider failure behavior |  |  |  |

## 6. Golden Corpus

- Corpus version:
- Number of cases:
- Categories covered:
- Pass rate:
- Critical regressions:
- Forbidden-behavior violations:
- Parity differences:
- Approval owner:

## 7. Security and trust

- Security audit reference:
- P0 findings:
- P1 findings:
- P2 findings:
- Identity ambiguity findings:
- RLS findings:
- Secret/token exposure check:
- Privacy and logging check:
- Manual recovery impact:
- User notification impact:
- Security Authority decision:

Any open P0 or unresolved veto keeps this REP `BLOCKED`.

## 8. Performance and operations

- TTFT:
- Total response latency:
- Error rate:
- Provider error rate:
- Streaming interruption rate:
- Token cost:
- Load-test reference:
- Observability dashboards:
- Alert thresholds:
- Kill-switch verification:
- Operations Authority decision:

## 9. Migration impact

- Migration performed: yes / no
- Dry-run reference:
- Records assessed:
- Linkable candidates:
- Conflicts:
- Duplicates:
- Orphans:
- Ambiguous ownership:
- Memory consent impact:
- Subscription/payment impact:
- Data-loss risk:
- Rollback impact:

No production mapping or user-data migration may be implied by an empty
section; the section must explicitly state `not performed` when applicable.

## 10. ADR and governance impact

- ADRs reviewed:
- ADRs changed:
- New ADRs required:
- Governance Framework impact:
- Release Constitution impact:
- Security & Trust Standard impact:
- Documentation changes:
- Known deviations and expiry dates:

## 11. Rollback verification

- Rollback procedure:
- Rehearsal environment:
- Rehearsal date:
- Data preservation result:
- V1-created data preservation result:
- Recovery time:
- Recovery point:
- Rollback owner:
- Operations Authority approval:

## 12. Known risks

| Risk | Severity | User-trust impact | Mitigation | Owner | Expiry |
|---|---|---|---|---|---|
|  | P0/P1/P2 |  |  |  |  |

## 13. Release Council decision

| Role | Decision | Veto status | Evidence reference | Signed at |
|---|---|---|---|---|
| Security Authority |  |  |  |  |
| Identity Authority |  |  |  |  |
| AI Quality Authority |  |  |  |  |
| Product Authority |  |  |  |  |
| Architecture Authority |  |  |  |  |
| Operations Authority |  |  |  |  |

**Final decision:** BLOCKED / READY / APPROVED / RELEASED / ROLLED BACK  
**Release Council record:**  
**Unresolved vetoes:**  
**Post-release review date:**  
