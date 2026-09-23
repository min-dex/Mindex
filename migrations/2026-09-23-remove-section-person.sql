-- Apply after deploying clients that omit section.person.
-- No CASCADE: unexpected dependencies abort the entire transaction.
begin;
set local lock_timeout = '5s';

do $migration$
declare
  view_oid oid := to_regclass('public.mindex_worship_presenter_slides');
  view_definition text;
  view_owner text;
  view_options text[];
  view_comment text;
  view_grants jsonb;
  grant_row jsonb;
  function_definition text;
  allowed_old text := $$array['sort_order','section_key','title','person','template_id','template_modified','source_kind','config','source_ref']$$;
  allowed_new text := $$array['sort_order','section_key','title','template_id','template_modified','source_kind','config','source_ref']$$;
begin
  if not exists (select 1 from information_schema.columns
    where table_schema='public' and table_name='mindex_worship_sections' and column_name='person') then
    raise exception 'Section person column already absent; inspect postconditions before rerunning';
  end if;
  lock table public.mindex_worship_sections in access exclusive mode;
  if exists (select 1 from public.mindex_worship_sections where btrim(person) <> '') then
    raise exception 'Nonempty section assignees exist; stop without discarding data';
  end if;
  if view_oid is null then raise exception 'Expected presenter view missing'; end if;
  select pg_get_viewdef(c.oid, true), pg_get_userbyid(c.relowner), c.reloptions,
    obj_description(c.oid, 'pg_class'),
    (select coalesce(jsonb_agg(jsonb_build_object(
      'role', case when a.grantee=0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end,
      'privilege', a.privilege_type, 'grantable', a.is_grantable)), '[]'::jsonb)
     from aclexplode(coalesce(c.relacl, acldefault('r',c.relowner))) a)
  into view_definition, view_owner, view_options, view_comment, view_grants
  from pg_class c where c.oid=view_oid;
  if view_definition !~ 'sec\.person AS section_person,' then
    raise exception 'Unexpected presenter view definition';
  end if;
  view_definition := replace(view_definition, 'sec.person AS section_person,', '');

  select pg_get_functiondef(to_regprocedure('mindex_atomic.patch_row(text,uuid,jsonb,jsonb)'))
  into function_definition;
  if function_definition is null or strpos(function_definition, allowed_old)=0 then
    raise exception 'Unexpected atomic patch function; review current definition';
  end if;
  execute replace(function_definition, allowed_old, allowed_new);

  drop view public.mindex_worship_presenter_slides;
  alter table public.mindex_worship_sections drop column person;
  execute 'create view public.mindex_worship_presenter_slides'
    || case when cardinality(view_options)>0 then ' with (' || array_to_string(view_options, ',') || ')' else '' end
    || ' as ' || view_definition;
  execute format('alter view public.mindex_worship_presenter_slides owner to %I', view_owner);
  -- Remove default grants first, then restore the exact privilege set.
  for grant_row in
    select jsonb_build_object('role',case when a.grantee=0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end)
    from pg_class c cross join lateral aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) a
    where c.oid='public.mindex_worship_presenter_slides'::regclass
  loop
    execute format('revoke all on public.mindex_worship_presenter_slides from %s',
      case when grant_row->>'role'='PUBLIC' then 'PUBLIC' else quote_ident(grant_row->>'role') end);
  end loop;
  for grant_row in select value from jsonb_array_elements(view_grants) loop
    execute format('grant %s on public.mindex_worship_presenter_slides to %s%s',
      grant_row->>'privilege',
      case when grant_row->>'role'='PUBLIC' then 'PUBLIC' else quote_ident(grant_row->>'role') end,
      case when (grant_row->>'grantable')::boolean then ' with grant option' else '' end);
  end loop;
  if view_comment is not null then
    execute format('comment on view public.mindex_worship_presenter_slides is %L',view_comment);
  end if;
end
$migration$;

notify pgrst, 'reload schema';
commit;

-- Both queries must return zero rows.
select column_name from information_schema.columns
where table_schema='public' and table_name='mindex_worship_sections' and column_name='person';
select column_name from information_schema.columns
where table_schema='public' and table_name='mindex_worship_presenter_slides' and column_name='section_person';
