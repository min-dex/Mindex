# Bulletin artwork and printed references

Bulletin backgrounds reuse MINDEX files in `assets/worship-backgrounds/`. Do not duplicate or resize the same background into this directory.

- Reviewed 2026-07-05 through 2026-08-23 issues retain `26-A3.png`, continuous white paper and a black RIA logo. The date rule covers this observed print period through the next reviewed change on September 6; it does not change the Presenter’s seasonal selection.
- September issues use `26-A5.png`, separate white panels and the image-filled RIA logo.
- `ria-mark-ink.svg` contains the four original RIA paths and three 청년부 glyphs extracted from page 1 of **청년부 주보 260719 (제19호).pdf**. It contains no background image or recreated logo lettering.
- `ria-mark.webp` is the existing logo crop from the user-provided September 20 PDF.
- Layout stores panel/logo design and outline columns alongside frames and background. Manual choices override date defaults.

The exact-date `archiveReference` data in `mindex.bulletin.js` is transcribed from the nine July–September PDFs listed in [the comparison](../../docs/young-adult-bulletin-weekly-comparison-20260926.md).
It supplies printed news, missing leaders/advertisement assignees, outlines, short scripture references, and the **as-published** roster.
It never supplies those weekly values to a different date. The editor identifies this source and permits switching to current worship/calendar data.
The printed communal prayer is part of the reviewed 2026 youth print order; it is not inserted into the worship DB.

Original errors are not generalized: September 20 repeated news numbering is renumbered; August 2 NEXT follows the next Sunday.
The July 5 fourth-song discrepancy and September 6 hymn-number discrepancy remain visible for review, with the existing linked DB song retained.

`content.sourceSnapshot` freezes the selected weekly projection and each saved roster month. It uses the existing content JSON column; no schema or production backfill is needed.
The explicit source-refresh action clears that snapshot and archive-copy selection while preserving manually edited fields. Common/monthly sharing excludes weekly source snapshots.
