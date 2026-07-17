"""Extend v1 for approved memory, session state, and project checkpoints.

Revision ID: 20260717_0002
Revises: 20260716_0001
"""
from alembic import op


revision = "20260717_0002"
down_revision = "20260716_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive only: existing rows remain addressable and existing text fields are preserved.
    op.execute("""
        alter table public.v1_memories
          add column if not exists source text not null default 'manual',
          add column if not exists category text,
          add column if not exists confidence double precision not null default 1.0,
          add column if not exists approval_status text not null default 'approved',
          add column if not exists conversation_id uuid references public.v1_conversations(id) on delete set null,
          add column if not exists project_id uuid references public.v1_projects(id) on delete set null,
          add column if not exists updated_at timestamptz not null default now(),
          add column if not exists deleted_at timestamptz;
    """)
    op.execute("""
        alter table public.v1_conversations
          add column if not exists active_mode text not null default 'aura',
          add column if not exists detected_intent text not null default 'general_chat',
          add column if not exists project_id uuid references public.v1_projects(id) on delete set null,
          add column if not exists close_summary jsonb,
          add column if not exists closed_at timestamptz;
    """)
    op.execute("""
        alter table public.v1_aura_states
          add column if not exists active_mode text not null default 'aura',
          add column if not exists detected_intent text not null default 'general_chat',
          add column if not exists active_project_id uuid references public.v1_projects(id) on delete set null,
          add column if not exists next_smallest_action text;
    """)
    op.execute("""
        alter table public.v1_projects
          add column if not exists status text not null default 'active',
          add column if not exists last_checkpoint jsonb,
          add column if not exists created_at timestamptz not null default now();
    """)
    op.execute("""
        do $$
        begin
          if not exists (
            select 1 from pg_constraint where conname = 'v1_memories_approval_status_check'
          ) then
            alter table public.v1_memories
              add constraint v1_memories_approval_status_check
              check (approval_status in ('proposed', 'approved', 'rejected'));
          end if;
          if not exists (
            select 1 from pg_constraint where conname = 'v1_memories_confidence_check'
          ) then
            alter table public.v1_memories
              add constraint v1_memories_confidence_check
              check (confidence >= 0 and confidence <= 1);
          end if;
        end
        $$;
    """)
    op.execute("""
        create index if not exists v1_memories_retrieval_idx
          on public.v1_memories(user_id, approval_status, deleted_at, project_id, category);
        create index if not exists v1_conversations_project_idx
          on public.v1_conversations(user_id, project_id, updated_at desc);
        create index if not exists v1_projects_checkpoint_idx
          on public.v1_projects(user_id, updated_at desc);
    """)
    op.execute("""
        alter table public.v1_memories enable row level security;
        alter table public.v1_conversations enable row level security;
        alter table public.v1_aura_states enable row level security;
        alter table public.v1_projects enable row level security;
    """)
    op.execute("""
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
    """)


def downgrade() -> None:
    op.execute("drop index if exists public.v1_memories_retrieval_idx")
    op.execute("drop index if exists public.v1_conversations_project_idx")
    op.execute("drop index if exists public.v1_projects_checkpoint_idx")
    op.execute("alter table public.v1_memories drop constraint if exists v1_memories_confidence_check")
    op.execute("alter table public.v1_memories drop constraint if exists v1_memories_approval_status_check")
    op.execute("""
        alter table public.v1_memories
          drop column if exists deleted_at,
          drop column if exists updated_at,
          drop column if exists project_id,
          drop column if exists conversation_id,
          drop column if exists approval_status,
          drop column if exists confidence,
          drop column if exists category,
          drop column if exists source
    """)
    op.execute("""
        alter table public.v1_conversations
          drop column if exists closed_at,
          drop column if exists close_summary,
          drop column if exists project_id,
          drop column if exists detected_intent,
          drop column if exists active_mode
    """)
    op.execute("""
        alter table public.v1_aura_states
          drop column if exists next_smallest_action,
          drop column if exists active_project_id,
          drop column if exists detected_intent,
          drop column if exists active_mode
    """)
    op.execute("""
        alter table public.v1_projects
          drop column if exists created_at,
          drop column if exists last_checkpoint,
          drop column if exists status
    """)
