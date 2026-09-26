-- Register nursery worship as a first-class ministry service.  The app aliases
-- legacy kindergarten IDs to this canonical ID when reading existing records.
insert into public.mindex_worship_service_types (
  id,
  display_name,
  short_name,
  group_key,
  sort_order,
  default_output_context,
  chromakey_enabled,
  config
)
values (
  'nursery',
  '유치부 예배',
  '유치부 예배',
  'ministry',
  10,
  'fullscreen',
  false,
  '{"legacy_name":"nursery","legacy_service_type_id":"nursery","autoScheduleEnabled":true}'::jsonb
)
on conflict (id) do update
set
  display_name = excluded.display_name,
  short_name = excluded.short_name,
  group_key = excluded.group_key,
  default_output_context = excluded.default_output_context,
  chromakey_enabled = excluded.chromakey_enabled,
  config = public.mindex_worship_service_types.config || excluded.config;
