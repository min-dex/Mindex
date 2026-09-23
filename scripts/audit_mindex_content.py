from __future__ import annotations

import json
import os
import re
import argparse
from datetime import date
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
ENV_PATHS = (
    ROOT / ".env.supabase.local",
    ROOT / ".env.supabase",
)
TEST_PATTERNS = re.compile(r"\b(test|dummy|sample|probe|debug)\b", re.IGNORECASE)


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

    raise RuntimeError(
        "Supabase config not found. Set MINDEX_SUPABASE_URL and "
        "MINDEX_SUPABASE_ANON_KEY, or use a local .env.supabase.local/.env.supabase file."
    )


def fetch_rows(supa_url: str, supa_key: str, table: str, select: str = "*") -> list[dict[str, Any]]:
    headers = {"apikey": supa_key, "Authorization": f"Bearer {supa_key}"}
    rows: list[dict[str, Any]] = []
    start = 0
    step = 1000
    while True:
        req = Request(
            f"{supa_url}/rest/v1/{table}?select={quote(select, safe='*,():')}",
            headers={**headers, "Range": f"{start}-{start + step - 1}"},
        )
        with urlopen(req, timeout=30) as response:
            batch = json.load(response)
        rows.extend(batch)
        if len(batch) < step:
            return rows
        start += step


def table_count(supa_url: str, supa_key: str, table: str) -> int:
    headers = {
        "apikey": supa_key,
        "Authorization": f"Bearer {supa_key}",
        "Range": "0-0",
        "Prefer": "count=exact",
    }
    req = Request(f"{supa_url}/rest/v1/{table}?select=id", headers=headers)
    with urlopen(req, timeout=30) as response:
        content_range = response.headers.get("Content-Range", "")
    match = re.fullmatch(r"(?:\d+-\d+|\*)/(\d+)", content_range.strip())
    if not match:
        raise RuntimeError(f"Exact row count unavailable for {table}; audit cannot treat it as zero.")
    return int(match.group(1))


def column_exists(supa_url: str, supa_key: str, table: str, column: str) -> bool:
    headers = {"apikey": supa_key, "Authorization": f"Bearer {supa_key}"}
    req = Request(
        f"{supa_url}/rest/v1/{table}?select=id,{quote(column)}&limit=1",
        headers=headers,
    )
    try:
        with urlopen(req, timeout=30):
            return True
    except HTTPError as error:
        if error.code == 400:
            return False
        raise


