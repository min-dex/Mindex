# Mindex

Mindex is a church ministry operations app for worship preparation, presenter
output, Praise data, Scripture lookup, calendar, and reference links. Worship
and Presenter reliability are the live-operation priority; Praise and
Scripture remain canonical data modules used by worship elements.

## Collaboration Link

Mindex can be shared as a static GitHub Pages app. Share collaborators a link
with the Supabase project URL and browser-safe anon key. Prefer the `#` format
because it is read only by the browser:

```text
https://<github-user>.github.io/<repo-name>/#supabaseUrl=<PROJECT_URL>&supabaseAnonKey=<ANON_KEY>
```

The app keeps the collaboration config and the current app location in the URL
hash. Copying the link from the top-right link button preserves the active
module, filters, selected song/service/book, and Bible chapter where possible,
so a fresh browser can open the same workspace without relying on local storage.

Use only the Supabase anon key in browser links. Never put a service role key in
GitHub, GitHub Pages, screenshots, issues, or shared URLs.

For administrator-only links, prefer Supabase Auth and add `auth=required`:

```text
https://<github-user>.github.io/<repo-name>/#supabaseUrl=<PROJECT_URL>&supabaseAnonKey=<ANON_KEY>&auth=required
```

Before using that link model, enable Supabase Auth redirect URLs and run
`scripts/admin-auth-rls.sql`. See `docs/admin-access-security.md`.

The app also reads a local injected config if you host it somewhere private:

```html
<script>
  window.MINDEX_SUPABASE = {
    url: "https://project.supabase.co",
    anonKey: "<ANON_KEY>",
    authRequired: true
  };
</script>
```

## Run

Use the included no-cache server (changes reflect on Cmd+R):

```sh
python3 serve.py
```

Then open:

```text
http://localhost:2300
```

## Desktop App

The desktop app uses Electron as a thin shell around the same static Mindex UI.
It keeps Supabase as the primary data source and uses native windows for
presenter output.

Install JavaScript dependencies once:

```sh
pnpm install
```

Run the Electron app:

```sh
pnpm run electron:dev
```

Create a local packaged build for testing:

```sh
pnpm run electron:pack
```

Publish a signed, notarized desktop release and its update metadata:

```sh
pnpm run electron:release
```

The release command requires the GitHub upload token, Developer ID signing
certificate, and Apple notarization credentials described in
`docs/electron-packaging-plan.md`. Each published desktop release must increase
the version in `package.json`; installed apps only download a newer version.

## Supabase

Run `supabase-schema.sql` in the Supabase SQL editor first.

The app accepts Supabase config in these ways:

1. Add hash params: `#supabaseUrl=...&supabaseAnonKey=...`
2. Add query params: `?supabaseUrl=...&supabaseAnonKey=...`
3. Inject `window.MINDEX_SUPABASE` before `app.js` loads.

Settings are intentionally not shown in the app UI because collaborators should
enter through a prepared link.

The app still remembers a link-provided config in browser `localStorage` after
it loads, but shared links should remain self-contained and not depend on that
browser-local copy.

## Data Source

Content data lives in Supabase. Do not keep lyrics, Bible text, worship setlists,
or other ministry content in generated seed files. Repository files should define
schema, import tools, and UI behavior; content changes should be written to the
database.

## GitHub Pages

1. Push this folder to a GitHub repository.
2. In GitHub, open `Settings` -> `Pages`.
3. Set `Source` to `Deploy from a branch`.
4. Select the branch, usually `main`, and folder `/root`.
5. Open the published URL and append the Supabase query params from the
   collaboration link format above.

## Theme

Mindex follows the system light/dark setting by default. Toggle manually with
`Cmd/Ctrl + Shift + L`, matching Studex and Notion-style theme switching.

## Form Label Rules

- Allowed types: `Verse`, `Chorus`, `Pre-Chorus`, `Bridge`, `Coda`
- A single type has no number: `Verse`
- Multiple blocks of the same type are numbered by structural order: `Verse 1`, `Verse 2`
- `display_label` is calculated by the app from `part_type` and `part_number`
- Hymn `Amen` endings use `Coda`

## Praise Classification

