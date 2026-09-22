-- Atomic worship persistence, additive installation.
-- This migration installs revisioned RPCs and private recovery state without
-- revoking legacy table writes. Do not enable the client protocol until this
-- migration and the production preflight have both succeeded.
begin;

create schema mindex_atomic;
revoke all on schema mindex_atomic from public;
alter table public.mindex_worship_services add column if not exists save_revision bigint not null default 0;
create table mindex_atomic.receipts (
  service_id uuid not null, request_id uuid not null, digest bytea not null,
  revision bigint not null, primary key(service_id, request_id)
);
create table mindex_atomic.checkpoints (
  service_id uuid primary key, aggregate jsonb not null
);
-- No cascading FK: retry receipts and recovery state must outlive the service.
create table mindex_atomic.tombstones (
  service_id uuid primary key, revision bigint not null
);

create function mindex_atomic.read_service(sid uuid) returns jsonb
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
create function mindex_atomic.patch_row(kind text, rid uuid, patch jsonb, remove_keys jsonb default '{}') returns void
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

create function mindex_atomic.insert_children(sid uuid, sections jsonb, elements jsonb) returns void
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
    perform mindex_atomic.patch_row('section',rid,item->'patch',coalesce(item->'removeKeys','{}'));
  end loop;
  for item in select value from jsonb_array_elements(elements) loop
    if jsonb_typeof(item) is distinct from 'object' then raise exception 'INVALID_ROW'; end if;
    if exists(select from jsonb_object_keys(item) k where k not in ('id','sectionId','patch','removeKeys')) then raise exception 'UNKNOWN_ROW_FIELD'; end if;
    rid := (item->>'id')::uuid; parent_id := (item->>'sectionId')::uuid;
    if rid is null then raise exception 'INVALID_ID'; end if;
    if not exists(select from public.mindex_worship_sections where id=parent_id and service_id=sid)
      then raise exception 'SECTION_OWNERSHIP'; end if;
    insert into public.mindex_worship_elements(id,section_id,element_type,created_at,updated_at) values(rid,parent_id,'plain_text',now(),now());
    perform mindex_atomic.patch_row('element',rid,item->'patch',coalesce(item->'removeKeys','{}'));
  end loop;
end
$$;

-- Validate references against the final transaction state, after moves/deletes.
-- Free text and heterogeneous manual slides remain untouched; this is not a parser.
create function mindex_atomic.validate_document(sid uuid, doc jsonb) returns void
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

create function mindex_atomic.save_existing(req jsonb) returns jsonb
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare sid uuid; v_request_id uuid; revision bigint; digest bytea;
  prior mindex_atomic.receipts%rowtype; item jsonb; rid uuid;
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
  select * into prior from mindex_atomic.receipts r where r.service_id=sid and r.request_id=v_request_id;
  if found then
    if prior.digest<>digest then raise exception 'REQUEST_ID_REUSED'; end if;
    return jsonb_build_object('replayed',true,'committedRevision',prior.revision::text,
      'aggregate',mindex_atomic.read_service(sid),
      'currentRevision',(select t.revision::text from mindex_atomic.tombstones t where t.service_id=sid),
      'deleted',exists(select from mindex_atomic.tombstones where service_id=sid));
  end if;
  if revision is null then raise exception 'SERVICE_NOT_FOUND'; end if;
  if revision<>(req->>'expectedRevision')::bigint then raise exception 'REVISION_CONFLICT'; end if;
  before_state := mindex_atomic.read_service(sid);
  perform mindex_atomic.insert_children(sid,coalesce(req->'newSections','[]'),coalesce(req->'newElements','[]'));
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
  insert into mindex_atomic.checkpoints values(sid,before_state)
    on conflict(service_id) do update set aggregate=excluded.aggregate;
  perform mindex_atomic.patch_row('service',sid,coalesce(req->'metadataPatch','{}'));
  for item in select value from jsonb_array_elements(coalesce(req->'sectionPatches','[]')) loop
    perform mindex_atomic.patch_row('section',(item->>'id')::uuid,item->'patch',coalesce(item->'removeKeys','{}'));
  end loop;
  for item in select value from jsonb_array_elements(coalesce(req->'elementPatches','[]')) loop
    perform mindex_atomic.patch_row('element',(item->>'id')::uuid,item->'patch',coalesce(item->'removeKeys','{}'));
  end loop;
  for item in select value from jsonb_array_elements(coalesce(req->'elementMoves','[]')) loop
    update public.mindex_worship_elements set section_id=(item->>'sectionId')::uuid where id=(item->>'id')::uuid;
  end loop;
  delete from public.mindex_worship_elements where id=any(deleted_elements);
  delete from public.mindex_worship_sections where id=any(deleted_sections);
  perform mindex_atomic.validate_document(sid,req->'document');
  update public.mindex_worship_services set
    source_ref=source_ref || jsonb_build_object('mindexServiceDocument',req->'document'),
    save_revision=save_revision+1 where id=sid returning save_revision into revision;
  insert into mindex_atomic.receipts values(sid,v_request_id,digest,revision);
  return jsonb_build_object('replayed',false,'committedRevision',revision::text,
    'aggregate',mindex_atomic.read_service(sid));
