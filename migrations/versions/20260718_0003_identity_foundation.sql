-- Schema only. This migration intentionally creates no identity mappings.
create table if not exists public.v1_identity_links (
  id uuid primary key default gen_random_uuid(),
  supabase_user_id uuid not null unique references auth.users(id) on delete cascade,
  legacy_user_id bigint not null unique,
  status text not null default 'unlinked'
    check (status in ('unlinked', 'verification_pending', 'verified', 'linked', 'conflict', 'revoked')),
  verification_method text,
  verification_evidence_hash text,
  initiated_by text,
  verified_at timestamptz,
  linked_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.v1_migration_audits (
  id uuid primary key default gen_random_uuid(),
  operation_key text not null unique,
  supabase_user_id uuid references auth.users(id) on delete set null,
  legacy_user_id bigint,
  operation text not null,
  status text not null,
  evidence_hash text,
  error_code text,
  rollback_state text,
  details jsonb,
  created_at timestamptz not null default now()
);

create index if not exists v1_migration_audits_supabase_idx
  on public.v1_migration_audits(supabase_user_id, created_at desc);
create index if not exists v1_migration_audits_legacy_idx
  on public.v1_migration_audits(legacy_user_id, created_at desc);

alter table public.v1_identity_links enable row level security;
alter table public.v1_migration_audits enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and policyname = 'identity links service role only'
  ) then
    create policy "identity links service role only"
      on public.v1_identity_links for all to authenticated
      using (false) with check (false);
  end if;
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public' and policyname = 'migration audits service role only'
  ) then
    create policy "migration audits service role only"
      on public.v1_migration_audits for all to authenticated
      using (false) with check (false);
  end if;
end
$$;

-- Replace broad ownership policies with relationship-aware policies. A
-- foreign key proves existence, not that the related row belongs to auth.uid().
drop policy if exists "v1 memories own rows" on public.v1_memories;
create policy "v1 memories own rows"
  on public.v1_memories for all to authenticated
  using (
    auth.uid() = user_id
    and (
      conversation_id is null
      or exists (
        select 1 from public.v1_conversations c
        where c.id = v1_memories.conversation_id
          and c.user_id = auth.uid()
      )
    )
    and (
      project_id is null
      or exists (
        select 1 from public.v1_projects p
        where p.id = v1_memories.project_id
          and p.user_id = auth.uid()
      )
    )
  )
  with check (
    auth.uid() = user_id
    and (
      conversation_id is null
      or exists (
        select 1 from public.v1_conversations c
        where c.id = v1_memories.conversation_id
          and c.user_id = auth.uid()
      )
    )
    and (
      project_id is null
      or exists (
        select 1 from public.v1_projects p
        where p.id = v1_memories.project_id
          and p.user_id = auth.uid()
      )
    )
  );

drop policy if exists "v1 conversations own rows" on public.v1_conversations;
create policy "v1 conversations own rows"
  on public.v1_conversations for all to authenticated
  using (
    auth.uid() = user_id
    and (
      project_id is null
      or exists (
        select 1 from public.v1_projects p
        where p.id = v1_conversations.project_id
          and p.user_id = auth.uid()
      )
    )
  )
  with check (
    auth.uid() = user_id
    and (
      project_id is null
      or exists (
        select 1 from public.v1_projects p
        where p.id = v1_conversations.project_id
          and p.user_id = auth.uid()
      )
    )
  );

drop policy if exists "v1 messages own rows" on public.v1_messages;
create policy "v1 messages own rows"
  on public.v1_messages for all to authenticated
  using (
    auth.uid() = user_id
    and exists (
      select 1 from public.v1_conversations c
      where c.id = v1_messages.conversation_id
        and c.user_id = auth.uid()
    )
  )
  with check (
    auth.uid() = user_id
    and exists (
      select 1 from public.v1_conversations c
      where c.id = v1_messages.conversation_id
        and c.user_id = auth.uid()
    )
  );
