-- DISPOSABLE TEST ONLY. Private operator recovery, not an exposed browser RPC.
-- Restore only a server checkpoint, never caller-supplied rows or a revision rewind.
create function mindex_atomic_lab.restore_checkpoint(req jsonb) returns jsonb
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare sid uuid; v_request_id uuid; revision bigint; digest bytea;
  prior mindex_atomic_lab.receipts%rowtype; saved jsonb; before_state jsonb;
  root public.mindex_worship_services%rowtype; item record;
begin
  if jsonb_typeof(req) is distinct from 'object' or octet_length(req::text)>4096
    then raise exception 'INVALID_REQUEST'; end if;
  if exists(select from jsonb_object_keys(req) k where k not in
    ('protocolVersion','serviceId','requestId','expectedRevision','checkpointRevision','confirmRestore'))
    then raise exception 'UNKNOWN_REQUEST_FIELD'; end if;
  if req->>'protocolVersion' is distinct from '1'
    or jsonb_typeof(req->'expectedRevision') is distinct from 'string'
    or (req->>'expectedRevision') !~ '^(0|[1-9][0-9]*)$'
    or jsonb_typeof(req->'checkpointRevision') is distinct from 'string'
    or (req->>'checkpointRevision') !~ '^(0|[1-9][0-9]*)$'
    then raise exception 'INVALID_PROTOCOL'; end if;
  if req->'confirmRestore' is distinct from 'true'::jsonb then raise exception 'RESTORE_INTENT_REQUIRED'; end if;
  sid := (req->>'serviceId')::uuid; v_request_id := (req->>'requestId')::uuid;
  if sid is null or v_request_id is null then raise exception 'INVALID_ID'; end if;
  perform pg_advisory_xact_lock_shared(1296649816, 1);
  perform pg_advisory_xact_lock(hashtextextended(sid::text, 0));
  select save_revision into revision from public.mindex_worship_services where id=sid for update;
  digest := sha256(convert_to('restore:' || req::text,'UTF8'));
  select * into prior from mindex_atomic_lab.receipts r where r.service_id=sid and r.request_id=v_request_id;
  if found then
    if prior.digest<>digest then raise exception 'REQUEST_ID_REUSED'; end if;
    return jsonb_build_object('replayed',true,'committedRevision',prior.revision::text,
      'aggregate',mindex_atomic_lab.read_service(sid),
      'currentRevision',(select t.revision::text from mindex_atomic_lab.tombstones t where t.service_id=sid),
      'deleted',exists(select from mindex_atomic_lab.tombstones where service_id=sid));
  end if;
  if revision is null then
    select t.revision into revision from mindex_atomic_lab.tombstones t where t.service_id=sid for update;
  end if;
  if revision is null then raise exception 'SERVICE_NOT_FOUND'; end if;
  if revision<>(req->>'expectedRevision')::bigint then raise exception 'REVISION_CONFLICT'; end if;
  select aggregate into saved from mindex_atomic_lab.checkpoints where service_id=sid for update;
  if saved is null then raise exception 'CHECKPOINT_NOT_FOUND'; end if;
  if saved->>'revision' is distinct from req->>'checkpointRevision' then raise exception 'CHECKPOINT_CHANGED'; end if;
  if saved->'service'->>'id' is distinct from sid::text then raise exception 'CHECKPOINT_OWNERSHIP'; end if;
  before_state := mindex_atomic_lab.read_service(sid);
  select * into root from jsonb_populate_record(null::public.mindex_worship_services,saved->'service');
  if exists(select from jsonb_array_elements(saved->'sections') s where s->>'service_id' is distinct from sid::text)
    or exists(select from jsonb_array_elements(saved->'elements') e where not exists
      (select from jsonb_array_elements(saved->'sections') s where s->>'id'=e->>'section_id'))
    or exists(select from jsonb_array_elements(saved->'slides') v where not exists
      (select from jsonb_array_elements(saved->'elements') e where e->>'id'=v->>'element_id'))
    then raise exception 'CHECKPOINT_OWNERSHIP'; end if;

  if before_state is null then
    root.save_revision := revision+1;
    root.updated_at := now();
    insert into public.mindex_worship_services select (root).*;
  else
    update public.mindex_worship_services set
      service_type_id=root.service_type_id, service_date=root.service_date,
      service_date_end=root.service_date_end, title=root.title, service_alias=root.service_alias,
      status=root.status, worship_leader=root.worship_leader, praise_leader=root.praise_leader,
      template_id=root.template_id, template_modified=root.template_modified,
      source_kind=root.source_kind, source_ref=root.source_ref, notes=root.notes,
      save_revision=revision+1, updated_at=now() where id=sid;
  end if;
  -- UUID conflicts with another service reject the entire transaction. No upsert/reparenting.
  delete from public.mindex_worship_sections where service_id=sid;
  insert into public.mindex_worship_sections select * from jsonb_populate_recordset(
    null::public.mindex_worship_sections,saved->'sections');
  insert into public.mindex_worship_elements select * from jsonb_populate_recordset(
    null::public.mindex_worship_elements,saved->'elements');
  insert into public.mindex_worship_slides select * from jsonb_populate_recordset(
    null::public.mindex_worship_slides,saved->'slides');
  -- Existence FKs are not enough: a surviving version may now belong to another song.
  for item in select e.id,e.song_id,e.song_version_id from public.mindex_worship_elements e
    join public.mindex_worship_sections s on s.id=e.section_id where s.service_id=sid loop
    perform mindex_atomic_lab.patch_row('element',item.id,
      jsonb_build_object('song_id',item.song_id,'song_version_id',item.song_version_id));
  end loop;
  perform mindex_atomic_lab.validate_document(sid,coalesce(root.source_ref->'mindexServiceDocument','{}'));
  if before_state is not null then
    update mindex_atomic_lab.checkpoints set aggregate=before_state where service_id=sid;
  end if;
  delete from mindex_atomic_lab.tombstones where service_id=sid;
  insert into mindex_atomic_lab.receipts values(sid,v_request_id,digest,revision+1);
  return jsonb_build_object('replayed',false,'committedRevision',(revision+1)::text,
    'aggregate',mindex_atomic_lab.read_service(sid));
end
$$;
revoke all on function mindex_atomic_lab.restore_checkpoint(jsonb) from public;
