-- PMP-01A.3.2 Durable Signed Assertion Store
-- Does not create identity links, open rollout, or alter migration gates.

create table if not exists public.v1_recovery_assertions (
  assertion_id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  operation_key text not null unique,
  policy_version text not null,
  schema_version text not null default '1',
  evidence_reference_hash text not null,
  asserted_supabase_user_id uuid not null,
  asserted_legacy_user_id text not null,
  reviewer_id uuid not null,
  reviewer_role text not null
    check (reviewer_role in ('primary_reviewer', 'second_reviewer')),
  decision text not null
    check (decision in ('approve', 'reject')),
  rationale_code text not null,
  signature text not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz
);

create index if not exists v1_recovery_assertions_case_idx
  on public.v1_recovery_assertions(case_id, created_at asc);

create index if not exists v1_recovery_assertions_reviewer_idx
  on public.v1_recovery_assertions(reviewer_id, created_at desc);

alter table public.v1_recovery_assertions enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and policyname = 'recovery assertions service role only'
  ) then
    create policy "recovery assertions service role only"
      on public.v1_recovery_assertions for all to authenticated
      using (false) with check (false);
  end if;
end
$$;
