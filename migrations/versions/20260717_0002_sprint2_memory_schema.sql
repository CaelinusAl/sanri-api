-- Additive Sprint 2 schema extension. Existing rows and columns are preserved.
alter table public.v1_memories
  add column if not exists source text not null default 'manual',
  add column if not exists category text,
  add column if not exists confidence double precision not null default 1.0,
  add column if not exists approval_status text not null default 'approved',
  add column if not exists conversation_id uuid references public.v1_conversations(id) on delete set null,
  add column if not exists project_id uuid references public.v1_projects(id) on delete set null,
  add column if not exists updated_at timestamptz not null default now(),
  add column if not exists deleted_at timestamptz;

alter table public.v1_conversations
  add column if not exists active_mode text not null default 'aura',
  add column if not exists detected_intent text not null default 'general_chat',
  add column if not exists project_id uuid references public.v1_projects(id) on delete set null,
  add column if not exists close_summary jsonb,
  add column if not exists closed_at timestamptz;

alter table public.v1_aura_states
  add column if not exists active_mode text not null default 'aura',
  add column if not exists detected_intent text not null default 'general_chat',
  add column if not exists active_project_id uuid references public.v1_projects(id) on delete set null,
  add column if not exists next_smallest_action text;

alter table public.v1_projects
  add column if not exists status text not null default 'active',
  add column if not exists last_checkpoint jsonb,
  add column if not exists created_at timestamptz not null default now();

alter table public.v1_memories
  add constraint v1_memories_approval_status_check
  check (approval_status in ('proposed', 'approved', 'rejected'));

alter table public.v1_memories
  add constraint v1_memories_confidence_check
  check (confidence >= 0 and confidence <= 1);

create index if not exists v1_memories_retrieval_idx
  on public.v1_memories(user_id, approval_status, deleted_at, project_id, category);
create index if not exists v1_conversations_project_idx
  on public.v1_conversations(user_id, project_id, updated_at desc);
create index if not exists v1_projects_checkpoint_idx
  on public.v1_projects(user_id, updated_at desc);

alter table public.v1_memories enable row level security;
alter table public.v1_conversations enable row level security;
alter table public.v1_aura_states enable row level security;
alter table public.v1_projects enable row level security;

do $$
begin
  if not exists (select 1 from pg_policies where schemaname = 'public' and policyname = 'v1 memories own rows') then
    create policy "v1 memories own rows" on public.v1_memories
      for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and policyname = 'v1 conversations own rows') then
    create policy "v1 conversations own rows" on public.v1_conversations
      for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and policyname = 'v1 aura states own rows') then
    create policy "v1 aura states own rows" on public.v1_aura_states
      for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
  end if;
  if not exists (select 1 from pg_policies where schemaname = 'public' and policyname = 'v1 projects own rows') then
    create policy "v1 projects own rows" on public.v1_projects
      for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
  end if;
end
$$;
