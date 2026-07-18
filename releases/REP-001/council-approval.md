# Council Approval — REP-001

**Package:** REP-001  
**Tip:** `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab`  
**Decision:** `BLOCKED`  
**Date opened:** 2026-07-18

## Motion

Freeze the PMP-01A.3 security core (A.3.1–A.3.8 evidence) as the technical
baseline for further PMP-01A work, **without** opening the release gate and
**without** authorizing production migration or automatic linking.

## Conditions that keep the decision BLOCKED

1. `PMP-01A-BLK-001` is not `RESOLVED` with Release Council acceptance.  
2. Hardcoded credential default in `_check_all.py` is not removed / rotated.  
3. Production backup/restore rehearsal is not recorded.  
4. Official PMP status tables are not refreshed to reflect A.3.5–A.3.8 evidence
   and operational exit criteria.

## Signature block (to be completed by authorities)

| Role | Name | Decision | Date | Signature |
|---|---|---|---|---|
| Security Authority |  |  |  |  |
| Identity Authority |  |  |  |  |
| Product Authority |  |  |  |  |
| Architecture Authority |  | ACCEPT freeze tip (no ship) | 2026-07-18 | evidence tip |
| Operations Authority |  |  |  |  |

**Allowed next focus after filing this pack:**  
entire team → `docs/blockers/PMP-01A-BLK-001.md`

**Forbidden until BLK-001 RESOLVED + this REP updated:**  
PMP-01B, PMP-01C, production migration, automatic linking, release-gate OPEN.
