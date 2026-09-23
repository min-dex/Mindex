create extension if not exists pgcrypto;

create table if not exists public.mindex_songs (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  subtitle text,
  original_title text,
  hymn_no text,
  praise_types text[] not null default '{}',
  artist text,
  lyricist text,
  composer text,
  translator text,
  album text,
  track text,
  scripture_refs text[] not null default '{}',
  memo text
);

alter table public.mindex_songs
  add column if not exists subtitle text;

alter table public.mindex_songs
  add column if not exists original_title text;

alter table public.mindex_songs
  add column if not exists praise_types text[] not null default '{}',
  add column if not exists artist text,
  add column if not exists lyricist text,
  add column if not exists composer text,
  add column if not exists translator text,
  add column if not exists album text,
  add column if not exists track text,
  add column if not exists scripture_refs text[] not null default '{}';

create index if not exists mindex_songs_title_idx
  on public.mindex_songs (title);

create index if not exists mindex_songs_hymn_no_idx
  on public.mindex_songs (hymn_no);

create table if not exists public.mindex_canonical_songs (
  id uuid primary key,
  title text not null,
  normalized_title text not null,
  subtitle text,
  original_title text,
  hymn_no text,
  source_count integer not null default 1,
  created_at timestamptz not null default now()
);

create table if not exists public.mindex_song_versions (
  id uuid primary key,
  canonical_song_id uuid not null references public.mindex_canonical_songs (id) on delete cascade,
  version_order integer not null,
  version_label text not null,
  curated_version_name text,
  version_review_status text not null default 'pending',
  source_song_id uuid references public.mindex_songs (id) on delete cascade,
  deck_key text,
  raw_section_name text,
  subtitle text,
  original_title text,
  hymn_no text,
  praise_types text[] not null default '{}',
  lyric_signature text not null,
  source_count integer not null default 1,
  is_primary boolean not null default false,
  created_at timestamptz not null default now(),
  unique (canonical_song_id, version_order),
  unique (canonical_song_id, lyric_signature)
);

alter table public.mindex_song_versions
  add column if not exists source_song_id uuid references public.mindex_songs (id) on delete cascade,
  add column if not exists praise_types text[] not null default '{}';

create index if not exists mindex_song_versions_source_song_idx
  on public.mindex_song_versions (source_song_id, version_order);

create table if not exists public.mindex_version_units (
  id uuid primary key,
  version_id uuid not null references public.mindex_song_versions (id) on delete cascade,
  canonical_song_id uuid not null references public.mindex_canonical_songs (id) on delete cascade,
  source_unit_id uuid,
  unit_order integer not null,
  unit_label text not null,
  unit_kind text not null,
  trigger text not null,
  slide_numbers jsonb not null default '[]'::jsonb,
  text text not null,
  curated_unit_type text,
  curated_unit_label text,
  curated_order integer,
  review_status text not null default 'pending',
  review_note text,
  reviewed_at timestamptz
);

create index if not exists mindex_version_units_version_idx
  on public.mindex_version_units (version_id, curated_order, unit_order);

create table if not exists public.mindex_song_relations (
  id uuid primary key default gen_random_uuid(),
  source_song_id uuid not null references public.mindex_songs(id) on delete cascade,
  related_song_id uuid not null references public.mindex_songs(id) on delete cascade,
  relation_type text not null default 'related',
  note text not null default '',
  created_at timestamptz not null default now(),
  check (source_song_id <> related_song_id),
  unique (source_song_id, related_song_id, relation_type)
);

create index if not exists mindex_song_relations_source_idx
  on public.mindex_song_relations (source_song_id, relation_type, related_song_id);

create index if not exists mindex_song_relations_related_idx
  on public.mindex_song_relations (related_song_id, relation_type, source_song_id);

-- Promote song-level support metadata out of the legacy memo JSON.
do $$
declare
  song_record record;
  memo_json jsonb;
  metadata_json jsonb;
  scripture_array text[];