end
$$;

create function mindex_atomic.delete_service(req jsonb) returns jsonb
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare sid uuid; v_request_id uuid; revision bigint; digest bytea;
  prior mindex_atomic.receipts%rowtype;
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
  select * into prior from mindex_atomic.receipts r where r.service_id=sid and r.request_id=v_request_id;
  if found then
    if prior.digest<>digest then raise exception 'REQUEST_ID_REUSED'; end if;
    return jsonb_build_object('replayed',true,'committedRevision',prior.revision::text,
      'aggregate',mindex_atomic.read_service(sid),
      'currentRevision',(select t.revision::text from mindex_atomic.tombstones t where t.service_id=sid),
      'deleted',exists(select from mindex_atomic.tombstones where service_id=sid));
  end if;
  if revision is null then raise exception 'SERVICE_NOT_FOUND'; end if;
  if revision<>(req->>'expectedRevision')::bigint then raise exception 'REVISION_CONFLICT'; end if;
  insert into mindex_atomic.checkpoints values(sid,mindex_atomic.read_service(sid))
    on conflict(service_id) do update set aggregate=excluded.aggregate;
  delete from public.mindex_worship_services where id=sid;
  revision := revision+1;
  insert into mindex_atomic.tombstones values(sid,revision);
  insert into mindex_atomic.receipts values(sid,v_request_id,digest,revision);
  return jsonb_build_object('replayed',false,'committedRevision',revision::text,'currentRevision',revision::text,'aggregate',null,'deleted',true);
end
$$;
create function mindex_atomic.create_service(req jsonb) returns jsonb
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare sid uuid; v_request_id uuid; digest bytea; prior mindex_atomic.receipts%rowtype;
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
  select * into prior from mindex_atomic.receipts r where r.service_id=sid and r.request_id=v_request_id;
  if found then
    if prior.digest<>digest then raise exception 'REQUEST_ID_REUSED'; end if;
    return jsonb_build_object('replayed',true,'committedRevision',prior.revision::text,
      'aggregate',mindex_atomic.read_service(sid),
      'currentRevision',(select t.revision::text from mindex_atomic.tombstones t where t.service_id=sid),
      'deleted',exists(select from mindex_atomic.tombstones where service_id=sid));
  end if;
  if exists(select from mindex_atomic.tombstones where service_id=sid)
    then raise exception 'SERVICE_DELETED'; end if;
  if exists(select from public.mindex_worship_services where id=sid)
    then raise exception 'SERVICE_ALREADY_EXISTS'; end if;
  -- Apply the final title at insertion so the business-identity index sees it.
  insert into public.mindex_worship_services(id,service_type_id,service_date,service_date_end,title,created_at,updated_at)
    values(sid,req->>'serviceTypeId',(req->>'serviceDate')::date,
      (req->'metadataPatch'->>'service_date_end')::date,coalesce(req->'metadataPatch'->>'title',''),now(),now());
  perform mindex_atomic.patch_row('service',sid,coalesce(req->'metadataPatch','{}'));
  perform mindex_atomic.insert_children(sid,req->'sections',req->'elements');
  perform mindex_atomic.validate_document(sid,req->'document');
  update public.mindex_worship_services set source_ref=source_ref || jsonb_build_object('mindexServiceDocument',req->'document'),
    save_revision=1 where id=sid;
  insert into mindex_atomic.receipts values(sid,v_request_id,digest,1);
  return jsonb_build_object('replayed',false,'committedRevision','1','aggregate',mindex_atomic.read_service(sid));
