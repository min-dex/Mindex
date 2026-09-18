import sys
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import audit_mindex_content  # type: ignore  # noqa: E402


class AuditMindexContentTest(unittest.TestCase):
    def test_count_requires_an_exact_total(self):
        for header, expected in [('0-0/12', 12), ('*/0', 0), ('0-0/0', 0)]:
            response = MagicMock()
            response.__enter__.return_value.headers = {'Content-Range': header}
            with patch.object(audit_mindex_content, 'urlopen', return_value=response):
                self.assertEqual(audit_mindex_content.table_count('https://example.test', 'fake', 'fixture'), expected)
        for header in ['', '0-0/*', 'garbage/17', '0-0/-1']:
            response = MagicMock()
            response.__enter__.return_value.headers = {'Content-Range': header}
            with patch.object(audit_mindex_content, 'urlopen', return_value=response):
                with self.assertRaisesRegex(RuntimeError, 'count unavailable'):
                    audit_mindex_content.table_count('https://example.test', 'fake', 'fixture')

    def test_structural_warnings_find_worship_order_drift(self):
        warnings = []

        audit_mindex_content.extend_structural_warnings(
            warnings,
            worship_services=[
                {
                    "id": "svc-1",
                    "service_type_id": "sun_1st",
                    "service_date": "2026-08-16",
                    "title": "주일예배 [1부]",
                    "service_alias": "",
                    "source_ref": {},
                },
                {
                    "id": "svc-empty",
                    "service_type_id": "wed",
                    "service_date": "2026-08-19",
                    "title": "수요예배",
                    "service_alias": "",
                    "source_ref": {"created_from": "mindex_auto_schedule", "auto_generated": True},
                },
                {
                    "id": "svc-future-empty",
                    "service_type_id": "sun_1st",
                    "service_date": "2026-08-30",
                    "title": "주일예배 [1부]",
                    "service_alias": "",
                    "source_ref": {"created_from": "mindex_auto_schedule", "auto_generated": True},
                },
                {
                    "id": "svc-no-gathering",
                    "service_type_id": "fri",
                    "service_date": "2026-08-14",
                    "title": "문화예배",
                    "service_alias": "문화예배",
                    "source_ref": {"no_gathering": True},
                },
            ],
            worship_sections=[
                {"id": "sec-1", "service_id": "svc-1", "sort_order": 1, "section_key": "ready", "title": "준비"},
                {"id": "sec-2", "service_id": "svc-1", "sort_order": 1, "section_key": "praise", "title": "찬양"},
                {"id": "sec-empty", "service_id": "svc-1", "sort_order": 2, "section_key": "sermon", "title": "설교"},
            ],
            worship_elements=[
                {
                    "id": "el-1",
                    "section_id": "sec-1",
                    "sort_order": 1,
                    "element_type": "praise",
                    "title": "찬양",
                    "input_mode": "praise_db",
                    "content_state": {"inputMode": "text"},
                },
                {
                    "id": "el-2",
                    "section_id": "sec-1",
                    "sort_order": 1,
                    "element_type": "praise",
                    "title": "찬양 2",
                    "input_mode": "lyrics_db",
                    "content_state": {"inputMode": "lyrics_db"},
                    "song_id": "song-1",
                },
            ],
            worship_slides=[],
            song_versions=[],
            today="2026-08-27",
        )

        warning_types = [warning["type"] for warning in warnings]
        self.assertIn("duplicate-worship-section-order", warning_types)
        self.assertIn("duplicate-worship-element-order", warning_types)
        self.assertIn("worship-service-without-sections", warning_types)
        self.assertIn("worship-section-without-elements", warning_types)
        self.assertIn("worship-element-input-mode-state-mismatch", warning_types)
        self.assertIn("worship-element-linked-song-without-version", warning_types)
        self.assertTrue(audit_mindex_content.input_modes_compatible("praise_db", "manual_praise"))

        empty_services = [
            warning for warning in warnings
            if warning["type"] == "worship-service-without-sections"
        ]
        self.assertEqual([warning["service_id"] for warning in empty_services], ["svc-empty"])


if __name__ == "__main__":
    unittest.main()