begin
  for song_record in
    select id, memo
    from public.mindex_songs
    where memo is not null
      and memo <> ''
      and memo ~ '^\s*\{'
  loop
    begin
      memo_json := song_record.memo::jsonb;
    exception when others then
      continue;
    end;

    metadata_json := case
      when jsonb_typeof(memo_json -> 'metadata') = 'object' then memo_json -> 'metadata'
      else '{}'::jsonb
    end;

    scripture_array := '{}';
    if jsonb_typeof(memo_json -> 'scripture') = 'array' then
      select coalesce(array_agg(trim(item.value)), '{}'::text[])
      into scripture_array
      from jsonb_array_elements_text(memo_json -> 'scripture') as item(value)
      where trim(item.value) <> '';
    end if;

    update public.mindex_songs
    set
      artist = coalesce(nullif(artist, ''), nullif(coalesce(metadata_json ->> 'artist', metadata_json ->> 'performer'), '')),
      lyricist = coalesce(nullif(lyricist, ''), nullif(metadata_json ->> 'lyricist', '')),
      composer = coalesce(nullif(composer, ''), nullif(metadata_json ->> 'composer', '')),
      translator = coalesce(nullif(translator, ''), nullif(metadata_json ->> 'translator', '')),
      album = coalesce(nullif(album, ''), nullif(metadata_json ->> 'album', '')),
      track = coalesce(nullif(track, ''), nullif(metadata_json ->> 'track', '')),
      scripture_refs = case
        when cardinality(scripture_refs) > 0 then scripture_refs
        else scripture_array
      end
    where id = song_record.id;

    if metadata_json <> '{}'::jsonb then
      metadata_json := metadata_json
        - 'type'
        - 'categories'
        - 'otherTitle'
        - 'praiseTypes'
        - 'artist'
        - 'performer'
        - 'lyricist'
        - 'composer'
        - 'translator'
        - 'album'
        - 'track';

      if metadata_json = '{}'::jsonb then
        memo_json := memo_json - 'metadata';
      else
        memo_json := jsonb_set(memo_json, '{metadata}', metadata_json, true);
      end if;
    end if;

    memo_json := memo_json - 'scripture';

    update public.mindex_songs
    set memo = memo_json::text
    where id = song_record.id;
  end loop;
end $$;

-- Move current Mindex song versions/forms out of mindex_songs.memo.
-- Legacy PPT-import rows are preserved; Mindex-owned rows are identified by source_song_id.
insert into public.mindex_canonical_songs (
  id,
  title,
  normalized_title,
  subtitle,
  original_title,
  hymn_no,
  source_count
)
select
  id,
  title,
  regexp_replace(lower(coalesce(title, '')), '\s+', '', 'g'),
  subtitle,
  original_title,
  hymn_no,
  1
from public.mindex_songs
on conflict (id) do nothing;

do $$
declare
  song_record record;
  memo_json jsonb;
  version_record record;
  form_record record;
  next_version_id uuid;
  unit_type text;
  unit_label text;
  version_label text;