end
$$;
revoke all on all functions in schema mindex_atomic from public;
revoke all on all tables in schema mindex_atomic from public;


do $role$
begin
  if not exists (select 1 from pg_roles where rolname = 'mindex_atomic_writer') then
    create role mindex_atomic_writer nologin noinherit nosuperuser nobypassrls;
  end if;
end
$role$;
-- Supabase's dashboard `postgres` role is intentionally not a superuser. Grant
-- temporary SET membership only for the ownership transfers in this transaction.
grant mindex_atomic_writer to postgres;
grant usage on schema public, mindex_atomic to mindex_atomic_writer;
grant create on schema public, mindex_atomic to mindex_atomic_writer;
grant select, insert, update, delete on all tables in schema mindex_atomic to mindex_atomic_writer;
grant execute on all functions in schema mindex_atomic to mindex_atomic_writer;
grant select on public.mindex_song_versions to mindex_atomic_writer;
-- patch_row locks the referenced version with FOR SHARE.
grant update(id) on public.mindex_song_versions to mindex_atomic_writer;
-- Canonical tables also use RLS in production; table grants alone are not enough.
alter table public.mindex_song_versions enable row level security;
create policy atomic_version_reference on public.mindex_song_versions
  for select to mindex_atomic_writer using (true);
-- FOR SHARE also applies UPDATE USING under RLS. No row mutation is needed.
create policy atomic_version_lock on public.mindex_song_versions
  for update to mindex_atomic_writer using (true) with check (false);

do $$
declare tab text;
begin
  foreach tab in array array['mindex_worship_services','mindex_worship_sections',
    'mindex_worship_elements','mindex_worship_slides'] loop
    execute format('alter table public.%I enable row level security',tab);
    execute format('grant select, insert, update, delete on public.%I to mindex_atomic_writer',tab);
    execute format('drop policy if exists atomic_write on public.%I',tab);
    execute format('create policy atomic_write on public.%I to mindex_atomic_writer using (true) with check (true)',tab);
  end loop;
end $$;

create function public.get_worship_service_v1(sid uuid) returns jsonb
language sql stable security definer set search_path = pg_catalog, pg_temp
as $$ select mindex_atomic.read_service(sid) $$;
create function public.save_worship_service_v1(req jsonb) returns jsonb
language sql security definer set search_path = pg_catalog, pg_temp
as $$ select mindex_atomic.save_existing(req) $$;
create function public.create_worship_service_v1(req jsonb) returns jsonb
language sql security definer set search_path = pg_catalog, pg_temp
as $$ select mindex_atomic.create_service(req) $$;
create function public.delete_worship_service_v1(req jsonb) returns jsonb
language sql security definer set search_path = pg_catalog, pg_temp
as $$ select mindex_atomic.delete_service(req) $$;

alter function public.get_worship_service_v1(uuid) owner to mindex_atomic_writer;
alter function public.save_worship_service_v1(jsonb) owner to mindex_atomic_writer;
alter function public.create_worship_service_v1(jsonb) owner to mindex_atomic_writer;
alter function public.delete_worship_service_v1(jsonb) owner to mindex_atomic_writer;
revoke all on function public.get_worship_service_v1(uuid), public.save_worship_service_v1(jsonb),
  public.create_worship_service_v1(jsonb), public.delete_worship_service_v1(jsonb) from public;
grant execute on function public.get_worship_service_v1(uuid), public.save_worship_service_v1(jsonb),
  public.create_worship_service_v1(jsonb), public.delete_worship_service_v1(jsonb) to anon, authenticated;


