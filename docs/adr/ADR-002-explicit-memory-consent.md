# ADR-002: Memory requires explicit consent

- Status: Accepted
- Date: 2026-07-18

## Decision

Long-term memory is never persisted or placed in prompt context without
explicit user consent. Proposed memories remain reviewable but are excluded
from retrieval. Approved, live, owner-scoped memories are the only records
eligible for context.

## Consequences

The legacy automatic `user_memory` write path must be migrated or disabled.
Memory approval and rejection become domain operations rather than incidental
database updates.