begin
  for song_record in
    select id, title, memo
    from public.mindex_songs
    where memo is not null
      and memo <> ''
      and memo ~ '^\s*\{'
  loop
    begin
      memo_json := song_record.memo::jsonb;
    exception when others then
      continue;
    end;

    if jsonb_typeof(memo_json -> 'versions') <> 'array'
      or jsonb_array_length(memo_json -> 'versions') = 0 then
      continue;
    end if;

    delete from public.mindex_version_units
    where version_id in (
      select id
      from public.mindex_song_versions
      where source_song_id = song_record.id
    );

    delete from public.mindex_song_versions
    where source_song_id = song_record.id;

    for version_record in
      select value, ordinality
      from jsonb_array_elements(memo_json -> 'versions') with ordinality
    loop
      next_version_id := gen_random_uuid();
      version_label := coalesce(
        nullif(version_record.value ->> 'raw_section_name', ''),
        nullif(version_record.value ->> 'version_label', ''),
        nullif(version_record.value ->> 'name', ''),
        'Version ' || version_record.ordinality
      );

      insert into public.mindex_song_versions (
        id,
        canonical_song_id,
        source_song_id,
        version_order,
        version_label,
        curated_version_name,
        version_review_status,
        deck_key,
        raw_section_name,
        subtitle,
        original_title,
        hymn_no,
        praise_types,
        lyric_signature,
        source_count,
        is_primary
      )
      values (
        next_version_id,
        song_record.id,
        song_record.id,
        version_record.ordinality,
        version_label,
        coalesce(nullif(version_record.value ->> 'name', ''), 'Version ' || version_record.ordinality),
        'reviewed',
        nullif(version_record.value ->> 'deck_key', ''),
        nullif(version_record.value ->> 'raw_section_name', ''),
        nullif(version_record.value ->> 'subtitle', ''),
        nullif(version_record.value ->> 'original_title', ''),
        nullif(version_record.value ->> 'hymn_no', ''),
        coalesce(
          (
            select array_agg(trim(item.value))
            from jsonb_array_elements_text(
              case
                when jsonb_typeof(version_record.value -> 'praise_types') = 'array'
                  then version_record.value -> 'praise_types'
                else '[]'::jsonb
              end
            ) as item(value)
            where trim(item.value) <> ''
          ),
          '{}'::text[]
        ),
        md5(version_record.value::text),
        1,
        coalesce((version_record.value ->> 'is_primary')::boolean, version_record.ordinality = 1)
      );

      if jsonb_typeof(version_record.value -> 'forms') = 'array' then
        for form_record in
          select value, ordinality
          from jsonb_array_elements(version_record.value -> 'forms') with ordinality
        loop
          unit_type := coalesce(nullif(form_record.value ->> 'part_type', ''), 'Lyrics');
          unit_label := coalesce(
            nullif(form_record.value ->> 'label', ''),
            case
              when nullif(form_record.value ->> 'part_number', '') is not null
                then unit_type || ' ' || (form_record.value ->> 'part_number')
              else unit_type
            end
          );

          insert into public.mindex_version_units (
            id,
            version_id,
            canonical_song_id,
            source_unit_id,
            unit_order,
            unit_label,
            unit_kind,
            trigger,
            slide_numbers,
            text,
            curated_unit_type,
            curated_unit_label,
            curated_order,
            review_status,
            review_note,
            reviewed_at
          )
          values (
            gen_random_uuid(),
            next_version_id,
            song_record.id,
            null,
            form_record.ordinality,
            unit_label,
            lower(regexp_replace(unit_type, '\s+', '-', 'g')),
            '',
            '[]'::jsonb,
            coalesce(form_record.value ->> 'lyrics', ''),
            unit_type,
            unit_label,
            form_record.ordinality,
            coalesce(nullif(form_record.value ->> 'review_status', ''), 'reviewed'),
            null,
            case
              when coalesce(nullif(form_record.value ->> 'review_status', ''), 'reviewed') = 'reviewed' then now()
              else null
            end
          );
        end loop;
      end if;
    end loop;

    memo_json := memo_json - 'versions';
    update public.mindex_songs
    set memo = case when memo_json = '{}'::jsonb then null else memo_json::text end
    where id = song_record.id;
  end loop;
end $$;

create table if not exists public.mindex_scripture_books (
  code text primary key,
  sort_order integer not null,
  testament text not null,
  korean_name text not null,
  english_name text not null,
  short_name text not null,
  aliases text[] not null default '{}',
  metadata jsonb not null default '{}'::jsonb,
  is_active boolean not null default true
);

alter table public.mindex_scripture_books
  add column if not exists metadata jsonb not null default '{}'::jsonb;

alter table public.mindex_scripture_books
  drop constraint if exists mindex_scripture_books_sort_order_key;

create index if not exists mindex_scripture_books_active_order_idx
  on public.mindex_scripture_books (is_active, testament, sort_order);
insert into public.mindex_scripture_books
  (code, sort_order, testament, korean_name, english_name, short_name, aliases, metadata)