def edge_text_issues(row: dict[str, Any], row_id: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field in fields:
        value = row.get(field)
        if not isinstance(value, str):
            continue
        if value != value.strip():
            issues.append({"type": "edge-space", "id": row_id, "field": field, "value": value})
        if re.search(r"[ \t]{2,}", value):
            issues.append({"type": "double-space", "id": row_id, "field": field, "value": value})
        if "\ufffd" in value:
            issues.append({"type": "replacement-char", "id": row_id, "field": field})
    return issues


def block_text_issues(row: dict[str, Any], row_id: str, fields: tuple[str, ...]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for field in fields:
        value = row.get(field)
        if not isinstance(value, str):
            continue
        if re.search(r"[ \t]{2,}", value):
            issues.append({"type": "double-space", "id": row_id, "field": field, "value": value})
        if "\ufffd" in value:
            issues.append({"type": "replacement-char", "id": row_id, "field": field})
    return issues


def looks_like_embedded_scripture_body(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    return bool(re.search(r"(?:^|\n)\s*\d{1,3}\s{2,}\S", text))


def normalize_title_key(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE).casefold()


def praise_type_signature(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        values = re.split(r"[,/|]", value)
    else:
        values = []
    return tuple(sorted({str(item).strip().casefold() for item in values if str(item).strip()}))


def explained_canonical_variant_keys(
    row: dict[str, Any],
    *,
    title_collision_count: int,
    praise_types: set[str],
) -> set[str]:
    title_key = normalize_title_key(row.get("title") or "")
    keys: set[str] = set()
    for field in ("subtitle", "original_title", "hymn_no"):
        key = normalize_title_key(row.get(field) or "")
        if key and key != title_key:
            keys.add(key)
    if "children" in praise_types:
        keys.add("children")
    if title_collision_count > 1:
        keys.update(praise_types)
    return keys


def normalize_service_input_mode(value: Any) -> str:
    value = str(value or "").strip()
    aliases = {
        "song": "praise_db",
        "song_db": "praise_db",
        "praise": "praise_db",
        "score": "score_db",
        "lyrics": "lyrics_db",
        "manual": "manual_praise",
        "manual_song": "manual_praise",
    }
    return aliases.get(value, value)


def source_ref_value(row: dict[str, Any], key: str) -> Any:
    source_ref = row.get("source_ref")
    if isinstance(source_ref, dict):
        return source_ref.get(key)
    return None


def input_modes_compatible(left: str, right: str) -> bool:
    if left == right:
        return True
    praise_db_modes = {"praise_db", "lyrics_db", "score_db", "manual_praise"}
    return left in praise_db_modes and right in praise_db_modes


def is_future_auto_placeholder_service(service: dict[str, Any], today: str | None) -> bool:
    if not today:
        return False
    service_date = str(service.get("service_date") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", service_date):
        return False
    source_ref = service.get("source_ref") if isinstance(service.get("source_ref"), dict) else {}
    auto_generated = bool(source_ref.get("auto_generated") or source_ref.get("created_from") == "mindex_auto_schedule")
    return auto_generated and service_date > today


def extend_structural_warnings(
    warnings: list[dict[str, Any]],
    *,
    worship_services: list[dict[str, Any]],
    worship_sections: list[dict[str, Any]],
    worship_elements: list[dict[str, Any]],
    worship_slides: list[dict[str, Any]],
    song_versions: list[dict[str, Any]],
    today: str | None = None,
) -> None:
    services_by_id = {row.get("id"): row for row in worship_services}
    sections_by_id = {row.get("id"): row for row in worship_sections}
    sections_by_service: dict[str, list[dict[str, Any]]] = {}
    elements_by_section: dict[str, list[dict[str, Any]]] = {}
    slides_by_element: dict[str, list[dict[str, Any]]] = {}
    for row in worship_sections:
        if row.get("service_id"):
            sections_by_service.setdefault(row["service_id"], []).append(row)
    for row in worship_elements:
        if row.get("section_id"):
            elements_by_section.setdefault(row["section_id"], []).append(row)
    for row in worship_slides:
        if row.get("element_id"):
            slides_by_element.setdefault(row["element_id"], []).append(row)

    def service_summary(service_id: Any) -> dict[str, Any]:
        service = services_by_id.get(service_id) or {}
        return {
            "service_id": service_id,
            "service_type_id": service.get("service_type_id"),
            "service_date": service.get("service_date"),
            "title": service.get("title"),
            "service_alias": service.get("service_alias"),
        }

    def section_summary(section_id: Any) -> dict[str, Any]:
        section = sections_by_id.get(section_id) or {}
        return {
            **service_summary(section.get("service_id")),
            "section_id": section_id,
            "section_key": section.get("section_key"),
            "section_title": section.get("title"),
        }

    section_order_counts = Counter(
        (row.get("service_id"), row.get("sort_order"))
        for row in worship_sections
        if row.get("service_id") and row.get("sort_order") is not None
    )
    for (service_id, sort_order), count in sorted(section_order_counts.items(), key=lambda item: (str(item[0][0]), item[0][1] or 0)):
        if count <= 1:
            continue
        rows = [
            row for row in worship_sections
            if row.get("service_id") == service_id and row.get("sort_order") == sort_order
        ]
        warnings.append({
            "type": "duplicate-worship-section-order",
            **service_summary(service_id),
            "sort_order": sort_order,
            "count": count,
            "section_ids": [row.get("id") for row in rows],
            "section_keys": [row.get("section_key") for row in rows],
            "section_titles": [row.get("title") for row in rows],
        })

    element_order_counts = Counter(
        (row.get("section_id"), row.get("sort_order"))
        for row in worship_elements
        if row.get("section_id") and row.get("sort_order") is not None
    )
    for (section_id, sort_order), count in sorted(element_order_counts.items(), key=lambda item: (str(item[0][0]), item[0][1] or 0)):
        if count <= 1:
            continue
        rows = [
            row for row in worship_elements
            if row.get("section_id") == section_id and row.get("sort_order") == sort_order
        ]
        warnings.append({
            "type": "duplicate-worship-element-order",
            **section_summary(section_id),
            "sort_order": sort_order,
            "count": count,
            "element_ids": [row.get("id") for row in rows],
            "element_types": [row.get("element_type") for row in rows],
            "element_titles": [row.get("title") for row in rows],
        })

    slide_order_counts = Counter(
        (row.get("element_id"), row.get("sort_order"))
        for row in worship_slides
        if row.get("element_id") and row.get("sort_order") is not None
    )
    for (element_id, sort_order), count in sorted(slide_order_counts.items(), key=lambda item: (str(item[0][0]), item[0][1] or 0)):
        if count <= 1:
            continue
        rows = [
            row for row in worship_slides
            if row.get("element_id") == element_id and row.get("sort_order") == sort_order
        ]
        warnings.append({
            "type": "duplicate-worship-slide-order",
            "element_id": element_id,
            "sort_order": sort_order,
            "count": count,
            "slide_ids": [row.get("id") for row in rows],
            "slide_types": [row.get("slide_type") for row in rows],
        })

    for service in worship_services:
        if source_ref_value(service, "no_gathering"):
            continue
        if is_future_auto_placeholder_service(service, today):
            continue
        if not sections_by_service.get(service.get("id")):
            warnings.append({
                "type": "worship-service-without-sections",
                **service_summary(service.get("id")),
                "created_from": source_ref_value(service, "created_from"),
                "auto_generated": bool(source_ref_value(service, "auto_generated")),
            })

    for section in worship_sections:
        if not elements_by_section.get(section.get("id")):
            warnings.append({
                "type": "worship-section-without-elements",
                **section_summary(section.get("id")),
                "sort_order": section.get("sort_order"),
            })

    version_source_by_id = {
        row.get("id"): row.get("source_song_id")
        for row in song_versions
        if row.get("id")
    }
    for element in worship_elements:
        input_mode = normalize_service_input_mode(element.get("input_mode"))
        content_state = element.get("content_state") if isinstance(element.get("content_state"), dict) else {}
        content_mode = normalize_service_input_mode(content_state.get("inputMode") or content_state.get("input_mode"))
        if input_mode and content_mode and not input_modes_compatible(input_mode, content_mode):
            warnings.append({
                "type": "worship-element-input-mode-state-mismatch",
                **section_summary(element.get("section_id")),
                "element_id": element.get("id"),
                "element_type": element.get("element_type"),
                "element_title": element.get("title"),
                "input_mode": input_mode,
                "content_state_input_mode": content_mode,
            })

        song_id = element.get("song_id")
        version_id = element.get("song_version_id")
        if song_id and version_id:
            version_source_id = version_source_by_id.get(version_id)
            if version_source_id and version_source_id != song_id:
                warnings.append({
                    "type": "worship-element-song-version-source-mismatch",
                    **section_summary(element.get("section_id")),
                    "element_id": element.get("id"),
                    "element_title": element.get("title"),
                    "song_id": song_id,
                    "song_version_id": version_id,
                    "version_source_song_id": version_source_id,
                })
        if input_mode in {"praise_db", "lyrics_db", "score_db"} and song_id and not version_id:
            warnings.append({
                "type": "worship-element-linked-song-without-version",
                **section_summary(element.get("section_id")),
                "element_id": element.get("id"),
                "element_type": element.get("element_type"),
                "element_title": element.get("title"),
                "song_id": song_id,
                "input_mode": input_mode,
            })


def audit(
    supa_url: str,
    supa_key: str,
    *,
    strict_schema: bool = False,
    structural: bool = False,
    today: str | None = None,
) -> tuple[dict[str, int], list[dict[str, Any]], list[dict[str, Any]]]:
    songs = fetch_rows(supa_url, supa_key, "mindex_songs")
    canonical_songs = fetch_rows(supa_url, supa_key, "mindex_canonical_songs")
    song_versions = fetch_rows(supa_url, supa_key, "mindex_song_versions")
    version_units = fetch_rows(supa_url, supa_key, "mindex_version_units")
    scriptures = fetch_rows(supa_url, supa_key, "mindex_scriptures")
    books = fetch_rows(supa_url, supa_key, "mindex_scripture_books")
    worship_service_types = fetch_rows(supa_url, supa_key, "mindex_worship_service_types")
    worship_services = fetch_rows(supa_url, supa_key, "mindex_worship_services")
    worship_sections = fetch_rows(supa_url, supa_key, "mindex_worship_sections")
    worship_elements = fetch_rows(supa_url, supa_key, "mindex_worship_elements")
    worship_slides = fetch_rows(supa_url, supa_key, "mindex_worship_slides")
    translations = fetch_rows(supa_url, supa_key, "mindex_bible_translations")
    verse_count = table_count(supa_url, supa_key, "mindex_bible_verses")

    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    song_ids = {row["id"] for row in songs}
    canonical_song_ids = {row["id"] for row in canonical_songs}
    song_versions_by_id: dict[str, dict[str, Any]] = {}
    for row in song_versions:
        # Preserve the first-match behavior even for malformed duplicate IDs.
        song_versions_by_id.setdefault(row["id"], row)
    song_version_ids = set(song_versions_by_id)
    scripture_ids = {row["id"] for row in scriptures}
    worship_service_ids = {row["id"] for row in worship_services}
    worship_service_type_ids = {row["id"] for row in worship_service_types}
    worship_section_ids = {row["id"] for row in worship_sections}
    worship_element_ids = {row["id"] for row in worship_elements}
    book_codes = {row["code"] for row in books}
    translation_ids = {row["id"] for row in translations}
    praise_types_by_canonical_id: dict[str, set[str]] = {}
    for row in song_versions:
        canonical_id = row.get("canonical_song_id")
        if canonical_id:
            praise_types_by_canonical_id.setdefault(canonical_id, set()).update(praise_type_signature(row.get("praise_types")))

    if strict_schema:
        optional_columns = (
            ("mindex_song_versions", "praise_types"),
        )
        for table, column in optional_columns:
            if not column_exists(supa_url, supa_key, table, column):
                warnings.append({"type": "missing-optional-column", "table": table, "column": column})

    seen_song_keys: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in songs:
        row_id = row["id"]
        title = row.get("title") or ""
        normalized = title.strip().casefold()
        if normalized:
            identity = (
                normalized,
                (row.get("subtitle") or "").strip().casefold(),
                (row.get("original_title") or "").strip().casefold(),
            )
            seen_song_keys.setdefault(identity, []).append(row)
        if TEST_PATTERNS.search(title):
            issues.append({"type": "testish-song-title", "id": row_id, "title": title})
        if row.get("hymn_no") and re.match(r"^\s*(?:통\s*)?\d{1,3}\s+\S+", title):
            warnings.append({"type": "song-title-contains-hymn-no", "id": row_id, "title": title, "hymn_no": row.get("hymn_no")})
        issues.extend(edge_text_issues(row, row_id, ("title", "subtitle", "original_title", "hymn_no")))
        warnings.extend(edge_text_issues(row, row_id, ("memo",)))

    for (title, subtitle, original_title), rows in seen_song_keys.items():
        if len(rows) > 1:
            hymn_numbers = [(row.get("hymn_no") or "").strip() for row in rows]
            if all(hymn_numbers) and len(set(hymn_numbers)) == len(hymn_numbers):
                continue
            praise_type_signatures = {praise_type_signature(row.get("praise_types")) for row in rows}
            if len(praise_type_signatures) > 1:
                continue
            ids = [row["id"] for row in rows]
            warnings.append({
                "type": "duplicate-song-identity",
                "title": title,
                "subtitle": subtitle,
                "original_title": original_title,
                "ids": ids,
                "count": len(ids),
            })

    canonical_title_key_rows: dict[str, list[dict[str, Any]]] = {}
    for row in canonical_songs:
        title_key = normalize_title_key(row.get("title") or "")
        if title_key:
            canonical_title_key_rows.setdefault(title_key, []).append(row)

    normalized_canonical_keys: dict[str, list[dict[str, Any]]] = {}
    for row in canonical_songs:
        row_id = row["id"]
        title = row.get("title") or ""
        normalized_title = row.get("normalized_title") or ""
        expected_title_key = normalize_title_key(title)
        normalized_canonical_keys.setdefault(normalized_title, []).append(row)
        if not title:
            issues.append({"type": "canonical-song-title-missing", "id": row_id})
        if not normalized_title:
            issues.append({"type": "canonical-song-normalized-title-missing", "id": row_id, "title": title})
        elif "::" not in normalized_title and normalized_title != expected_title_key:
            warnings.append({
                "type": "canonical-normalized-title-differs-from-title",
                "id": row_id,
                "title": title,
                "normalized_title": normalized_title,
                "expected": expected_title_key,
            })
        if "::" in normalized_title:
            base, variant = normalized_title.split("::", 1)
            if not base or not variant:
                issues.append({"type": "canonical-variant-key-malformed", "id": row_id, "normalized_title": normalized_title})
            elif base != expected_title_key:
                issues.append({
                    "type": "canonical-variant-key-base-mismatch",
                    "id": row_id,
                    "title": title,
                    "normalized_title": normalized_title,
                    "expected_base": expected_title_key,
                })
            elif normalize_title_key(variant) != variant:
                issues.append({"type": "canonical-variant-key-malformed", "id": row_id, "normalized_title": normalized_title})
            elif variant not in explained_canonical_variant_keys(
                row,
                title_collision_count=len(canonical_title_key_rows.get(expected_title_key, [])),
                praise_types=praise_types_by_canonical_id.get(row_id, set()),
            ):
                warnings.append({
                    "type": "canonical-variant-key-unexplained",
                    "id": row_id,
                    "title": title,
                    "normalized_title": normalized_title,
                })
        issues.extend(edge_text_issues(row, row_id, ("title", "subtitle", "original_title", "hymn_no", "normalized_title")))

    for normalized_title, rows in normalized_canonical_keys.items():
        if normalized_title and len(rows) > 1:
            issues.append({
                "type": "duplicate-canonical-normalized-title",
                "normalized_title": normalized_title,
                "ids": [row["id"] for row in rows],
            })

    for row in song_versions:
        row_id = row["id"]
        canonical_id = row.get("canonical_song_id")
        source_id = row.get("source_song_id")
        if canonical_id not in canonical_song_ids:
            issues.append({"type": "song-version-missing-canonical-song", "id": row_id, "canonical_song_id": canonical_id})
        if source_id and source_id not in song_ids:
            issues.append({"type": "song-version-missing-source-song", "id": row_id, "source_song_id": source_id})
        issues.extend(edge_text_issues(row, row_id, ("version_label", "subtitle", "original_title", "lyric_signature")))

    for row in version_units:
        row_id = row["id"]
        version_id = row.get("version_id")
        canonical_id = row.get("canonical_song_id")
        if version_id not in song_version_ids:
            issues.append({"type": "version-unit-missing-version", "id": row_id, "version_id": version_id})
        if canonical_id and canonical_id not in canonical_song_ids:
            issues.append({"type": "version-unit-missing-canonical-song", "id": row_id, "canonical_song_id": canonical_id})
        issues.extend(edge_text_issues(row, row_id, ("unit_label", "unit_kind")))
        warnings.extend(block_text_issues(row, row_id, ("text",)))

    for row in scriptures:
        row_id = row["id"]
        if row.get("book_code") and row.get("book_code") not in book_codes:
            issues.append({"type": "scripture-missing-book", "id": row_id, "book_code": row.get("book_code")})
        issues.extend(edge_text_issues(row, row_id, ("title", "book", "reference", "translation")))
        warnings.extend(edge_text_issues(row, row_id, ("text", "memo")))

    for row in books:
        code = row["code"]
        if not row.get("korean_name") or not row.get("english_name"):
            issues.append({"type": "book-name-missing", "code": code})
        issues.extend(edge_text_issues(row, code, ("korean_name", "english_name", "short_name", "testament")))

    for row in worship_services:
        row_id = row["id"]
        if row.get("service_type_id") not in worship_service_type_ids:
            issues.append({"type": "worship-service-missing-type", "id": row_id, "service_type_id": row.get("service_type_id")})
        issues.extend(edge_text_issues(row, row_id, ("title", "worship_leader", "praise_leader")))
        warnings.extend(block_text_issues(row, row_id, ("notes",)))

    for row in worship_sections:
        row_id = row["id"]
        if row.get("service_id") not in worship_service_ids:
            issues.append({"type": "worship-section-missing-service", "id": row_id, "service_id": row.get("service_id")})
        issues.extend(edge_text_issues(row, row_id, ("section_key", "title", "person")))

    for row in worship_elements:
        row_id = row["id"]
        if row.get("section_id") not in worship_section_ids:
            issues.append({"type": "worship-element-missing-section", "id": row_id, "section_id": row.get("section_id")})
        if row.get("song_id") and row.get("song_id") not in song_ids:
            issues.append({"type": "worship-element-missing-song", "id": row_id, "song_id": row.get("song_id"), "title": row.get("title")})
        if row.get("song_version_id") and row.get("song_version_id") not in song_version_ids:
            issues.append({"type": "worship-element-missing-song-version", "id": row_id, "song_version_id": row.get("song_version_id"), "title": row.get("title")})
        if row.get("song_id") and row.get("song_version_id"):
            version = song_versions_by_id.get(row.get("song_version_id"))
            if version and version.get("source_song_id") and version.get("source_song_id") != row.get("song_id"):
                warnings.append({
                    "type": "worship-element-song-version-source-mismatch",
                    "id": row_id,
                    "song_id": row.get("song_id"),
                    "song_version_id": row.get("song_version_id"),
                    "version_source_song_id": version.get("source_song_id"),
                    "title": row.get("title"),
                })
        if row.get("scripture_id") and row.get("scripture_id") not in scripture_ids:
            issues.append({"type": "worship-element-missing-scripture", "id": row_id, "scripture_id": row.get("scripture_id"), "title": row.get("title")})
        if row.get("element_type") == "scripture_body":
            if looks_like_embedded_scripture_body(row.get("title")):
                issues.append({"type": "scripture-body-title-contains-verses", "id": row_id, "title": row.get("title")})
            if looks_like_embedded_scripture_body(row.get("body")):
                issues.append({"type": "scripture-body-body-contains-verses", "id": row_id})
            config = row.get("config") if isinstance(row.get("config"), dict) else {}
            config_slides = config.get("slides") or config.get("slideOverrides") or config.get("slide_overrides")
            if isinstance(config_slides, list) and any(looks_like_embedded_scripture_body(slide) for slide in config_slides):
                issues.append({"type": "scripture-body-config-contains-verses", "id": row_id})
        issues.extend(edge_text_issues(row, row_id, ("element_type", "title", "person", "scripture_reference")))
        warnings.extend(block_text_issues(row, row_id, ("body",)))

    for row in worship_slides:
        row_id = row["id"]
        if row.get("element_id") not in worship_element_ids:
            issues.append({"type": "worship-slide-missing-element", "id": row_id, "element_id": row.get("element_id")})
        issues.extend(edge_text_issues(row, row_id, ("slide_type", "title", "marker")))
        warnings.extend(block_text_issues(row, row_id, ("body",)))

    if structural:
        extend_structural_warnings(
            warnings,
            worship_services=worship_services,
            worship_sections=worship_sections,
            worship_elements=worship_elements,
            worship_slides=worship_slides,
            song_versions=song_versions,
            today=today,
        )

    for row in translations:
        row_id = row["id"]
        if not row.get("translation_key") or not row.get("name"):
            issues.append({"type": "translation-name-missing", "id": row_id})
        issues.extend(edge_text_issues(row, row_id, ("translation_key", "name", "language", "abbreviation", "source", "license")))

    counts = {
        "songs": len(songs),
        "canonical_songs": len(canonical_songs),
        "song_versions": len(song_versions),
        "version_units": len(version_units),
        "scriptures": len(scriptures),
        "scripture_books": len(books),
        "worship_service_types": len(worship_service_types),
        "worship_services": len(worship_services),
        "worship_sections": len(worship_sections),
        "worship_elements": len(worship_elements),
        "worship_slides": len(worship_slides),
        "bible_translations": len(translations),
        "bible_verses": verse_count,
        "linked_translation_ids": len(translation_ids),
    }
    return counts, issues, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Mindex Supabase content for residue and reference issues.")
    parser.add_argument("--json", action="store_true", help="Print all issues and warnings as JSON.")
    parser.add_argument("--strict-schema", action="store_true", help="Warn about optional schema columns that the app can otherwise tolerate.")
    parser.add_argument("--structural", action="store_true", help="Also warn about operational data-structure drift, such as duplicate worship ordering.")
    parser.add_argument("--today", default=date.today().isoformat(), help="YYYY-MM-DD boundary for future auto-generated placeholder services.")
    args = parser.parse_args()

    counts, issues, warnings = audit(*read_config(), strict_schema=args.strict_schema, structural=args.structural, today=args.today)
    if args.json:
        print(json.dumps({"counts": counts, "issues": issues, "warnings": warnings}, ensure_ascii=False, indent=2))
    else:
        print("counts:", json.dumps(counts, ensure_ascii=False, sort_keys=True))
        print(f"issues: {len(issues)}")
        for issue in issues[:50]:
            print(json.dumps(issue, ensure_ascii=False))
        if len(issues) > 50:
            print(f"... {len(issues) - 50} more issues")
        print(f"warnings: {len(warnings)}")
        warning_types: dict[str, int] = {}
        for warning in warnings:
            warning_types[warning["type"]] = warning_types.get(warning["type"], 0) + 1
        if warning_types:
            print("warning_types:", json.dumps(warning_types, ensure_ascii=False, sort_keys=True))
        for warning in warnings[:20]:
            print(json.dumps(warning, ensure_ascii=False))
        if len(warnings) > 20:
            print(f"... {len(warnings) - 20} more warnings")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