create function mindex_atomic.restore_checkpoint(req jsonb) returns jsonb
language plpgsql set search_path = pg_catalog, pg_temp as $$
declare sid uuid; v_request_id uuid; revision bigint; digest bytea;
  prior mindex_atomic.receipts%rowtype; saved jsonb; before_state jsonb;
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
  select * into prior from mindex_atomic.receipts r where r.service_id=sid and r.request_id=v_request_id;
  if found then
    if prior.digest<>digest then raise exception 'REQUEST_ID_REUSED'; end if;
    return jsonb_build_object('replayed',true,'committedRevision',prior.revision::text,
      'aggregate',mindex_atomic.read_service(sid),
      'currentRevision',(select t.revision::text from mindex_atomic.tombstones t where t.service_id=sid),
      'deleted',exists(select from mindex_atomic.tombstones where service_id=sid));
  end if;
  if revision is null then
    select t.revision into revision from mindex_atomic.tombstones t where t.service_id=sid for update;
  end if;
  if revision is null then raise exception 'SERVICE_NOT_FOUND'; end if;
  if revision<>(req->>'expectedRevision')::bigint then raise exception 'REVISION_CONFLICT'; end if;
  select aggregate into saved from mindex_atomic.checkpoints where service_id=sid for update;
  if saved is null then raise exception 'CHECKPOINT_NOT_FOUND'; end if;
  if saved->>'revision' is distinct from req->>'checkpointRevision' then raise exception 'CHECKPOINT_CHANGED'; end if;
  if saved->'service'->>'id' is distinct from sid::text then raise exception 'CHECKPOINT_OWNERSHIP'; end if;
  before_state := mindex_atomic.read_service(sid);
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
    perform mindex_atomic.patch_row('element',item.id,
      jsonb_build_object('song_id',item.song_id,'song_version_id',item.song_version_id));
  end loop;
  perform mindex_atomic.validate_document(sid,coalesce(root.source_ref->'mindexServiceDocument','{}'));
  if before_state is not null then
    update mindex_atomic.checkpoints set aggregate=before_state where service_id=sid;
  end if;
  delete from mindex_atomic.tombstones where service_id=sid;
  insert into mindex_atomic.receipts values(sid,v_request_id,digest,revision+1);
  return jsonb_build_object('replayed',false,'committedRevision',(revision+1)::text,
    'aggregate',mindex_atomic.read_service(sid));
end
$$;
revoke all on function mindex_atomic.restore_checkpoint(jsonb) from public;


create table mindex_atomic.canonical_invalidations (
  service_id uuid primary key references public.mindex_worship_services(id) on delete cascade,
  last_xid xid8 not null
);
revoke all on mindex_atomic.canonical_invalidations from public, anon, authenticated;
grant select, insert, update, delete on mindex_atomic.canonical_invalidations to mindex_atomic_writer;
grant select on public.mindex_songs, public.mindex_canonical_songs,
  public.mindex_version_units, public.mindex_scriptures, public.mindex_worship_templates to mindex_atomic_writer;

create function mindex_atomic.canonical_write_gate() returns trigger
language plpgsql security definer set search_path = pg_catalog, pg_temp as $$
begin
  -- Before-statement ordering avoids holding a canonical row while waiting for
  -- a save that has already locked its service and needs that canonical row.
  perform pg_advisory_xact_lock(1296649816, 1);
  return null;
end $$;

create function mindex_atomic.canonical_changed() returns trigger
language plpgsql security definer set search_path = pg_catalog, pg_temp as $$
declare prev jsonb; next jsonb; ids uuid[]; version_ids uuid[]; services uuid[];
  sid uuid; xid xid8 := pg_current_xact_id(); touched int;