values
  ('GEN', 1, 'Old Testament', '창세기', 'Genesis', '창', array['Genesis','창','Book of Genesis'], jsonb_build_object('chapters', 50)),
  ('EXO', 2, 'Old Testament', '출애굽기', 'Exodus', '출', array['Exodus','출','Book of Exodus'], jsonb_build_object('chapters', 40)),
  ('LEV', 3, 'Old Testament', '레위기', 'Leviticus', '레', array['Leviticus','레','Book of Leviticus'], jsonb_build_object('chapters', 27)),
  ('NUM', 4, 'Old Testament', '민수기', 'Numbers', '민', array['Numbers','민','Book of Numbers'], jsonb_build_object('chapters', 36)),
  ('DEU', 5, 'Old Testament', '신명기', 'Deuteronomy', '신', array['Deuteronomy','신','Book of Deuteronomy'], jsonb_build_object('chapters', 34)),
  ('JOS', 6, 'Old Testament', '여호수아', 'Joshua', '수', array['Joshua','수','Book of Joshua'], jsonb_build_object('chapters', 24)),
  ('JDG', 7, 'Old Testament', '사사기', 'Judges', '삿', array['Judges','삿','Book of Judges'], jsonb_build_object('chapters', 21)),
  ('RUT', 8, 'Old Testament', '룻기', 'Ruth', '룻', array['Ruth','룻','Book of Ruth'], jsonb_build_object('chapters', 4)),
  ('1SA', 9, 'Old Testament', '사무엘상', '1 Samuel', '삼상', array['1 Samuel','삼상','First Book of Samuel'], jsonb_build_object('chapters', 31)),
  ('2SA', 10, 'Old Testament', '사무엘하', '2 Samuel', '삼하', array['2 Samuel','삼하','Second Book of Samuel'], jsonb_build_object('chapters', 24)),
  ('1KI', 11, 'Old Testament', '열왕기상', '1 Kings', '왕상', array['1 Kings','왕상','First Book of Kings'], jsonb_build_object('chapters', 22)),
  ('2KI', 12, 'Old Testament', '열왕기하', '2 Kings', '왕하', array['2 Kings','왕하','Second Book of Kings'], jsonb_build_object('chapters', 25)),
  ('1CH', 13, 'Old Testament', '역대상', '1 Chronicles', '대상', array['1 Chronicles','대상','First Book of Chronicles'], jsonb_build_object('chapters', 29)),
  ('2CH', 14, 'Old Testament', '역대하', '2 Chronicles', '대하', array['2 Chronicles','대하','Second Book of Chronicles'], jsonb_build_object('chapters', 36)),
  ('EZR', 15, 'Old Testament', '에스라', 'Ezra', '스', array['Ezra','스','Book of Ezra'], jsonb_build_object('chapters', 10)),
  ('NEH', 16, 'Old Testament', '느헤미야', 'Nehemiah', '느', array['Nehemiah','느','Book of Nehemiah'], jsonb_build_object('chapters', 13)),
  ('EST', 17, 'Old Testament', '에스더', 'Esther', '에', array['Esther','에','Book of Esther'], jsonb_build_object('chapters', 10)),
  ('JOB', 18, 'Old Testament', '욥기', 'Job', '욥', array['Job','욥','Book of Job'], jsonb_build_object('chapters', 42)),
  ('PSA', 19, 'Old Testament', '시편', 'Psalms', '시', array['Psalms','시','Book of Psalms','Psalm'], jsonb_build_object('chapters', 150)),
  ('PRO', 20, 'Old Testament', '잠언', 'Proverbs', '잠', array['Proverbs','잠','Book of Proverbs'], jsonb_build_object('chapters', 31)),
  ('ECC', 21, 'Old Testament', '전도서', 'Ecclesiastes', '전', array['Ecclesiastes','전','Ecclesiastes'], jsonb_build_object('chapters', 12)),
  ('SNG', 22, 'Old Testament', '아가', 'Song of Songs', '아', array['Song of Songs','아','Song of Songs','Song of Solomon'], jsonb_build_object('chapters', 8)),
  ('ISA', 23, 'Old Testament', '이사야', 'Isaiah', '사', array['Isaiah','사','Book of Isaiah'], jsonb_build_object('chapters', 66)),
  ('JER', 24, 'Old Testament', '예레미야', 'Jeremiah', '렘', array['Jeremiah','렘','Book of Jeremiah'], jsonb_build_object('chapters', 52)),
  ('LAM', 25, 'Old Testament', '예레미야애가', 'Lamentations', '애', array['Lamentations','애','Book of Lamentations'], jsonb_build_object('chapters', 5)),
  ('EZK', 26, 'Old Testament', '에스겔', 'Ezekiel', '겔', array['Ezekiel','겔','Book of Ezekiel'], jsonb_build_object('chapters', 48)),
  ('DAN', 27, 'Old Testament', '다니엘', 'Daniel', '단', array['Daniel','단','Book of Daniel'], jsonb_build_object('chapters', 12)),
  ('HOS', 28, 'Old Testament', '호세아', 'Hosea', '호', array['Hosea','호','Book of Hosea'], jsonb_build_object('chapters', 14)),
  ('JOL', 29, 'Old Testament', '요엘', 'Joel', '욜', array['Joel','욜','Book of Joel'], jsonb_build_object('chapters', 3)),
  ('AMO', 30, 'Old Testament', '아모스', 'Amos', '암', array['Amos','암','Book of Amos'], jsonb_build_object('chapters', 9)),
  ('OBA', 31, 'Old Testament', '오바댜', 'Obadiah', '옵', array['Obadiah','옵','Book of Obadiah'], jsonb_build_object('chapters', 1)),
  ('JON', 32, 'Old Testament', '요나', 'Jonah', '욘', array['Jonah','욘','Book of Jonah'], jsonb_build_object('chapters', 4)),
  ('MIC', 33, 'Old Testament', '미가', 'Micah', '미', array['Micah','미','Book of Micah'], jsonb_build_object('chapters', 7)),
  ('NAM', 34, 'Old Testament', '나훔', 'Nahum', '나', array['Nahum','나','Book of Nahum'], jsonb_build_object('chapters', 3)),
  ('HAB', 35, 'Old Testament', '하박국', 'Habakkuk', '합', array['Habakkuk','합','Book of Habakkuk'], jsonb_build_object('chapters', 3)),
  ('ZEP', 36, 'Old Testament', '스바냐', 'Zephaniah', '습', array['Zephaniah','습','Book of Zephaniah'], jsonb_build_object('chapters', 3)),
  ('HAG', 37, 'Old Testament', '학개', 'Haggai', '학', array['Haggai','학','Book of Haggai'], jsonb_build_object('chapters', 2)),
  ('ZEC', 38, 'Old Testament', '스가랴', 'Zechariah', '슥', array['Zechariah','슥','Book of Zechariah'], jsonb_build_object('chapters', 14)),
  ('MAL', 39, 'Old Testament', '말라기', 'Malachi', '말', array['Malachi','말','Book of Malachi'], jsonb_build_object('chapters', 4)),
  ('MAT', 40, 'New Testament', '마태복음', 'Matthew', '마', array['Matthew','마','Gospel of Matthew'], jsonb_build_object('chapters', 28)),
  ('MRK', 41, 'New Testament', '마가복음', 'Mark', '막', array['Mark','막','Gospel of Mark'], jsonb_build_object('chapters', 16)),
  ('LUK', 42, 'New Testament', '누가복음', 'Luke', '눅', array['Luke','눅','Gospel of Luke'], jsonb_build_object('chapters', 24)),
  ('JHN', 43, 'New Testament', '요한복음', 'John', '요', array['John','요','Gospel of John'], jsonb_build_object('chapters', 21)),
  ('ACT', 44, 'New Testament', '사도행전', 'Acts', '행', array['Acts','행','Acts of the Apostles'], jsonb_build_object('chapters', 28)),
  ('ROM', 45, 'New Testament', '로마서', 'Romans', '롬', array['Romans','롬','Epistle to the Romans'], jsonb_build_object('chapters', 16)),
  ('1CO', 46, 'New Testament', '고린도전서', '1 Corinthians', '고전', array['1 Corinthians','고전','First Epistle to the Corinthians'], jsonb_build_object('chapters', 16)),
  ('2CO', 47, 'New Testament', '고린도후서', '2 Corinthians', '고후', array['2 Corinthians','고후','Second Epistle to the Corinthians'], jsonb_build_object('chapters', 13)),
  ('GAL', 48, 'New Testament', '갈라디아서', 'Galatians', '갈', array['Galatians','갈','Epistle to the Galatians'], jsonb_build_object('chapters', 6)),
  ('EPH', 49, 'New Testament', '에베소서', 'Ephesians', '엡', array['Ephesians','엡','Epistle to the Ephesians'], jsonb_build_object('chapters', 6)),
  ('PHP', 50, 'New Testament', '빌립보서', 'Philippians', '빌', array['Philippians','빌','Epistle to the Philippians'], jsonb_build_object('chapters', 4)),
  ('COL', 51, 'New Testament', '골로새서', 'Colossians', '골', array['Colossians','골','Epistle to the Colossians'], jsonb_build_object('chapters', 4)),
  ('1TH', 52, 'New Testament', '데살로니가전서', '1 Thessalonians', '살전', array['1 Thessalonians','살전','First Epistle to the Thessalonians'], jsonb_build_object('chapters', 5)),
  ('2TH', 53, 'New Testament', '데살로니가후서', '2 Thessalonians', '살후', array['2 Thessalonians','살후','Second Epistle to the Thessalonians'], jsonb_build_object('chapters', 3)),
  ('1TI', 54, 'New Testament', '디모데전서', '1 Timothy', '딤전', array['1 Timothy','딤전','First Epistle to Timothy'], jsonb_build_object('chapters', 6)),
  ('2TI', 55, 'New Testament', '디모데후서', '2 Timothy', '딤후', array['2 Timothy','딤후','Second Epistle to Timothy'], jsonb_build_object('chapters', 4)),
  ('TIT', 56, 'New Testament', '디도서', 'Titus', '딛', array['Titus','딛','Epistle to Titus'], jsonb_build_object('chapters', 3)),
  ('PHM', 57, 'New Testament', '빌레몬서', 'Philemon', '몬', array['Philemon','몬','Epistle to Philemon'], jsonb_build_object('chapters', 1)),
  ('HEB', 58, 'New Testament', '히브리서', 'Hebrews', '히', array['Hebrews','히','Epistle to the Hebrews'], jsonb_build_object('chapters', 13)),
  ('JAS', 59, 'New Testament', '야고보서', 'James', '약', array['James','약','Epistle of James'], jsonb_build_object('chapters', 5)),
  ('1PE', 60, 'New Testament', '베드로전서', '1 Peter', '벧전', array['1 Peter','벧전','First Epistle of Peter'], jsonb_build_object('chapters', 5)),
  ('2PE', 61, 'New Testament', '베드로후서', '2 Peter', '벧후', array['2 Peter','벧후','Second Epistle of Peter'], jsonb_build_object('chapters', 3)),
  ('1JN', 62, 'New Testament', '요한일서', '1 John', '요일', array['1 John','요일','First Epistle of John'], jsonb_build_object('chapters', 5)),
  ('2JN', 63, 'New Testament', '요한이서', '2 John', '요이', array['2 John','요이','Second Epistle of John'], jsonb_build_object('chapters', 1)),
  ('3JN', 64, 'New Testament', '요한삼서', '3 John', '요삼', array['3 John','요삼','Third Epistle of John'], jsonb_build_object('chapters', 1)),
  ('JUD', 65, 'New Testament', '유다서', 'Jude', '유', array['Jude','유','Epistle of Jude'], jsonb_build_object('chapters', 1)),
  ('REV', 66, 'New Testament', '요한계시록', 'Revelation', '계', array['Revelation','계','Book of Revelation'], jsonb_build_object('chapters', 22))
