-- LOCAL TEST PROTOTYPE ONLY. Not a production migration or exposed RPC.
-- Basic creation, existing-row patches and deletion; client cutover remains gated.
create schema mindex_atomic_lab;
revoke all on schema mindex_atomic_lab from public;
alter table public.mindex_worship_services add column save_revision bigint not null default 0;
create table mindex_atomic_lab.receipts (
  service_id uuid not null, request_id uuid not null, digest bytea not null,
  revision bigint not null, primary key(service_id, request_id)
);
create table mindex_atomic_lab.checkpoints (
  service_id uuid primary key, aggregate jsonb not null
);
-- No cascading FK: retry receipts and recovery state must outlive the service.
create table mindex_atomic_lab.tombstones (
  service_id uuid primary key, revision bigint not null
);

create function mindex_atomic_lab.read_service(sid uuid) returns jsonb
language sql stable set search_path = pg_catalog, pg_temp as $$
  select jsonb_build_object(
    'revision', s.save_revision::text,
    'service', to_jsonb(s) - 'save_revision',
    'sections', coalesce((select jsonb_agg(to_jsonb(x) order by x.id)
      from public.mindex_worship_sections x where x.service_id=s.id), '[]'),
    'elements', coalesce((select jsonb_agg(to_jsonb(e) order by e.id)
      from public.mindex_worship_elements e join public.mindex_worship_sections x
      on x.id=e.section_id where x.service_id=s.id), '[]'),
    'slides', coalesce((select jsonb_agg(to_jsonb(v) order by v.id)
      from public.mindex_worship_slides v join public.mindex_worship_elements e
      on e.id=v.element_id join public.mindex_worship_sections x
      on x.id=e.section_id where x.service_id=s.id), '[]')
  ) from public.mindex_worship_services s where s.id=sid
$$;

-- Identifiers are fixed allowlists; values always use bind parameters.
create function mindex_atomic_lab.patch_row(kind text, rid uuid, patch jsonb, remove_keys jsonb default '{}') returns void
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare tab text; allowed text[]; key text; assignments text[] := '{}'; affected int;
  song uuid; version_id uuid; owner_song uuid;
