-- PMP-01A.3.6 Durable Recovery Case Ledger
-- Persists case state + operation_key idempotency.
-- No identity mapping writes.

create table if not exists public.v1_recovery_cases (
  case_id uuid primary key default gen_random_uuid(),
  state text not null
    check (state in (
      'DRAFT',
      'EVIDENCE_PENDING',
      'READY_FOR_REVIEW',
      'AWAITING_SECOND_APPROVAL',
      'APPROVED',
      'LINK_CREATED',
      'REJECTED',
      'CANCELLED',
      'EXPIRED',
      'REVOKED',
      'CLOSED'
    )),
  subject_user_id uuid not null,
  claimed_legacy_identity_ref text not null,
  created_by uuid not null,
  evidence_hash text,
  evidence_type text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  expires_at timestamptz,
  state_version integer not null default 0
);

create index if not exists v1_recovery_cases_subject_idx
  on public.v1_recovery_cases(subject_user_id, created_at desc);

create index if not exists v1_recovery_cases_legacy_idx
  on public.v1_recovery_cases(claimed_legacy_identity_ref, created_at desc);

create unique index if not exists v1_recovery_cases_one_open_subject
  on public.v1_recovery_cases(subject_user_id)
  where state not in ('REJECTED', 'CANCELLED', 'EXPIRED', 'REVOKED', 'CLOSED');

create unique index if not exists v1_recovery_cases_one_open_legacy
  on public.v1_recovery_cases(claimed_legacy_identity_ref)
  where state not in ('REJECTED', 'CANCELLED', 'EXPIRED', 'REVOKED', 'CLOSED');

create table if not exists public.v1_recovery_case_operations (
  operation_key text primary key,
  case_id uuid not null references public.v1_recovery_cases(case_id),
  created_at timestamptz not null default now()
);

create index if not exists v1_recovery_case_operations_case_idx
  on public.v1_recovery_case_operations(case_id, created_at asc);

alter table public.v1_recovery_cases enable row level security;
alter table public.v1_recovery_case_operations enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and policyname = 'recovery cases service role only'
  ) then
    create policy "recovery cases service role only"
      on public.v1_recovery_cases for all to authenticated
      using (false) with check (false);
  end if;
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and policyname = 'recovery case operations service role only'
  ) then
    create policy "recovery case operations service role only"
      on public.v1_recovery_case_operations for all to authenticated
      using (false) with check (false);
  end if;
end
$$;