on conflict (code) do update set
  sort_order = excluded.sort_order,
  testament = excluded.testament,
  korean_name = excluded.korean_name,
  english_name = excluded.english_name,
  short_name = excluded.short_name,
  aliases = excluded.aliases,
  is_active = excluded.is_active;

update public.mindex_scripture_books
set
  metadata = coalesce(metadata, '{}'::jsonb);

create table if not exists public.mindex_scriptures (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  book_code text references public.mindex_scripture_books (code),
  book text not null default '',
  reference text not null default '',
  translation text not null default '',
  text text not null default '',
  memo text,
  is_active boolean not null default true
);

create index if not exists mindex_scriptures_title_idx
  on public.mindex_scriptures (title);

create index if not exists mindex_scriptures_reference_idx
  on public.mindex_scriptures (reference);

alter table public.mindex_scriptures
  add column if not exists book text not null default '';

alter table public.mindex_scriptures
  add column if not exists book_code text;

do $$
begin
  alter table public.mindex_scriptures
    add constraint mindex_scriptures_book_code_fkey
    foreign key (book_code)
    references public.mindex_scripture_books (code);
exception
  when duplicate_object then null;
end $$;

create index if not exists mindex_scriptures_book_idx
  on public.mindex_scriptures (book);

create index if not exists mindex_scriptures_book_code_idx
  on public.mindex_scriptures (book_code);

