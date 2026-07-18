# REP-001 Release Notes

**Train:** Alpha — security-core freeze  
**Tip:** `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab` (`pmp01a37-complete`)  
**Date:** 2026-07-18  
**Ship to production:** **NO**

## What this freeze delivers

Manual recovery **security core** for PMP-01A.3:

1. Reviewer API bound to server-side JWT + role  
2. Durable signed assertions  
3. Four-eyes quorum  
4. Quorum-gated recovery links (hash-only token persistence)  
5. Thin recovery UI (no client authority)  
6. Durable recovery case ledger + `operation_key` idempotency  
7. Durable append-only audit ledger (PostgreSQL trigger)  
8. Validated on real PostgreSQL (A.3.8)  
9. Release-readiness assessed as **NO-GO** (A.3.9) pending `PMP-01A-BLK-001`

## What this freeze does **not** deliver

- Open release gate  
- Automatic identity linking  
- Production user migration  
- Resolution of `PMP-01A-BLK-001`  
- PMP-01B / PMP-01C / Context Engine / Project Engine enablement  

## Operator note

Use `docs/operations/OPERATIONS-MANUAL.md` for deploy / restart / backup /
restore / incident / rollback. Do not treat this freeze as production
authorization.
