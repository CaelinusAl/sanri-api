-- PMP-01A.3.4 Recovery Link Lifecycle
-- Hashed secrets only. Does not create identity links, open rollout,
-- or enable automatic linking / migration.

create table if not exists public.v1_recovery_links (
  link_id uuid primary key default gen_random_uuid(),
  case_id uuid not null,
  operation_key text not null unique,
  token_hash text not null,
  evidence_reference_hash text not null,
  created_by uuid not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  revoked_at timestamptz,
  revoked_by uuid,
  revoke_reason text,
  used_at timestamptz
);

create index if not exists v1_recovery_links_case_idx
  on public.v1_recovery_links(case_id, created_at asc);

create unique index if not exists v1_recovery_links_one_active_per_case
  on public.v1_recovery_links(case_id)
  where revoked_at is null and used_at is null;

alter table public.v1_recovery_links enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and policyname = 'recovery links service role only'
  ) then
    create policy "recovery links service role only"
      on public.v1_recovery_links for all to authenticated
      using (false) with check (false);
  end if;
end
$$;