create table if not exists public.mindex_bible_translations (
  id uuid primary key default gen_random_uuid(),
  translation_key text not null unique,
  name text not null,
  language text not null default 'ko',
  abbreviation text not null default '',
  source text not null default '',
  license text not null default '',
  metadata jsonb not null default '{}'::jsonb,
  is_active boolean not null default true
);

create table if not exists public.mindex_bible_verses (
  id uuid primary key default gen_random_uuid(),
  translation_id uuid not null references public.mindex_bible_translations (id) on delete cascade,
  book_code text not null references public.mindex_scripture_books (code),
  chapter integer not null check (chapter > 0),
  verse integer not null check (verse > 0),
  verse_end integer check (verse_end is null or verse_end >= verse),
  text text not null,
  paragraph_index integer,
  section_title text not null default '',
  metadata jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  unique (translation_id, book_code, chapter, verse)
);

-- The UNIQUE constraint above already indexes translation/book/chapter/verse.
-- Do not duplicate it with a separate lookup index.

create index if not exists mindex_bible_verses_book_chapter_idx
  on public.mindex_bible_verses (book_code, chapter);

-- Prototype collaboration policies.
-- Use only with a browser-safe anon key and a project intended for shared editing.
alter table public.mindex_songs enable row level security;
alter table public.mindex_canonical_songs enable row level security;
alter table public.mindex_song_versions enable row level security;
alter table public.mindex_version_units enable row level security;
alter table public.mindex_song_relations enable row level security;
alter table public.mindex_scripture_books enable row level security;
alter table public.mindex_scriptures enable row level security;
alter table public.mindex_bible_translations enable row level security;
alter table public.mindex_bible_verses enable row level security;