begin
  if tg_op='UPDATE' and to_jsonb(old)=to_jsonb(new) then return new; end if;
  if tg_op<>'INSERT' then prev := to_jsonb(old); end if;
  if tg_op<>'DELETE' then next := to_jsonb(new); end if;
  ids := array_remove(array[(prev->>'id')::uuid,(next->>'id')::uuid],null);
  if tg_table_name='mindex_version_units' then
    version_ids := array_remove(array[(prev->>'version_id')::uuid,(next->>'version_id')::uuid],null);
  elsif tg_table_name='mindex_song_versions' then
    version_ids := ids;
  elsif tg_table_name='mindex_songs' then
    select array_agg(id) into version_ids from public.mindex_song_versions
      where source_song_id=any(ids);
  elsif tg_table_name='mindex_canonical_songs' then
    select array_agg(id) into version_ids from public.mindex_song_versions
      where canonical_song_id=any(ids);
  elsif tg_table_name in ('mindex_scriptures','mindex_worship_templates') then
    version_ids := '{}';
  else
    raise exception 'INVALID_CANONICAL_TABLE';
  end if;
  select array_agg(distinct affected.service_id order by affected.service_id) into services from (
    select s.service_id from public.mindex_worship_elements e
      join public.mindex_worship_sections s on s.id=e.section_id
      where e.song_version_id=any(coalesce(version_ids,'{}'))
        or (tg_table_name='mindex_songs' and e.song_id=any(ids))
        or (tg_table_name='mindex_scriptures' and e.scripture_id=any(ids))
        or (tg_table_name='mindex_worship_templates' and (e.template_id=any(ids) or s.template_id=any(ids)))
    union
    select s.id from public.mindex_worship_services s
      where tg_table_name='mindex_worship_templates' and s.template_id=any(ids)
    union
    select s.service_id from public.mindex_worship_sections s
      where tg_table_name='mindex_worship_templates' and s.template_id=any(ids)
    union
    select s.service_id from public.mindex_worship_slides v
      join public.mindex_worship_elements e on e.id=v.element_id
      join public.mindex_worship_sections s on s.id=e.section_id
      where tg_table_name='mindex_worship_templates' and v.template_id=any(ids)
  ) affected;
  if cardinality(services)>0 and tg_op='DELETE' and tg_table_name<>'mindex_version_units'
    then raise exception 'CANONICAL_IN_USE' using errcode='23503'; end if;
  if tg_table_name='mindex_song_versions' and tg_op='UPDATE' then
    if exists(select from public.mindex_worship_elements e where e.song_version_id=old.id
      and e.song_id is distinct from coalesce(new.source_song_id,new.canonical_song_id))
      then raise exception 'LINKED_VERSION_REASSIGNMENT' using errcode='23503'; end if;
  end if;
  foreach sid in array coalesce(services,'{}') loop
    perform pg_advisory_xact_lock(hashtextextended(sid::text,0));
    perform 1 from public.mindex_worship_services where id=sid for update;
    -- Once per transaction/service, even for multi-row unit edits and UPSERT.
    -- A private table is used instead of a caller-forgeable setting or temp table.
    insert into mindex_atomic.canonical_invalidations values(sid,xid)
      on conflict(service_id) do update set last_xid=excluded.last_xid
      where mindex_atomic.canonical_invalidations.last_xid<>excluded.last_xid;
    get diagnostics touched = row_count;
    if touched=1 then
      insert into mindex_atomic.checkpoints values(sid,mindex_atomic.read_service(sid))
        on conflict(service_id) do update set aggregate=excluded.aggregate;
      update public.mindex_worship_services set save_revision=save_revision+1 where id=sid;
    end if;
  end loop;
  if tg_op='DELETE' then return old; else return new; end if;
end $$;

alter function mindex_atomic.canonical_write_gate() owner to mindex_atomic_writer;
alter function mindex_atomic.canonical_changed() owner to mindex_atomic_writer;
revoke all on function mindex_atomic.canonical_write_gate(), mindex_atomic.canonical_changed() from public;
do $$
declare tab text;
begin
  foreach tab in array array['mindex_songs','mindex_canonical_songs','mindex_song_versions',
    'mindex_version_units','mindex_scriptures','mindex_worship_templates'] loop
    execute format('alter table public.%I enable row level security',tab);
    execute format('create policy atomic_dependency_read on public.%I for select to mindex_atomic_writer using (true)',tab);
    execute format('create trigger atomic_canonical_gate before insert or update or delete on public.%I
      for each statement execute function mindex_atomic.canonical_write_gate()',tab);
    execute format('create trigger atomic_canonical_change before insert or update or delete on public.%I
      for each row execute function mindex_atomic.canonical_changed()',tab);
  end loop;
end $$;

comment on schema mindex_atomic is
  'Private atomic worship persistence state. Browser roles must not access this schema.';
comment on column public.mindex_worship_services.save_revision is
  'Server-owned compare-and-swap revision for atomic worship aggregate writes.';

revoke create on schema public, mindex_atomic from mindex_atomic_writer;
revoke mindex_atomic_writer from postgres;
notify pgrst, 'reload schema';

commit;