`hymn_no` is only the hymn number metadata. The song list filters use praise
types instead: `hymn`, `ccm`, or both. Existing songs are inferred so hymns still
appear under `Hymns` and non-hymns under `CCM`. Songs that were CCM before hymn
book inclusion can store `ccm` in `praise_types`; with a `hymn_no`, they appear in
both filters.

## Praise Metadata

Song metadata uses direct `mindex_songs` columns for fields that are edited often.
The app still reads older `mindex_songs.memo.metadata` values as a fallback, then
saves promoted fields back to columns when those columns exist.
Currently supported promoted fields are:

- `praise_types`
- `artist`
- `lyricist`
- `composer`
- `translator`
- `album`
- `track`
- `scripture_refs`

When `lyricist` and `composer` are identical, the app displays them as
`Words/Music`.

### Canonical Praise Titles

`mindex_canonical_songs.normalized_title` is a matching key, not display text.
Keep the public title in `title`, aliases or alternate first lines in
`subtitle`, and formal English names in `original_title`.

Most canonical rows use the normalized main title only. When two genuinely
different songs share the same main title, the app derives a variant key instead
of adding one-off song exceptions:

- children songs: `normalizedTitle::children`
- same-title songs distinguished by subtitle: `normalizedTitle::normalizedSubtitle`

This keeps official title spelling clean while allowing rough user input,
spacing mistakes, subtitles, and aliases to match through normalization.

Run `scripts/db-maintenance-2026-06-23.sql` when the Supabase schema needs the
current app columns, indexes, and ordered table-browsing views. The legacy
`mindex_songs.memo.versions` payload can be copied into relational
`mindex_song_versions` / `mindex_version_units` rows with:

```sh
python3 scripts/backfill_song_versions_from_memo.py
python3 scripts/backfill_song_versions_from_memo.py --apply
```

Only add `--clear-memo-versions` after verifying the relational rows in the app.

Song-to-song relationships are stored in `mindex_song_relations`. Older
`mindex_songs.memo.related_song_ids` values can be moved with:

```sh
python3 scripts/backfill_song_relations_from_memo.py
python3 scripts/backfill_song_relations_from_memo.py --apply
```

Only add `--clear-memo-related` after verifying the relation rows in the app.

### Hymn Reference Audit

Use 하나성경 as a read-only reference to check hymn numbers, titles, missing
lyrics, and broad verse/chorus/Amen structure. The audit does not write to
Supabase and does not persist or include the reference lyrics in its report.

```sh
python3 scripts/audit_hbible_hymns.py --book new --number 202
python3 scripts/audit_hbible_hymns.py --book union --number 204
python3 scripts/audit_hbible_hymns.py --book both --output /tmp/mindex-hymn-audit.json
```

Treat findings as review candidates. Do not automatically replace MINDEX text,
line breaks, or 새찬송가-통일찬송가 relationships from this source.

## Presenter Media

Presenter video slides should store only a file path or public URL in service
item text, not video bytes in the database. Use browser-friendly H.264 `.mp4`
for the safest church-computer playback; `1920x1080` at `30fps` is the practical
default unless the output chain is known to be 4K.

## Copy / Projection

The Forms view keeps only the current working exports:

- `Text`: copies lyrics with song form labels such as `[Verse 1]` and `[Chorus]`
- `Show`: downloads the selected version as a FreeShow `.show` file
- `XML`: downloads the selected version as a simple XML file

The Scripture view stores a title, Bible book, reference, translation, passage
text, and note. Bible books in `mindex_scripture_books` retain only the worship
lookup fields: code, Korean and English names, aliases, order, Old/New Testament,
short name, and chapter count in `metadata.chapters`. Broader learning metadata
is maintained outside Mindex.

The Notion export source has been normalized into `data/scripture-books.csv`.
Future Bible XML imports should write a row to `mindex_bible_translations` and
verse rows to `mindex_bible_verses` keyed by `translation_id`, `book_code`,
`chapter`, and `verse`. These verse tables are read-only for browser links;
imports should use a server-side/service-role script. `Text` copies the passage
with its heading. `Slides` copies blank-line separated passage blocks with
`[Scripture n]` labels.

Import EasySlides XML Bible files after running `supabase-schema.sql`:

```sh
python3 scripts/import_bible_xml.py "/path/to/성경(.xml).zip" --dry-run
python3 scripts/import_bible_xml.py "/path/to/성경(.xml).zip"
```