grant select, insert, update, delete on public.mindex_song_relations to anon, authenticated;

drop policy if exists "mindex_songs_shared_read" on public.mindex_songs;
create policy "mindex_songs_shared_read"
  on public.mindex_songs
  for select
  to anon
  using (true);

drop policy if exists "mindex_songs_shared_insert" on public.mindex_songs;
create policy "mindex_songs_shared_insert"
  on public.mindex_songs
  for insert
  to anon
  with check (true);

drop policy if exists "mindex_songs_shared_update" on public.mindex_songs;
create policy "mindex_songs_shared_update"
  on public.mindex_songs
  for update
  to anon
  using (true)
  with check (true);

drop policy if exists "mindex_songs_shared_delete" on public.mindex_songs;
create policy "mindex_songs_shared_delete"
  on public.mindex_songs
  for delete
  to anon
  using (true);

drop policy if exists "mindex_canonical_songs_shared_read" on public.mindex_canonical_songs;
create policy "mindex_canonical_songs_shared_read"
  on public.mindex_canonical_songs
  for select
  to anon
  using (true);

drop policy if exists "mindex_canonical_songs_shared_insert" on public.mindex_canonical_songs;
create policy "mindex_canonical_songs_shared_insert"
  on public.mindex_canonical_songs
  for insert
  to anon
  with check (true);

drop policy if exists "mindex_canonical_songs_shared_update" on public.mindex_canonical_songs;
create policy "mindex_canonical_songs_shared_update"
  on public.mindex_canonical_songs
  for update
  to anon
  using (true)
  with check (true);

drop policy if exists "mindex_canonical_songs_shared_delete" on public.mindex_canonical_songs;
create policy "mindex_canonical_songs_shared_delete"
  on public.mindex_canonical_songs
  for delete
  to anon
  using (true);

drop policy if exists "mindex_song_versions_shared_read" on public.mindex_song_versions;
create policy "mindex_song_versions_shared_read"
  on public.mindex_song_versions
  for select
  to anon
  using (true);

drop policy if exists "mindex_song_versions_shared_insert" on public.mindex_song_versions;
create policy "mindex_song_versions_shared_insert"
  on public.mindex_song_versions
  for insert
  to anon
  with check (true);

drop policy if exists "mindex_song_versions_shared_update" on public.mindex_song_versions;
create policy "mindex_song_versions_shared_update"
  on public.mindex_song_versions
  for update
  to anon
  using (true)
  with check (true);

drop policy if exists "mindex_song_versions_shared_delete" on public.mindex_song_versions;
create policy "mindex_song_versions_shared_delete"
  on public.mindex_song_versions
  for delete
  to anon
  using (true);

drop policy if exists "mindex_version_units_shared_read" on public.mindex_version_units;
create policy "mindex_version_units_shared_read"
  on public.mindex_version_units
  for select
  to anon
  using (true);

drop policy if exists "mindex_version_units_shared_insert" on public.mindex_version_units;
create policy "mindex_version_units_shared_insert"
  on public.mindex_version_units
  for insert
  to anon
  with check (true);

