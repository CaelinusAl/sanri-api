# SANRI Architecture Decision Records

**Framework Status:** Operational

ADRs record durable architectural decisions for SANRI OS. A change to the
domain model, orchestration path, memory contract, provider boundary, or
legacy compatibility policy must reference an existing ADR or add a new one.

## Status values

- `Proposed`: under review
- `Accepted`: current decision
- `Deprecated`: replaced by a newer decision

## Current Sprint 3 decisions

- ADR-001: AURA is the only orchestrator
- ADR-002: Memory requires explicit consent
- ADR-003: Provider independence
- ADR-004: Project Engine is a domain capability
- ADR-005: Context Engine is isolated
- ADR-006: Session close is mandatory
- ADR-007: V1 is the single source of truth
- ADR-008: Legacy uses a compatibility adapter
- ADR-009: Domain layer boundaries
- ADR-010: Staged traffic migration
- ADR-011: Canonical Supabase identity
- ADR-012: Verified legacy account linking
- ADR-013: Fail-closed legacy compatibility
- ADR-014: Anonymous identity policy
- ADR-015: Relationship-aware RLS
- ADR-016: Federated sources of truth
