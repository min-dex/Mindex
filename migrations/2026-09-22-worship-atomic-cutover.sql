-- Atomic worship persistence cutover.
-- Apply only after the additive migration, RPC smoke tests, compatible client
-- deployment, and confirmation that no worship editor is actively saving.
begin;

do $preflight$
declare
  relation_name text;
  function_name text;
begin
  if to_regnamespace('mindex_atomic') is null then
    raise exception 'ATOMIC_SCHEMA_MISSING';
  end if;
  if not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'mindex_worship_services'
      and column_name = 'save_revision'
  ) then
    raise exception 'ATOMIC_REVISION_MISSING';
  end if;

  foreach relation_name in array array[
    'mindex_worship_services',
    'mindex_worship_sections',
    'mindex_worship_elements',
    'mindex_worship_slides'
  ] loop
    if to_regclass(format('public.%I', relation_name)) is null then
      raise exception 'ATOMIC_RELATION_MISSING:%', relation_name;
    end if;
  end loop;

  foreach function_name in array array[
    'get_worship_service_v1',
    'save_worship_service_v1',
    'create_worship_service_v1',
    'delete_worship_service_v1'
  ] loop
    if to_regprocedure(format('public.%I(%s)', function_name,
      case when function_name = 'get_worship_service_v1' then 'uuid' else 'jsonb' end)) is null then
      raise exception 'ATOMIC_RPC_MISSING:%', function_name;
    end if;
  end loop;
end
$preflight$;

do $cutover$
declare
  relation_name text;
begin
  foreach relation_name in array array[
    'mindex_worship_services',
    'mindex_worship_sections',
    'mindex_worship_elements',
    'mindex_worship_slides'
  ] loop
    execute format('revoke insert, update, delete on public.%I from public, anon, authenticated', relation_name);
    execute format('grant select on public.%I to anon, authenticated', relation_name);
  end loop;
end
$cutover$;

revoke all on function public.get_worship_service_v1(uuid),
  public.save_worship_service_v1(jsonb),
  public.create_worship_service_v1(jsonb),
  public.delete_worship_service_v1(jsonb) from public;
grant execute on function public.get_worship_service_v1(uuid),
  public.save_worship_service_v1(jsonb),
  public.create_worship_service_v1(jsonb),
  public.delete_worship_service_v1(jsonb) to anon, authenticated;

notify pgrst, 'reload schema';

commit;
