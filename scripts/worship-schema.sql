-- Worship domain schema for Mindex
-- Run in Supabase SQL editor after reviewing.
--
-- This schema defines the Worship domain model independently from older
-- service tables.
--
-- Canonical model:
--   Worship Service > Section > Element > Slide
--
-- Naming decision:
--   Keep "worship service" for the top-level service instance. The app tab is
--   Worship, and "worship service" is the natural English church-domain term.
--   Worship data lives in the normalized mindex_worship_* tables.
--
-- Template model:
--   Service Template / Section Template / Element Template / Slide Template
--
-- Import model:
--   PPT/PDF/manual sources become reviewed import sources/mappings, not source
--   of truth over curated Mindex Praise/Scripture data.

create extension if not exists pgcrypto;

-- ── Shared timestamp trigger ────────────────────────────────────────────────
create or replace function public.mindex_touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ── Stable service taxonomy ────────────────────────────────────────────────
create table if not exists public.mindex_worship_service_types (
  id text primary key,
  display_name text not null,
  short_name text not null default '',
  group_key text not null default 'public',
  sort_order int not null default 0,
  is_active boolean not null default true,
  default_output_context text not null default 'auto'
    check (default_output_context in ('auto', 'chromakey', 'fullscreen')),
  chromakey_enabled boolean not null default false,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists mindex_worship_service_types_touch_updated_at on public.mindex_worship_service_types;
create trigger mindex_worship_service_types_touch_updated_at
before update on public.mindex_worship_service_types
for each row execute function public.mindex_touch_updated_at();

create index if not exists mindex_worship_service_types_group_sort_idx
  on public.mindex_worship_service_types (group_key, sort_order, id);

-- ── Templates ───────────────────────────────────────────────────────────────
create table if not exists public.mindex_worship_templates (
  id uuid primary key default gen_random_uuid(),
  template_level text not null
    check (template_level in ('service', 'section', 'element', 'slide')),
  stable_key text not null,
  version int not null default 1,
  version_key text not null default '',
  name text not null,
  service_type_id text references public.mindex_worship_service_types(id),
  parent_template_id uuid references public.mindex_worship_templates(id) on delete set null,
  base_template_id uuid references public.mindex_worship_templates(id) on delete set null,
  effective_from date not null default date '1900-01-01',
  effective_to date,
  element_type text,
  slide_type text,
  output_context text not null default 'auto'
    check (output_context in ('auto', 'chromakey', 'fullscreen')),
  is_active boolean not null default true,
  is_default boolean not null default false,
  description text not null default '',
  change_set jsonb not null default '{}'::jsonb,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (stable_key, version)
);

alter table public.mindex_worship_templates
  add column if not exists version_key text not null default '',
  add column if not exists base_template_id uuid references public.mindex_worship_templates(id) on delete set null,
  add column if not exists effective_from date not null default date '1900-01-01',
  add column if not exists effective_to date,
  add column if not exists change_set jsonb not null default '{}'::jsonb;

drop trigger if exists mindex_worship_templates_touch_updated_at on public.mindex_worship_templates;
create trigger mindex_worship_templates_touch_updated_at
before update on public.mindex_worship_templates
for each row execute function public.mindex_touch_updated_at();

create index if not exists mindex_worship_templates_level_key_idx
  on public.mindex_worship_templates (template_level, stable_key, version desc);
create index if not exists mindex_worship_templates_effective_idx
  on public.mindex_worship_templates (service_type_id, template_level, stable_key, effective_from desc, version desc)
  where is_active;
create index if not exists mindex_worship_templates_service_type_idx
  on public.mindex_worship_templates (service_type_id, template_level, is_active);
create index if not exists mindex_worship_templates_parent_idx
  on public.mindex_worship_templates (parent_template_id);
create index if not exists mindex_worship_templates_base_idx
  on public.mindex_worship_templates (base_template_id);

create table if not exists public.mindex_worship_template_items (
  id uuid primary key default gen_random_uuid(),
  template_id uuid not null references public.mindex_worship_templates(id) on delete cascade,
  child_template_id uuid references public.mindex_worship_templates(id) on delete set null,
  sort_order int not null default 0,
  slot_key text not null default '',
  default_title text not null default '',
  default_person text not null default '',
  default_body text not null default '',
  required boolean not null default false,
  flexible boolean not null default true,
  repeatable boolean not null default false,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists mindex_worship_template_items_touch_updated_at on public.mindex_worship_template_items;
create trigger mindex_worship_template_items_touch_updated_at
before update on public.mindex_worship_template_items
for each row execute function public.mindex_touch_updated_at();

create index if not exists mindex_worship_template_items_template_idx
  on public.mindex_worship_template_items (template_id, sort_order);
create index if not exists mindex_worship_template_items_child_idx
  on public.mindex_worship_template_items (child_template_id);

-- ── Worship instances ──────────────────────────────────────────────────────
create table if not exists public.mindex_worship_services (
  id uuid primary key default gen_random_uuid(),
  service_type_id text not null references public.mindex_worship_service_types(id),
  service_date date not null,
  service_date_end date,
  title text not null default '',
  service_alias text not null default '',
  status text not null default 'draft'
    check (status in ('draft', 'ready', 'live', 'complete', 'archived')),
  worship_leader text not null default '',
  praise_leader text not null default '',
  template_id uuid references public.mindex_worship_templates(id) on delete set null,
  template_modified boolean not null default false,
  source_kind text not null default 'mindex'
    check (source_kind in ('mindex', 'manual', 'ppt', 'pdf', 'import', 'archive')),
  source_ref jsonb not null default '{}'::jsonb,
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists mindex_worship_services_touch_updated_at on public.mindex_worship_services;
create trigger mindex_worship_services_touch_updated_at
before update on public.mindex_worship_services
for each row execute function public.mindex_touch_updated_at();

create index if not exists mindex_worship_services_type_date_idx
  on public.mindex_worship_services (service_type_id, service_date desc);
create unique index if not exists mindex_worship_services_identity_idx
  on public.mindex_worship_services (service_type_id, service_date, coalesce(service_date_end, service_date), title);
create index if not exists mindex_worship_services_template_idx
  on public.mindex_worship_services (template_id);
create index if not exists mindex_worship_services_status_idx
  on public.mindex_worship_services (status, service_date);

create table if not exists public.mindex_worship_sections (
  id uuid primary key default gen_random_uuid(),
  service_id uuid not null references public.mindex_worship_services(id) on delete cascade,
  sort_order int not null default 0,
  section_key text not null default '',
  title text not null,
  template_id uuid references public.mindex_worship_templates(id) on delete set null,
  template_modified boolean not null default false,
  source_kind text not null default 'mindex'
    check (source_kind in ('mindex', 'manual', 'ppt', 'pdf', 'import', 'archive')),
  source_ref jsonb not null default '{}'::jsonb,
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists mindex_worship_sections_touch_updated_at on public.mindex_worship_sections;
create trigger mindex_worship_sections_touch_updated_at
before update on public.mindex_worship_sections
for each row execute function public.mindex_touch_updated_at();

create index if not exists mindex_worship_sections_service_idx
  on public.mindex_worship_sections (service_id, sort_order);
create index if not exists mindex_worship_sections_template_idx
  on public.mindex_worship_sections (template_id);

create table if not exists public.mindex_worship_elements (
  id uuid primary key default gen_random_uuid(),
  section_id uuid not null references public.mindex_worship_sections(id) on delete cascade,
  sort_order int not null default 0,
  element_type text not null
    check (element_type in (
      'blank',
      'plain_text',
      'title_person',
      'body',
      'praise',
      'scripture_reading',
      'scripture_body',
      'image',
      'video',
      'score',
      'editable',
      'ppt',
      'pdf'
    )),
  title text not null default '',
  person text not null default '',
  body text not null default '',
  song_id uuid references public.mindex_songs(id) on delete set null,
  song_version_id uuid references public.mindex_song_versions(id) on delete set null,
  scripture_id uuid references public.mindex_scriptures(id) on delete set null,
  scripture_reference text not null default '',
  asset jsonb not null default '{}'::jsonb,
  input_mode text not null default ''
    check (input_mode in ('', 'praise_db', 'score_db', 'lyrics_db', 'manual_praise', 'text', 'scripture', 'asset', 'config', 'none')),
  content_state jsonb not null default '{}'::jsonb,
  template_id uuid references public.mindex_worship_templates(id) on delete set null,
  template_modified boolean not null default false,
  source_kind text not null default 'mindex'
    check (source_kind in ('mindex', 'manual', 'ppt', 'pdf', 'import', 'archive')),
  source_ref jsonb not null default '{}'::jsonb,
  review_status text not null default 'draft'
    check (review_status in ('draft', 'matched', 'needs_review', 'approved')),
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists mindex_worship_elements_touch_updated_at on public.mindex_worship_elements;
create trigger mindex_worship_elements_touch_updated_at
before update on public.mindex_worship_elements
for each row execute function public.mindex_touch_updated_at();

create index if not exists mindex_worship_elements_section_idx
  on public.mindex_worship_elements (section_id, sort_order);
create index if not exists mindex_worship_elements_type_idx
  on public.mindex_worship_elements (element_type);
create index if not exists mindex_worship_elements_song_idx
  on public.mindex_worship_elements (song_id);
create index if not exists mindex_worship_elements_scripture_idx
  on public.mindex_worship_elements (scripture_id);
create index if not exists mindex_worship_elements_input_mode_idx
  on public.mindex_worship_elements (input_mode);
create index if not exists mindex_worship_elements_template_idx
  on public.mindex_worship_elements (template_id);

create table if not exists public.mindex_worship_slides (
  id uuid primary key default gen_random_uuid(),
  element_id uuid not null references public.mindex_worship_elements(id) on delete cascade,
  sort_order int not null default 0,
  slide_type text not null
    check (slide_type in (
      'blank',
      'plain_text',
      'title_person',
      'body',
      'praise_title',
      'praise_body',
      'scripture_reading',
      'scripture_body',
      'image',
      'video',
      'score',
      'editable',
      'ppt',
      'pdf'
    )),
  output_context text not null default 'auto'
    check (output_context in ('auto', 'chromakey', 'fullscreen')),
  title text not null default '',
  body text not null default '',
  marker text not null default '',
  media jsonb not null default '{}'::jsonb,
  layout jsonb not null default '{}'::jsonb,
  template_id uuid references public.mindex_worship_templates(id) on delete set null,
  template_modified boolean not null default false,
  source_kind text not null default 'mindex'
    check (source_kind in ('mindex', 'manual', 'ppt', 'pdf', 'import', 'archive')),
  source_ref jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists mindex_worship_slides_touch_updated_at on public.mindex_worship_slides;
create trigger mindex_worship_slides_touch_updated_at
before update on public.mindex_worship_slides
for each row execute function public.mindex_touch_updated_at();

create index if not exists mindex_worship_slides_element_idx
  on public.mindex_worship_slides (element_id, sort_order);
create index if not exists mindex_worship_slides_template_idx
  on public.mindex_worship_slides (template_id);

-- ── Import review pipeline ─────────────────────────────────────────────────
create table if not exists public.mindex_worship_import_sources (
  id uuid primary key default gen_random_uuid(),
  source_kind text not null
    check (source_kind in ('ppt', 'pdf', 'manual', 'archive', 'setlist')),
  source_name text not null default '',
  source_path text not null default '',
  source_hash text not null default '',
  service_type_id text references public.mindex_worship_service_types(id),
  service_date date,
  status text not null default 'parsed'
    check (status in ('parsed', 'reviewing', 'applied', 'archived')),
  raw_payload jsonb not null default '{}'::jsonb,
  parse_report jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists mindex_worship_import_sources_touch_updated_at on public.mindex_worship_import_sources;
create trigger mindex_worship_import_sources_touch_updated_at
before update on public.mindex_worship_import_sources
for each row execute function public.mindex_touch_updated_at();

create index if not exists mindex_worship_import_sources_service_idx
  on public.mindex_worship_import_sources (service_type_id, service_date);
create index if not exists mindex_worship_import_sources_hash_idx
  on public.mindex_worship_import_sources (source_hash);

create table if not exists public.mindex_worship_import_candidates (
  id uuid primary key default gen_random_uuid(),
  import_source_id uuid not null references public.mindex_worship_import_sources(id) on delete cascade,
  sort_order int not null default 0,
  candidate_level text not null
    check (candidate_level in ('service', 'section', 'element', 'slide')),
  candidate_key text not null default '',
  raw_label text not null default '',
  raw_title text not null default '',
  raw_body text not null default '',
  normalized_label text not null default '',
  normalized_title text not null default '',
  normalized_body text not null default '',
  suggested_type text not null default '',
  suggested_template_id uuid references public.mindex_worship_templates(id) on delete set null,
  suggested_song_id uuid references public.mindex_songs(id) on delete set null,
  suggested_scripture_id uuid references public.mindex_scriptures(id) on delete set null,
  confidence numeric(5,4) not null default 0,
  review_status text not null default 'needs_review'
    check (review_status in ('needs_review', 'matched', 'approved', 'rejected')),
  raw_payload jsonb not null default '{}'::jsonb,
  normalized_payload jsonb not null default '{}'::jsonb,
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists mindex_worship_import_candidates_touch_updated_at on public.mindex_worship_import_candidates;
create trigger mindex_worship_import_candidates_touch_updated_at
before update on public.mindex_worship_import_candidates
for each row execute function public.mindex_touch_updated_at();

create index if not exists mindex_worship_import_candidates_source_idx
  on public.mindex_worship_import_candidates (import_source_id, sort_order);
create index if not exists mindex_worship_import_candidates_review_idx
  on public.mindex_worship_import_candidates (review_status, confidence desc);
create index if not exists mindex_worship_import_candidates_song_idx
  on public.mindex_worship_import_candidates (suggested_song_id);
create index if not exists mindex_worship_import_candidates_scripture_idx
  on public.mindex_worship_import_candidates (suggested_scripture_id);

create table if not exists public.mindex_worship_import_mappings (
  id uuid primary key default gen_random_uuid(),
  import_source_id uuid not null references public.mindex_worship_import_sources(id) on delete cascade,
  import_candidate_id uuid references public.mindex_worship_import_candidates(id) on delete cascade,
  target_level text not null
    check (target_level in ('service', 'section', 'element', 'slide')),
  target_id uuid,
  review_status text not null default 'needs_review'
    check (review_status in ('needs_review', 'matched', 'approved', 'rejected')),
  confidence numeric(5,4) not null default 0,
  raw_payload jsonb not null default '{}'::jsonb,
  normalized_payload jsonb not null default '{}'::jsonb,
  notes text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

drop trigger if exists mindex_worship_import_mappings_touch_updated_at on public.mindex_worship_import_mappings;
create trigger mindex_worship_import_mappings_touch_updated_at
before update on public.mindex_worship_import_mappings
for each row execute function public.mindex_touch_updated_at();

create index if not exists mindex_worship_import_mappings_source_idx
  on public.mindex_worship_import_mappings (import_source_id, target_level);
create index if not exists mindex_worship_import_mappings_candidate_idx
  on public.mindex_worship_import_mappings (import_candidate_id);
create index if not exists mindex_worship_import_mappings_review_idx
  on public.mindex_worship_import_mappings (review_status, confidence desc);

-- ── Presenter-friendly read model ──────────────────────────────────────────
create or replace view public.mindex_worship_presenter_slides as
select
  svc.id as service_id,
  svc.service_type_id,
  svc.service_date,
  sec.id as section_id,
  sec.sort_order as section_order,
  sec.section_key,
  sec.title as section_title,
  el.id as element_id,
  el.sort_order as element_order,
  el.element_type,
  el.title as element_title,
  el.person as element_person,
  el.song_id,
  el.song_version_id,
  el.scripture_id,
  el.scripture_reference,
  sl.id as slide_id,
  sl.sort_order as slide_order,
  sl.slide_type,
  sl.output_context,
  sl.title as slide_title,
  sl.body as slide_body,
  sl.marker as slide_marker,
  sl.media,
  sl.layout
from public.mindex_worship_services svc
join public.mindex_worship_sections sec on sec.service_id = svc.id
join public.mindex_worship_elements el on el.section_id = sec.id
join public.mindex_worship_slides sl on sl.element_id = el.id;

-- ── RLS: legacy prototype collaboration model.
-- Do not run this block against the shared church database. The production
-- security contract is in scripts/admin-auth-rls.sql: anon may read, and only
-- authenticated administrators may write. Use supabase-rls-audit.sql after
-- applying RLS changes.
alter table public.mindex_worship_service_types enable row level security;
alter table public.mindex_worship_templates enable row level security;
alter table public.mindex_worship_template_items enable row level security;
alter table public.mindex_worship_services enable row level security;
alter table public.mindex_worship_sections enable row level security;
alter table public.mindex_worship_elements enable row level security;
alter table public.mindex_worship_slides enable row level security;
alter table public.mindex_worship_import_sources enable row level security;
alter table public.mindex_worship_import_candidates enable row level security;
alter table public.mindex_worship_import_mappings enable row level security;

drop policy if exists "mindex_worship_service_types_shared_all" on public.mindex_worship_service_types;
create policy "mindex_worship_service_types_shared_all"
  on public.mindex_worship_service_types for all to anon using (true) with check (true);

drop policy if exists "mindex_worship_templates_shared_all" on public.mindex_worship_templates;
create policy "mindex_worship_templates_shared_all"
  on public.mindex_worship_templates for all to anon using (true) with check (true);

drop policy if exists "mindex_worship_template_items_shared_all" on public.mindex_worship_template_items;
create policy "mindex_worship_template_items_shared_all"
  on public.mindex_worship_template_items for all to anon using (true) with check (true);

drop policy if exists "mindex_worship_services_shared_all" on public.mindex_worship_services;
create policy "mindex_worship_services_shared_all"
  on public.mindex_worship_services for all to anon using (true) with check (true);

drop policy if exists "mindex_worship_sections_shared_all" on public.mindex_worship_sections;
create policy "mindex_worship_sections_shared_all"
  on public.mindex_worship_sections for all to anon using (true) with check (true);

drop policy if exists "mindex_worship_elements_shared_all" on public.mindex_worship_elements;
create policy "mindex_worship_elements_shared_all"
  on public.mindex_worship_elements for all to anon using (true) with check (true);

drop policy if exists "mindex_worship_slides_shared_all" on public.mindex_worship_slides;
create policy "mindex_worship_slides_shared_all"
  on public.mindex_worship_slides for all to anon using (true) with check (true);

drop policy if exists "mindex_worship_import_sources_shared_all" on public.mindex_worship_import_sources;
create policy "mindex_worship_import_sources_shared_all"
  on public.mindex_worship_import_sources for all to anon using (true) with check (true);

drop policy if exists "mindex_worship_import_candidates_shared_all" on public.mindex_worship_import_candidates;
create policy "mindex_worship_import_candidates_shared_all"
  on public.mindex_worship_import_candidates for all to anon using (true) with check (true);

drop policy if exists "mindex_worship_import_mappings_shared_all" on public.mindex_worship_import_mappings;
create policy "mindex_worship_import_mappings_shared_all"
  on public.mindex_worship_import_mappings for all to anon using (true) with check (true);

-- Keep service types empty until the user-approved Mindex Worship templates are
-- created. Do not seed PPT-derived service orders here.