begin
  if jsonb_typeof(patch) is distinct from 'object' then raise exception 'INVALID_PATCH'; end if;
  if jsonb_typeof(remove_keys) is distinct from 'object' then raise exception 'INVALID_REMOVAL'; end if;
  case kind
    when 'service' then
      tab := 'mindex_worship_services';
      allowed := array['title','service_alias','worship_leader','praise_leader','notes','status',
        'service_date','service_type_id','service_date_end','template_id','template_modified','source_kind','source_ref'];
    when 'section' then
      tab := 'mindex_worship_sections';
      allowed := array['sort_order','section_key','title','person','template_id','template_modified','source_kind','config','source_ref'];
    when 'element' then
      tab := 'mindex_worship_elements';
      allowed := array['sort_order','element_type','title','person','body','scripture_reference',
        'asset','input_mode','content_state','template_id','template_modified','source_kind','review_status','config','source_ref',
        'song_id','song_version_id','scripture_id'];
    else raise exception 'INVALID_KIND';
  end case;
  if kind='service' then
    if patch ? 'service_date' and (jsonb_typeof(patch->'service_date') is distinct from 'string'
      or (patch->>'service_date') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
      then raise exception 'INVALID_SERVICE_DATE'; end if;
    -- Documents/history are aggregate-owned, never writable as ordinary metadata.
    if coalesce(patch->'source_ref','{}') ?| array['mindexServiceDocument','mindexServiceDocumentHistory']
      or coalesce(remove_keys->'source_ref','[]') ?| array['mindexServiceDocument','mindexServiceDocumentHistory']
      then raise exception 'PROTECTED_DOCUMENT_FIELD'; end if;
    if patch ? 'service_date_end' and patch->'service_date_end'<>'null'::jsonb then
      if jsonb_typeof(patch->'service_date_end')<>'string'
        or (patch->>'service_date_end') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        then raise exception 'INVALID_END_DATE'; end if;
    end if;
  end if;
  for key in select jsonb_object_keys(patch) union select jsonb_object_keys(remove_keys) loop
    if not key=any(allowed) then raise exception 'UNKNOWN_PATCH_FIELD'; end if;
    if key=any(array['asset','content_state','config','source_ref']) then
      if patch ? key and jsonb_typeof(patch->key) is distinct from 'object' then raise exception 'INVALID_JSON_PATCH'; end if;
      if remove_keys ? key then
        if jsonb_typeof(remove_keys->key) is distinct from 'array' then raise exception 'INVALID_REMOVAL'; end if;
        if exists(select from jsonb_array_elements(remove_keys->key) v where jsonb_typeof(v)<>'string') then raise exception 'INVALID_REMOVAL'; end if;
        if exists(select from jsonb_array_elements_text(remove_keys->key) v where coalesce(patch->key,'{}') ? v)
          then raise exception 'CONFLICTING_REMOVAL'; end if;
      end if;
      assignments := array_append(assignments, format(
        '%I = (t.%I - array(select jsonb_array_elements_text(coalesce($3 -> %L,''[]'')))) || coalesce($2 -> %L,''{}'')',key,key,key,key));
    else
      if remove_keys ? key then raise exception 'INVALID_REMOVAL'; end if;
      assignments := array_append(assignments, format('%I = p.%I',key,key));
    end if;
  end loop;
  if cardinality(assignments)=0 then return; end if;
  execute format('update public.%I t set %s from jsonb_populate_record(null::public.%I,$2) p where t.id=$1',
    tab,array_to_string(assignments,','),tab) using rid,patch,remove_keys;
  get diagnostics affected = row_count;
  if affected<>1 then raise exception 'ROW_NOT_FOUND'; end if;
  if kind='service' and exists(select from public.mindex_worship_services
    where id=rid and service_date_end<service_date) then raise exception 'INVALID_DATE_RANGE'; end if;
  if kind='element' and (patch ? 'song_id' or patch ? 'song_version_id') then
    select song_id,song_version_id into song,version_id from public.mindex_worship_elements where id=rid;
    if version_id is not null then
      select coalesce(v.source_song_id,v.canonical_song_id) into owner_song
        from public.mindex_song_versions v where v.id=version_id for share;
      if song is null or song is distinct from owner_song then raise exception 'SONG_VERSION_MISMATCH'; end if;
    end if;
  end if;
end
$$;

create function mindex_atomic_lab.insert_children(sid uuid, sections jsonb, elements jsonb) returns void
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare item jsonb; rid uuid; parent_id uuid;
begin
  if jsonb_typeof(sections) is distinct from 'array' or jsonb_typeof(elements) is distinct from 'array'
    then raise exception 'INVALID_SHAPE'; end if;
  for item in select value from jsonb_array_elements(sections) loop
    if jsonb_typeof(item) is distinct from 'object' then raise exception 'INVALID_ROW'; end if;
    if exists(select from jsonb_object_keys(item) k where k not in ('id','patch','removeKeys')) then raise exception 'UNKNOWN_ROW_FIELD'; end if;
    rid := (item->>'id')::uuid;
    if rid is null then raise exception 'INVALID_ID'; end if;
    insert into public.mindex_worship_sections(id,service_id,title,created_at,updated_at) values(rid,sid,'',now(),now());
    perform mindex_atomic_lab.patch_row('section',rid,item->'patch',coalesce(item->'removeKeys','{}'));
  end loop;
  for item in select value from jsonb_array_elements(elements) loop
    if jsonb_typeof(item) is distinct from 'object' then raise exception 'INVALID_ROW'; end if;
    if exists(select from jsonb_object_keys(item) k where k not in ('id','sectionId','patch','removeKeys')) then raise exception 'UNKNOWN_ROW_FIELD'; end if;
    rid := (item->>'id')::uuid; parent_id := (item->>'sectionId')::uuid;
    if rid is null then raise exception 'INVALID_ID'; end if;
    if not exists(select from public.mindex_worship_sections where id=parent_id and service_id=sid)
      then raise exception 'SECTION_OWNERSHIP'; end if;
    insert into public.mindex_worship_elements(id,section_id,element_type,created_at,updated_at) values(rid,parent_id,'plain_text',now(),now());
    perform mindex_atomic_lab.patch_row('element',rid,item->'patch',coalesce(item->'removeKeys','{}'));
  end loop;
end
$$;

-- Validate references against the final transaction state, after moves/deletes.
-- Free text and heterogeneous manual slides remain untouched; this is not a parser.
create function mindex_atomic_lab.validate_document(sid uuid, doc jsonb) returns void
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare list_key text; entry jsonb; target jsonb; element_id text; section_id text;
  actual_section uuid; actual_slot text; actual_song uuid; actual_version uuid;
  seen text[]; slide_id text; linked jsonb;
begin
  if jsonb_typeof(doc) is distinct from 'object'
    or jsonb_typeof(doc->'sourceText') is distinct from 'string'
    then raise exception 'INVALID_DOCUMENT'; end if;
  if doc ? 'serviceId' and doc->>'serviceId' is distinct from sid::text
    then raise exception 'DOCUMENT_SERVICE_MISMATCH'; end if;
  if doc ? 'serviceDate' and (doc->>'serviceDate') is distinct from
    (select service_date::text from public.mindex_worship_services where id=sid)
    then raise exception 'DOCUMENT_DATE_MISMATCH'; end if;
  foreach list_key in array array['sourceRecords','slides','exceptions'] loop
    if not doc ? list_key then continue; end if;
    if jsonb_typeof(doc->list_key) is distinct from 'array' then raise exception 'INVALID_DOCUMENT_LIST'; end if;
    seen := '{}';
    for entry in select value from jsonb_array_elements(doc->list_key) loop
      if jsonb_typeof(entry) is distinct from 'object' then raise exception 'INVALID_DOCUMENT_ENTRY'; end if;
      target := case when list_key='exceptions' then coalesce(entry->'target','{}') else entry end;
      if jsonb_typeof(target) is distinct from 'object' then raise exception 'INVALID_DOCUMENT_TARGET'; end if;
      element_id := nullif(target->>'elementId','');
      section_id := nullif(target->>'sectionId','');
      -- The renderer's implicit ready screen has a synthetic group, not a DB section.
      if list_key='slides' and element_id is null and section_id=sid::text||':ready'
        and ((entry->>'id'=sid::text||':ready' and entry->>'type'='ready')
          or (entry->>'id'=sid::text||':ready:after-blank' and entry->>'type'='blank'
            and entry->'autoTrailingBlank'='true'::jsonb)) then
        section_id := null;
      end if;
      if section_id is not null and not exists(select from public.mindex_worship_sections
        where id::text=section_id and service_id=sid) then raise exception 'DOCUMENT_SECTION_OWNERSHIP'; end if;
      if element_id is not null then
        select e.section_id,coalesce(e.source_ref->>'slotKey',e.source_ref->>'slot_key',e.config->>'slotKey',e.config->>'slot_key'),
          e.song_id,e.song_version_id into actual_section,actual_slot,actual_song,actual_version
        from public.mindex_worship_elements e join public.mindex_worship_sections s on s.id=e.section_id
        where e.id::text=element_id and s.service_id=sid;
        if not found then raise exception 'DOCUMENT_ELEMENT_OWNERSHIP'; end if;
        if section_id is not null and section_id<>actual_section::text then raise exception 'DOCUMENT_PARENT_MISMATCH'; end if;
        if nullif(target->>'slotKey','') is not null and nullif(actual_slot,'') is not null
          and target->>'slotKey'<>actual_slot then raise exception 'DOCUMENT_SLOT_MISMATCH'; end if;
        if list_key='sourceRecords' then
          if element_id=any(seen) then raise exception 'DUPLICATE_DOCUMENT_RECORD'; end if;
          seen := array_append(seen,element_id);
          linked := coalesce(entry->'linkedSource','{}');
          if jsonb_typeof(linked) is distinct from 'object' then raise exception 'INVALID_DOCUMENT_LINK'; end if;
          if linked ? 'songId' and linked->>'songId' is distinct from actual_song::text
            then raise exception 'DOCUMENT_SONG_MISMATCH'; end if;
          if linked ? 'songVersionId' and linked->>'songVersionId' is distinct from actual_version::text
            then raise exception 'DOCUMENT_VERSION_MISMATCH'; end if;
        end if;
      end if;
      if list_key='slides' then
        slide_id := entry->>'id';
        if jsonb_typeof(entry->'id') is distinct from 'string' or coalesce(slide_id,'')=''
          then raise exception 'INVALID_DOCUMENT_SLIDE_ID'; end if;
        if slide_id=any(seen) then raise exception 'DUPLICATE_DOCUMENT_SLIDE'; end if;
        seen := array_append(seen,slide_id);
      end if;
    end loop;
  end loop;
end
$$;

create function mindex_atomic_lab.save_existing(req jsonb) returns jsonb
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare sid uuid; v_request_id uuid; revision bigint; digest bytea;
  prior mindex_atomic_lab.receipts%rowtype; item jsonb; rid uuid;
  before_state jsonb; seen uuid[] := '{}'; section_ids uuid[]; element_ids uuid[];
  deleted_sections uuid[] := '{}'; deleted_elements uuid[] := '{}'; moved uuid[] := '{}';
  key text; target uuid;
begin
  if jsonb_typeof(req) is distinct from 'object' or octet_length(req::text)>4194304
    then raise exception 'INVALID_REQUEST'; end if;
  if exists(select from jsonb_object_keys(req) k where k not in
    ('protocolVersion','serviceId','requestId','expectedRevision','metadataPatch','sectionPatches','elementPatches','document',
     'deleteSectionIds','deleteElementIds','elementMoves','newSections','newElements'))
    then raise exception 'UNKNOWN_REQUEST_FIELD'; end if;
  if req->>'protocolVersion' is distinct from '1'
    or jsonb_typeof(req->'expectedRevision') is distinct from 'string'
    or (req->>'expectedRevision') !~ '^(0|[1-9][0-9]*)$'
    then raise exception 'INVALID_PROTOCOL'; end if;
  sid := (req->>'serviceId')::uuid; v_request_id := (req->>'requestId')::uuid;
  if sid is null or v_request_id is null then raise exception 'INVALID_ID'; end if;
  if jsonb_typeof(coalesce(req->'sectionPatches','[]'))<>'array'
    or jsonb_typeof(coalesce(req->'elementPatches','[]'))<>'array'
    or jsonb_typeof(req->'document') is distinct from 'object'
    then raise exception 'INVALID_SHAPE'; end if;
  -- Also serializes retries after deletion, when no root row remains to lock.
  -- Shared dependency gate precedes every service lock. Canonical writers take
  -- its exclusive counterpart before locking canonical rows (separate key space).
  perform pg_advisory_xact_lock_shared(1296649816, 1);
  perform pg_advisory_xact_lock(hashtextextended(sid::text, 0));
  select save_revision into revision from public.mindex_worship_services where id=sid for update;
  digest := sha256(convert_to('save:' || req::text,'UTF8'));
  select * into prior from mindex_atomic_lab.receipts r where r.service_id=sid and r.request_id=v_request_id;
  if found then
    if prior.digest<>digest then raise exception 'REQUEST_ID_REUSED'; end if;
    return jsonb_build_object('replayed',true,'committedRevision',prior.revision::text,
      'aggregate',mindex_atomic_lab.read_service(sid),
      'currentRevision',(select t.revision::text from mindex_atomic_lab.tombstones t where t.service_id=sid),
      'deleted',exists(select from mindex_atomic_lab.tombstones where service_id=sid));
  end if;
  if revision is null then raise exception 'SERVICE_NOT_FOUND'; end if;
  if revision<>(req->>'expectedRevision')::bigint then raise exception 'REVISION_CONFLICT'; end if;
  before_state := mindex_atomic_lab.read_service(sid);
  perform mindex_atomic_lab.insert_children(sid,coalesce(req->'newSections','[]'),coalesce(req->'newElements','[]'));
  select array_agg(id) into section_ids from public.mindex_worship_sections where service_id=sid;
  select array_agg(id) into element_ids from public.mindex_worship_elements where section_id=any(section_ids);
  foreach key in array array['deleteSectionIds','deleteElementIds','elementMoves'] loop
    if jsonb_typeof(coalesce(req->key,'[]')) is distinct from 'array' then raise exception 'INVALID_SHAPE'; end if;
  end loop;
  foreach key in array array['deleteSectionIds','deleteElementIds'] loop
    seen := '{}';
    for item in select value from jsonb_array_elements(coalesce(req->key,'[]')) loop
      if jsonb_typeof(item) is distinct from 'string' then raise exception 'INVALID_ID'; end if;
      rid := (item #>> '{}')::uuid;
      if not coalesce(rid=any(case when key='deleteSectionIds' then section_ids else element_ids end),false)
        then raise exception 'DELETE_OWNERSHIP'; end if;
      if rid=any(seen) then raise exception 'DUPLICATE_ID'; end if;
      seen := array_append(seen,rid);
    end loop;
    if key='deleteSectionIds' then deleted_sections := seen; else deleted_elements := seen; end if;
  end loop;
  for item in select value from jsonb_array_elements(coalesce(req->'elementMoves','[]')) loop
    if jsonb_typeof(item) is distinct from 'object' then raise exception 'INVALID_ROW'; end if;
    if exists(select from jsonb_object_keys(item) k where k not in ('id','sectionId')) then raise exception 'UNKNOWN_ROW_FIELD'; end if;
    rid := (item->>'id')::uuid; target := (item->>'sectionId')::uuid;
    if not coalesce(rid=any(element_ids),false) or not coalesce(target=any(section_ids),false)
      then raise exception 'MOVE_OWNERSHIP'; end if;
    if rid=any(deleted_elements) or target=any(deleted_sections) then raise exception 'CONFLICTING_STRUCTURE'; end if;
    if rid=any(moved) then raise exception 'DUPLICATE_ID'; end if;
    moved := array_append(moved,rid);
  end loop;
  -- A section deletion must name each child to delete or move out, never silently cascade it.
  if exists(select from public.mindex_worship_elements where section_id=any(deleted_sections)
    and not id=any(deleted_elements) and not id=any(moved)) then raise exception 'CHILD_DELETE_INTENT_REQUIRED'; end if;
  seen := '{}';
  for item in select value from jsonb_array_elements(coalesce(req->'sectionPatches','[]')) loop
    rid := (item->>'id')::uuid;
    if rid is null or not coalesce(rid=any(section_ids),false) then raise exception 'SECTION_OWNERSHIP'; end if;
    if rid=any(deleted_sections) then raise exception 'CONFLICTING_STRUCTURE'; end if;
    if rid=any(seen) then raise exception 'DUPLICATE_ID'; end if;
    seen := array_append(seen,rid);
    if exists(select from jsonb_object_keys(item) k where k not in ('id','patch','removeKeys')) then raise exception 'UNKNOWN_ROW_FIELD'; end if;
  end loop;
  seen := '{}';
  for item in select value from jsonb_array_elements(coalesce(req->'elementPatches','[]')) loop
    rid := (item->>'id')::uuid;
    if rid is null or not coalesce(rid=any(element_ids),false) then raise exception 'ELEMENT_OWNERSHIP'; end if;
    if rid=any(deleted_elements) then raise exception 'CONFLICTING_STRUCTURE'; end if;
    if rid=any(seen) then raise exception 'DUPLICATE_ID'; end if;
    seen := array_append(seen,rid);
    if exists(select from jsonb_object_keys(item) k where k not in ('id','patch','removeKeys')) then raise exception 'UNKNOWN_ROW_FIELD'; end if;
  end loop;
  insert into mindex_atomic_lab.checkpoints values(sid,before_state)
    on conflict(service_id) do update set aggregate=excluded.aggregate;
  perform mindex_atomic_lab.patch_row('service',sid,coalesce(req->'metadataPatch','{}'));
  for item in select value from jsonb_array_elements(coalesce(req->'sectionPatches','[]')) loop
    perform mindex_atomic_lab.patch_row('section',(item->>'id')::uuid,item->'patch',coalesce(item->'removeKeys','{}'));
  end loop;
  for item in select value from jsonb_array_elements(coalesce(req->'elementPatches','[]')) loop
    perform mindex_atomic_lab.patch_row('element',(item->>'id')::uuid,item->'patch',coalesce(item->'removeKeys','{}'));
  end loop;
  for item in select value from jsonb_array_elements(coalesce(req->'elementMoves','[]')) loop
    update public.mindex_worship_elements set section_id=(item->>'sectionId')::uuid where id=(item->>'id')::uuid;
  end loop;
  delete from public.mindex_worship_elements where id=any(deleted_elements);
  delete from public.mindex_worship_sections where id=any(deleted_sections);
  perform mindex_atomic_lab.validate_document(sid,req->'document');
  update public.mindex_worship_services set
    source_ref=source_ref || jsonb_build_object('mindexServiceDocument',req->'document'),
    save_revision=save_revision+1 where id=sid returning save_revision into revision;
  insert into mindex_atomic_lab.receipts values(sid,v_request_id,digest,revision);
  return jsonb_build_object('replayed',false,'committedRevision',revision::text,
    'aggregate',mindex_atomic_lab.read_service(sid));
end
$$;

create function mindex_atomic_lab.delete_service(req jsonb) returns jsonb
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare sid uuid; v_request_id uuid; revision bigint; digest bytea;
  prior mindex_atomic_lab.receipts%rowtype;
begin
  if jsonb_typeof(req) is distinct from 'object' or octet_length(req::text)>4096
    then raise exception 'INVALID_REQUEST'; end if;
  if exists(select from jsonb_object_keys(req) k where k not in
    ('protocolVersion','serviceId','requestId','expectedRevision','confirmDelete'))
    then raise exception 'UNKNOWN_REQUEST_FIELD'; end if;
  if req->>'protocolVersion' is distinct from '1'
    or jsonb_typeof(req->'expectedRevision') is distinct from 'string'
    or (req->>'expectedRevision') !~ '^(0|[1-9][0-9]*)$'
    then raise exception 'INVALID_PROTOCOL'; end if;
  if req->'confirmDelete' is distinct from 'true'::jsonb then raise exception 'DELETE_INTENT_REQUIRED'; end if;
  sid := (req->>'serviceId')::uuid; v_request_id := (req->>'requestId')::uuid;
  if sid is null or v_request_id is null then raise exception 'INVALID_ID'; end if;
  perform pg_advisory_xact_lock_shared(1296649816, 1);
  perform pg_advisory_xact_lock(hashtextextended(sid::text, 0));
  select save_revision into revision from public.mindex_worship_services where id=sid for update;
  digest := sha256(convert_to('delete:' || req::text,'UTF8'));
  select * into prior from mindex_atomic_lab.receipts r where r.service_id=sid and r.request_id=v_request_id;
  if found then
    if prior.digest<>digest then raise exception 'REQUEST_ID_REUSED'; end if;
    return jsonb_build_object('replayed',true,'committedRevision',prior.revision::text,
      'aggregate',mindex_atomic_lab.read_service(sid),
      'currentRevision',(select t.revision::text from mindex_atomic_lab.tombstones t where t.service_id=sid),
      'deleted',exists(select from mindex_atomic_lab.tombstones where service_id=sid));
  end if;
  if revision is null then raise exception 'SERVICE_NOT_FOUND'; end if;
  if revision<>(req->>'expectedRevision')::bigint then raise exception 'REVISION_CONFLICT'; end if;
  insert into mindex_atomic_lab.checkpoints values(sid,mindex_atomic_lab.read_service(sid))
    on conflict(service_id) do update set aggregate=excluded.aggregate;
  delete from public.mindex_worship_services where id=sid;
  revision := revision+1;
  insert into mindex_atomic_lab.tombstones values(sid,revision);
  insert into mindex_atomic_lab.receipts values(sid,v_request_id,digest,revision);
  return jsonb_build_object('replayed',false,'committedRevision',revision::text,'currentRevision',revision::text,'aggregate',null,'deleted',true);
end
$$;
create function mindex_atomic_lab.create_service(req jsonb) returns jsonb
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare sid uuid; v_request_id uuid; digest bytea; prior mindex_atomic_lab.receipts%rowtype;
begin
  if jsonb_typeof(req) is distinct from 'object' or octet_length(req::text)>4194304
    then raise exception 'INVALID_REQUEST'; end if;
  if exists(select from jsonb_object_keys(req) k where k not in
    ('protocolVersion','serviceId','requestId','serviceTypeId','serviceDate','metadataPatch','sections','elements','document'))
    then raise exception 'UNKNOWN_REQUEST_FIELD'; end if;
  if req->>'protocolVersion' is distinct from '1' then raise exception 'INVALID_PROTOCOL'; end if;
  if coalesce(req->'metadataPatch','{}') ?| array['service_date','service_type_id']
    then raise exception 'DUPLICATE_CREATE_IDENTITY'; end if;
  sid := (req->>'serviceId')::uuid; v_request_id := (req->>'requestId')::uuid;
  if sid is null or v_request_id is null then raise exception 'INVALID_ID'; end if;
  if jsonb_typeof(req->'sections') is distinct from 'array'
    or jsonb_typeof(req->'elements') is distinct from 'array'
    or jsonb_typeof(req->'document') is distinct from 'object'
    or jsonb_typeof(req->'serviceTypeId') is distinct from 'string'
    or jsonb_typeof(req->'serviceDate') is distinct from 'string'
    or (req->>'serviceDate') !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    then raise exception 'INVALID_SHAPE'; end if;
  perform pg_advisory_xact_lock_shared(1296649816, 1);
  perform pg_advisory_xact_lock(hashtextextended(sid::text, 0));
  digest := sha256(convert_to('create:' || req::text,'UTF8'));
  select * into prior from mindex_atomic_lab.receipts r where r.service_id=sid and r.request_id=v_request_id;
  if found then
    if prior.digest<>digest then raise exception 'REQUEST_ID_REUSED'; end if;
    return jsonb_build_object('replayed',true,'committedRevision',prior.revision::text,
      'aggregate',mindex_atomic_lab.read_service(sid),
      'currentRevision',(select t.revision::text from mindex_atomic_lab.tombstones t where t.service_id=sid),
      'deleted',exists(select from mindex_atomic_lab.tombstones where service_id=sid));
  end if;
  if exists(select from mindex_atomic_lab.tombstones where service_id=sid)
    then raise exception 'SERVICE_DELETED'; end if;
  if exists(select from public.mindex_worship_services where id=sid)
    then raise exception 'SERVICE_ALREADY_EXISTS'; end if;
  -- Apply the final title at insertion so the business-identity index sees it.
  insert into public.mindex_worship_services(id,service_type_id,service_date,service_date_end,title,created_at,updated_at)
    values(sid,req->>'serviceTypeId',(req->>'serviceDate')::date,
      (req->'metadataPatch'->>'service_date_end')::date,coalesce(req->'metadataPatch'->>'title',''),now(),now());
  perform mindex_atomic_lab.patch_row('service',sid,coalesce(req->'metadataPatch','{}'));
  perform mindex_atomic_lab.insert_children(sid,req->'sections',req->'elements');
  perform mindex_atomic_lab.validate_document(sid,req->'document');
  update public.mindex_worship_services set source_ref=source_ref || jsonb_build_object('mindexServiceDocument',req->'document'),
    save_revision=1 where id=sid;
  insert into mindex_atomic_lab.receipts values(sid,v_request_id,digest,1);
  return jsonb_build_object('replayed',false,'committedRevision','1','aggregate',mindex_atomic_lab.read_service(sid));
end
$$;
revoke all on all functions in schema mindex_atomic_lab from public;
revoke all on all tables in schema mindex_atomic_lab from public;
