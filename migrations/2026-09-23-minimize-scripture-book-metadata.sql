-- Keep Mindex scripture-book records focused on worship lookup and reading.
-- The first statement stores a JSON snapshot of every original row so this
-- migration is reversible without touching scripture, verse, or worship links.
begin;

do $preflight$
declare
  book_count integer;
  missing_chapter_count integer;
begin
  select count(*) into book_count
  from public.mindex_scripture_books;
  if book_count <> 66 then
    raise exception 'SCRIPTURE_BOOK_COUNT_MISMATCH:%', book_count;
  end if;

  select count(*) into missing_chapter_count
  from public.mindex_scripture_books
  where coalesce(nullif(metadata ->> 'chapters', '')::integer, 0) < 1;
  if missing_chapter_count <> 0 then
    raise exception 'SCRIPTURE_CHAPTER_COUNT_MISSING:%', missing_chapter_count;
  end if;
end
$preflight$;

create schema if not exists mindex_archive;

create table if not exists mindex_archive.scripture_books_metadata_backup (
  id bigint generated always as identity primary key,
  backed_up_at timestamptz not null default now(),
  migration_key text not null,
  code text not null,
  payload jsonb not null,
  unique (migration_key, code)
);

insert into mindex_archive.scripture_books_metadata_backup (migration_key, code, payload)
select '2026-09-23-minimize-scripture-book-metadata', code, to_jsonb(mindex_scripture_books)
from public.mindex_scripture_books
on conflict (migration_key, code) do nothing;

-- Formal English titles remain reference/search aliases before their separate
-- column is removed. Existing aliases retain their original order.
update public.mindex_scripture_books
set aliases = coalesce(aliases, '{}'::text[]) || array[canonical_english_title]
where nullif(canonical_english_title, '') is not null
  and not (canonical_english_title = any(coalesce(aliases, '{}'::text[])));

-- Chapters are the only per-book metadata Mindex needs. Retain a compact,
-- stable representation rather than unrelated learning and import fields.
update public.mindex_scripture_books
set metadata = jsonb_build_object('chapters', (metadata ->> 'chapters')::integer);

drop index if exists public.mindex_scripture_books_scope_order_idx;
drop index if exists public.mindex_scripture_books_corpus_idx;
create index if not exists mindex_scripture_books_active_order_idx
  on public.mindex_scripture_books (is_active, testament, sort_order);

alter table public.mindex_scripture_books
  drop column if exists division,
  drop column if exists canonical_english_title,
  drop column if exists jewish_category,
  drop column if exists author,
  drop column if exists corpus,
  drop column if exists canon,
  drop column if exists book_group,
  drop column if exists osis_code,
  drop column if exists usfm_code;

notify pgrst, 'reload schema';

commit;
