from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ENV_PATHS = (
    ROOT / ".env.supabase.local",
    ROOT / ".env.supabase",
)

REQUIRED_TABLES: dict[str, tuple[str, ...]] = {
    "mindex_songs": ("id", "title", "hymn_no", "praise_types", "scripture_refs", "memo"),
    "mindex_canonical_songs": ("id", "title", "normalized_title", "source_count"),
    "mindex_song_versions": ("id", "canonical_song_id", "version_order", "version_label"),
    "mindex_version_units": ("id", "version_id", "unit_order", "unit_label", "unit_kind", "text"),
    "mindex_scriptures": ("id", "title", "book_code", "reference", "translation", "text", "is_active"),
    "mindex_scripture_books": ("code", "korean_name", "english_name", "sort_order", "is_active"),
    "mindex_bible_translations": ("id", "translation_key", "name", "abbreviation", "language"),
    "mindex_bible_verses": ("id", "translation_id", "book_code", "chapter", "verse", "text"),
    "mindex_worship_service_types": ("id", "display_name", "group_key", "sort_order", "default_output_context"),
    "mindex_worship_services": (
        "id",
        "service_type_id",
        "service_date",
        "created_at",
        "updated_at",
        "title",
        "service_alias",
        "status",
        "worship_leader",
        "praise_leader",
    ),
    "mindex_worship_sections": ("id", "service_id", "sort_order", "created_at", "updated_at", "section_key", "title"),
    "mindex_worship_elements": ("id", "section_id", "sort_order", "created_at", "updated_at", "element_type", "title", "person", "song_id", "scripture_reference", "input_mode", "content_state"),
    "mindex_worship_slides": ("id", "element_id", "sort_order", "created_at", "updated_at", "slide_type", "output_context", "title", "body", "marker"),
    "mindex_worship_templates": ("id", "template_level", "stable_key", "version", "name"),
    "mindex_worship_template_items": ("id", "template_id", "sort_order", "slot_key", "default_title"),
    "mindex_worship_import_sources": ("id", "source_kind", "source_name", "status", "raw_payload"),
    "mindex_worship_import_candidates": ("id", "import_source_id", "candidate_level", "review_status", "raw_title"),
    "mindex_worship_import_mappings": ("id", "import_source_id", "target_level", "review_status"),
    "mindex_reference_links": ("id", "title", "url", "sort_order"),
    "mindex_sunday_calendar": (
        "id",
        "date",
        "liturgical",
        "note",
        "church_schedule",
        "youth_offering_prayer",
        "liturgical_color",
        "first_reading",
        "psalm",
        "second_reading",
        "gospel",
    ),
}

OPTIONAL_COLUMNS: dict[str, tuple[str, ...]] = {
    "mindex_song_versions": ("praise_types",),
    "mindex_reference_links": ("group_name",),
}

OPTIONAL_TABLES: dict[str, tuple[str, ...]] = {
    "mindex_activity_events": ("id", "title", "date", "status", "location", "memo"),
    "mindex_activity_teams": ("id", "event_id", "name", "color", "score", "sort_order"),
    "mindex_activity_games": ("id", "event_id", "title", "game_type", "status", "sort_order", "owner", "location", "supplies", "memo", "config"),
    "mindex_activity_score_events": ("id", "event_id", "game_id", "team_id", "points", "reason", "created_at"),
    "mindex_activity_puzzle_boards": ("id", "game_id", "title", "rows", "cols", "image_url"),
    "mindex_activity_puzzle_pieces": ("id", "board_id", "label", "row_no", "col_no", "found", "found_by_team_id", "found_at", "points", "sort_order"),
    "mindex_activity_quiz_questions": ("id", "game_id", "question_type", "prompt", "answer", "points", "sort_order", "memo"),
    "mindex_activity_quiz_choices": ("id", "question_id", "label", "is_correct", "sort_order"),
    "mindex_activity_physical_games": ("game_id", "duration_seconds", "scoring_rule"),
}

SHOULD_HAVE_ROWS = (
    "mindex_songs",
    "mindex_scripture_books",
    "mindex_worship_service_types",
)


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def read_config() -> tuple[str, str]:
    url = os.environ.get("MINDEX_SUPABASE_URL") or os.environ.get("SUPABASE_URL", "")
    key = (
        os.environ.get("MINDEX_SUPABASE_ANON_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("SUPABASE_KEY")
        or ""
    )
    if url and key:
        return url, key

    for path in ENV_PATHS:
        values = read_env_file(path)
        url = values.get("MINDEX_SUPABASE_URL") or values.get("SUPABASE_URL", "")
        key = (
            values.get("MINDEX_SUPABASE_ANON_KEY")
            or values.get("SUPABASE_ANON_KEY")
            or values.get("SUPABASE_KEY")
            or values.get("SUPABASE_SERVICE_ROLE_KEY")
            or ""
        )
        if url and key:
            return url, key
    raise RuntimeError("Supabase config not found for Mindex.")


def request_json(supa_url: str, supa_key: str, table: str, select: str, headers: dict[str, str] | None = None) -> list[dict[str, Any]]:
    req = Request(
        f"{supa_url}/rest/v1/{table}?select={quote(select, safe='*,():')}&limit=1",
        headers={
            "apikey": supa_key,
            "Authorization": f"Bearer {supa_key}",
            **(headers or {}),
        },
    )
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def table_count(supa_url: str, supa_key: str, table: str, column: str = "id") -> int:
    req = Request(
        f"{supa_url}/rest/v1/{table}?select={quote(column)}&limit=1",
        headers={
            "apikey": supa_key,
            "Authorization": f"Bearer {supa_key}",
            "Prefer": "count=exact",
        },
    )
    with urlopen(req, timeout=30) as response:
        content_range = response.headers.get("Content-Range", "")
    match = re.search(r"/(\d+)$", content_range)
    return int(match.group(1)) if match else 0


def main() -> int:
    supa_url, supa_key = read_config()
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    for table, columns in REQUIRED_TABLES.items():
        select = ",".join(columns)
        try:
            request_json(supa_url, supa_key, table, select)
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            issues.append({"type": "schema-query-failed", "table": table, "status": error.code, "body": body[:300]})
            continue

        try:
            counts[table] = table_count(supa_url, supa_key, table, columns[0])
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            warnings.append({"type": "count-query-failed", "table": table, "status": error.code, "body": body[:300]})

    for table, columns in OPTIONAL_COLUMNS.items():
        for column in columns:
            try:
                request_json(supa_url, supa_key, table, column)
            except HTTPError as error:
                body = error.read().decode("utf-8", errors="replace")
                warnings.append({"type": "missing-optional-column", "table": table, "column": column, "status": error.code, "body": body[:300]})

    for table, columns in OPTIONAL_TABLES.items():
        try:
            request_json(supa_url, supa_key, table, ",".join(columns))
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            warnings.append({"type": "missing-optional-table", "table": table, "status": error.code, "body": body[:300]})

    for table in SHOULD_HAVE_ROWS:
        if counts.get(table, 0) == 0:
            warnings.append({"type": "empty-production-table", "table": table})

    print(json.dumps({"counts": counts, "issues": issues, "warnings": warnings}, ensure_ascii=False, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
