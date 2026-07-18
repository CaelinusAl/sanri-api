-- PMP-01A.3.7 Durable Recovery Audit Ledger
-- Append-only audit events; scoped uniqueness (case_id, operation_key, event_type).
-- No identity mapping writes. No raw tokens / signing secrets.

create table if not exists public.v1_recovery_audit_events (
  event_id uuid primary key default gen_random_uuid(),
  event_type text not null,
  case_id uuid not null,
  operation_key text not null,
  actor_id uuid not null,
  created_at timestamptz not null default now(),
  from_state text,
  to_state text,
  entity_ref text,
  detail jsonb not null default '{}'::jsonb,
  constraint v1_recovery_audit_events_case_op_type_uq
    unique (case_id, operation_key, event_type)
);

create index if not exists v1_recovery_audit_events_case_idx
  on public.v1_recovery_audit_events(case_id, created_at asc);

create index if not exists v1_recovery_audit_events_op_idx
  on public.v1_recovery_audit_events(operation_key, created_at asc);

create or replace function public.v1_recovery_audit_events_append_only()
returns trigger
language plpgsql
as $$
begin
  raise exception 'v1_recovery_audit_events is append-only';
end;
$$;

drop trigger if exists v1_recovery_audit_events_append_only_trg
  on public.v1_recovery_audit_events;

create trigger v1_recovery_audit_events_append_only_trg
  before update or delete on public.v1_recovery_audit_events
  for each row
  execute function public.v1_recovery_audit_events_append_only();

alter table public.v1_recovery_audit_events enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and policyname = 'recovery audit events service role only'
  ) then
    create policy "recovery audit events service role only"
      on public.v1_recovery_audit_events for all to authenticated
      using (false) with check (false);
  end if;
end
$$;
