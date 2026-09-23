-- Mindex admin-link security hardening.
--
-- Run this only after Supabase Auth is configured and the app is opened with
-- auth=required or window.MINDEX_SUPABASE.authRequired = true.
--
-- Model:
-- - anon can read shared Mindex data needed for public/static loading.
-- - authenticated users can write administrator-managed tables.
-- - service-role/server imports continue to bypass RLS as usual.

do $$
declare
  editable_tables text[] := array[
    'mindex_songs',
    'mindex_canonical_songs',
    'mindex_song_versions',
    'mindex_version_units',
    'mindex_song_relations',
    'mindex_scriptures',
    'mindex_reference_links',
    'mindex_sunday_calendar',
    'mindex_worship_service_types',
    'mindex_worship_templates',
    'mindex_worship_template_items',
    'mindex_worship_services',
    'mindex_bulletins',
    'mindex_worship_sections',
    'mindex_worship_elements',
    'mindex_worship_slides',
    'mindex_worship_import_sources',
    'mindex_worship_import_candidates',
    'mindex_worship_import_mappings',
    'mindex_activity_events',
    'mindex_activity_games',
    'mindex_activity_teams',
    'mindex_activity_score_events',
    'mindex_activity_puzzle_boards',
    'mindex_activity_puzzle_pieces',
    'mindex_activity_quiz_questions',
    'mindex_activity_quiz_choices',
    'mindex_activity_physical_games'
  ];
  readonly_tables text[] := array[
    'mindex_scripture_books',
    'mindex_bible_translations',
    'mindex_bible_verses'
  ];
  readonly_views text[] := array[
    'mindex_worship_presenter_slides'
  ];
  table_name text;
begin
  foreach table_name in array editable_tables loop
    if to_regclass(format('public.%I', table_name)) is null then
      continue;
    end if;

    execute format('alter table public.%I enable row level security', table_name);
    execute format('grant select on public.%I to anon, authenticated', table_name);
    execute format('revoke insert, update, delete on public.%I from anon', table_name);
    execute format('grant insert, update, delete on public.%I to authenticated', table_name);

    execute format('drop policy if exists "%s_shared_read" on public.%I', table_name, table_name);
    execute format('drop policy if exists "%s_shared_insert" on public.%I', table_name, table_name);
    execute format('drop policy if exists "%s_shared_update" on public.%I', table_name, table_name);
    execute format('drop policy if exists "%s_shared_delete" on public.%I', table_name, table_name);
    execute format('drop policy if exists "%s_shared_all" on public.%I', table_name, table_name);

    execute format('drop policy if exists "%s_admin_read" on public.%I', table_name, table_name);
    execute format('create policy "%s_admin_read" on public.%I for select to anon, authenticated using (true)', table_name, table_name);
    execute format('drop policy if exists "%s_admin_insert" on public.%I', table_name, table_name);
    execute format('create policy "%s_admin_insert" on public.%I for insert to authenticated with check (true)', table_name, table_name);
    execute format('drop policy if exists "%s_admin_update" on public.%I', table_name, table_name);
    execute format('create policy "%s_admin_update" on public.%I for update to authenticated using (true) with check (true)', table_name, table_name);
    execute format('drop policy if exists "%s_admin_delete" on public.%I', table_name, table_name);
    execute format('create policy "%s_admin_delete" on public.%I for delete to authenticated using (true)', table_name, table_name);
  end loop;

  foreach table_name in array readonly_tables loop
    if to_regclass(format('public.%I', table_name)) is null then
      continue;
    end if;

    execute format('alter table public.%I enable row level security', table_name);
    execute format('grant select on public.%I to anon, authenticated', table_name);
    execute format('revoke insert, update, delete on public.%I from anon, authenticated', table_name);
    execute format('drop policy if exists "%s_shared_read" on public.%I', table_name, table_name);
    execute format('drop policy if exists "%s_shared_insert" on public.%I', table_name, table_name);
    execute format('drop policy if exists "%s_shared_update" on public.%I', table_name, table_name);
    execute format('drop policy if exists "%s_shared_delete" on public.%I', table_name, table_name);
    execute format('drop policy if exists "%s_shared_all" on public.%I', table_name, table_name);
    execute format('drop policy if exists "%s_admin_read" on public.%I', table_name, table_name);
    execute format('create policy "%s_admin_read" on public.%I for select to anon, authenticated using (true)', table_name, table_name);
  end loop;

  foreach table_name in array readonly_views loop
    if to_regclass(format('public.%I', table_name)) is null then
      continue;
    end if;

    execute format('grant select on public.%I to anon, authenticated', table_name);
  end loop;
end $$;
