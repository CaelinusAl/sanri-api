-- Apply this migration with Supabase SQL editor or `alembic upgrade head`
-- after converting it to an Alembic Python revision in deployment.

create extension if not exists vector;

create table if not exists public.v1_conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text,
  mode text not null default 'aura' check (mode in ('aura', 'reflection')),
  intent text not null default 'build',
  work_mode text not null default 'deep_work',
  session_goal text,
  emotional_climate text,
  reflection_after_action jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.v1_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.v1_conversations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  input_tokens integer,
  output_tokens integer,
  memory_suggestions jsonb,
  progress_report jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.v1_memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  content text not null,
  memory_type text not null default 'explicit',
  embedding extensions.vector(1536),
  created_at timestamptz not null default now()
);

create table if not exists public.v1_aura_states (
  user_id uuid primary key references auth.users(id) on delete cascade,
  current_focus text,
  energy_level text,
  active_project text,
  last_checkpoint text,
  relationship_style text not null default 'Strategic Partner',
  updated_at timestamptz not null default now()
);

create table if not exists public.v1_projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  current_sprint text,
  next_step text,
  notes jsonb,
  decisions jsonb,
  manifestos jsonb,
  risks jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists v1_conversations_user_idx on public.v1_conversations(user_id, updated_at desc);
create index if not exists v1_messages_conversation_idx on public.v1_messages(conversation_id, created_at);
create index if not exists v1_messages_user_idx on public.v1_messages(user_id, created_at);
create index if not exists v1_memories_user_idx on public.v1_memories(user_id, created_at desc);
create index if not exists v1_projects_user_idx on public.v1_projects(user_id, updated_at desc);

alter table public.v1_conversations enable row level security;
alter table public.v1_messages enable row level security;
alter table public.v1_memories enable row level security;
alter table public.v1_aura_states enable row level security;
alter table public.v1_projects enable row level security;

create policy "v1 conversations own rows" on public.v1_conversations
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "v1 messages own rows" on public.v1_messages
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "v1 memories own rows" on public.v1_memories
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "v1 aura states own rows" on public.v1_aura_states
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "v1 projects own rows" on public.v1_projects
  for all to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
