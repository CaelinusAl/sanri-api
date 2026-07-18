# REP-001

First Release Evidence Package for the PMP-01A.3 security-core freeze.

| Field | Value |
|---|---|
| Tip | `f7cc6b3632dc17adea8547c7fd983e0b3dbf44ab` |
| Tag | `pmp01a37-complete` |
| Status | **BLOCKED** (engineering freeze ready; production GO blocked) |
| Authoritative file | [`REP.md`](./REP.md) |

## Read order

1. [`REP.md`](./REP.md) — full evidence pack (tests, commits, tags, validations)
2. [`release-notes.md`](./release-notes.md)
3. [`a38-postgresql-validation.md`](./a38-postgresql-validation.md)
4. [`council-approval.md`](./council-approval.md)
5. Companion: [`../../docs/operations/OPERATIONS-MANUAL.md`](../../docs/operations/OPERATIONS-MANUAL.md)
6. Next focus: [`../../docs/blockers/PMP-01A-BLK-001.md`](../../docs/blockers/PMP-01A-BLK-001.md)
7. BLK-001 design freeze package (Stream A/B/B2, entry gate, L-06):
   [`../../docs/blockers/`](../../docs/blockers/) — tag `pmp01a39-governance-freeze`
   when present. Status: design frozen; entry gate still `PENDING`; BLK-001 OPEN.

## PDF export (optional)

From repo root (requires pandoc):

```bash
pandoc releases/REP-001/REP.md -o releases/REP-001/REP-001.pdf --from markdown --pdf-engine=xelatex
```

If pandoc/PDF engine is unavailable, `REP.md` remains the single source of truth.