drop policy if exists "mindex_version_units_shared_update" on public.mindex_version_units;
create policy "mindex_version_units_shared_update"
  on public.mindex_version_units
  for update
  to anon
  using (true)
  with check (true);

drop policy if exists "mindex_version_units_shared_delete" on public.mindex_version_units;
create policy "mindex_version_units_shared_delete"
  on public.mindex_version_units
  for delete
  to anon
  using (true);

drop policy if exists "mindex_song_relations_shared_read" on public.mindex_song_relations;
create policy "mindex_song_relations_shared_read"
  on public.mindex_song_relations
  for select
  to anon
  using (true);

drop policy if exists "mindex_song_relations_shared_insert" on public.mindex_song_relations;
create policy "mindex_song_relations_shared_insert"
  on public.mindex_song_relations
  for insert
  to anon
  with check (true);

drop policy if exists "mindex_song_relations_shared_update" on public.mindex_song_relations;
create policy "mindex_song_relations_shared_update"
  on public.mindex_song_relations
  for update
  to anon
  using (true)
  with check (true);

drop policy if exists "mindex_song_relations_shared_delete" on public.mindex_song_relations;
create policy "mindex_song_relations_shared_delete"
  on public.mindex_song_relations
  for delete
  to anon
  using (true);

drop policy if exists "mindex_scripture_books_shared_read" on public.mindex_scripture_books;
create policy "mindex_scripture_books_shared_read"
  on public.mindex_scripture_books
  for select
  to anon
  using (true);

drop policy if exists "mindex_scriptures_shared_read" on public.mindex_scriptures;
create policy "mindex_scriptures_shared_read"
  on public.mindex_scriptures
  for select
  to anon
  using (true);

drop policy if exists "mindex_scriptures_shared_insert" on public.mindex_scriptures;
create policy "mindex_scriptures_shared_insert"
  on public.mindex_scriptures
  for insert
  to anon
  with check (true);

drop policy if exists "mindex_scriptures_shared_update" on public.mindex_scriptures;
create policy "mindex_scriptures_shared_update"
  on public.mindex_scriptures
  for update
  to anon
  using (true)
  with check (true);

drop policy if exists "mindex_scriptures_shared_delete" on public.mindex_scriptures;
create policy "mindex_scriptures_shared_delete"
  on public.mindex_scriptures
  for delete
  to anon
  using (true);

drop policy if exists "mindex_bible_translations_shared_read" on public.mindex_bible_translations;
create policy "mindex_bible_translations_shared_read"
  on public.mindex_bible_translations
  for select
  to anon
  using (true);

drop policy if exists "mindex_bible_verses_shared_read" on public.mindex_bible_verses;
create policy "mindex_bible_verses_shared_read"
  on public.mindex_bible_verses
  for select
  to anon
  using (true);

create table if not exists public.mindex_reference_links (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  url text not null,
  group_name text,
  sort_order integer not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.mindex_reference_links
  add column if not exists group_name text;

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'mindex_reference_links'
      and column_name = 'category'
  ) then
    execute 'update public.mindex_reference_links set group_name = nullif(category, '''') where group_name is null';
  end if;
end $$;

alter table public.mindex_reference_links
  drop column if exists category,
  drop column if exists description;

create index if not exists mindex_reference_links_sort_idx
  on public.mindex_reference_links (sort_order, title);

alter table public.mindex_reference_links enable row level security;

drop policy if exists "mindex_reference_links_shared_read" on public.mindex_reference_links;
create policy "mindex_reference_links_shared_read"
  on public.mindex_reference_links
  for select
  to anon
  using (true);

drop policy if exists "mindex_reference_links_shared_insert" on public.mindex_reference_links;
create policy "mindex_reference_links_shared_insert"
  on public.mindex_reference_links
  for insert
  to anon
  with check (true);

drop policy if exists "mindex_reference_links_shared_update" on public.mindex_reference_links;
create policy "mindex_reference_links_shared_update"
  on public.mindex_reference_links
  for update
  to anon
  using (true)
  with check (true);

drop policy if exists "mindex_reference_links_shared_delete" on public.mindex_reference_links;
create policy "mindex_reference_links_shared_delete"
  on public.mindex_reference_links
  for delete
  to anon
  using (true);

-- Migration: remove is_active from mindex_songs (concept removed from app)
alter table public.mindex_songs drop column if exists is_active;
