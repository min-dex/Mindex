"""Offline operation-count regression; no timing claims or Supabase requests."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import audit_mindex_content as audit


class CountingRows(list):
    def __init__(self, rows):
        super().__init__(rows)
        self.visits = 0

    def __iter__(self):
        for row in super().__iter__():
            self.visits += 1
            yield row


def run_fixture(versions, elements):
    tables = {
        'mindex_songs': [{'id': 'a', 'title': 'Alpha'}, {'id': 'b', 'title': 'Beta'}],
        'mindex_canonical_songs': [{'id': 'c', 'title': 'Canonical', 'normalized_title': 'canonical'}],
        'mindex_song_versions': versions,
        'mindex_worship_service_types': [{'id': 'type'}],
        'mindex_worship_services': [{'id': 'service', 'service_type_id': 'type'}],
        'mindex_worship_sections': [{'id': 'section', 'service_id': 'service'}],
        'mindex_worship_elements': elements,
    }
    with patch.object(audit, 'fetch_rows', side_effect=lambda _u, _k, table, *args: tables.get(table, [])), \
         patch.object(audit, 'table_count', return_value=0), \
         patch.object(audit, 'column_exists', return_value=True), \
         patch.object(audit, 'urlopen', side_effect=AssertionError('live I/O forbidden')):
        return audit.audit('https://example.invalid', 'synthetic-key')


class VersionLookupCostTest(unittest.TestCase):
    def test_version_scan_cost_does_not_multiply_by_element_count(self):
        for version_count, element_count in [(100, 200), (200, 400)]:
            with self.subTest(versions=version_count, elements=element_count):
                versions = CountingRows([{'id': f'v{i}', 'canonical_song_id': 'c', 'source_song_id': 'a'}
                                         for i in range(version_count)])
                elements = [{'id': f'e{i}', 'section_id': 'section', 'song_id': 'b',
                             'song_version_id': f'v{version_count-1}', 'title': 'Praise'}
                            for i in range(element_count)]
                counts, issues, warnings = run_fixture(versions, elements)
                self.assertEqual(issues, [])
                self.assertEqual(counts['song_versions'], version_count)
                self.assertEqual(counts['worship_elements'], element_count)
                self.assertEqual(warnings, [{'type': 'worship-element-song-version-source-mismatch',
                    'id': f'e{i}', 'song_id': 'b', 'song_version_id': f'v{version_count-1}',
                    'version_source_song_id': 'a', 'title': 'Praise'} for i in range(element_count)])
                print(f'versions={version_count} elements={element_count} version_row_visits={versions.visits}')
                self.assertLessEqual(versions.visits, 3 * version_count, 'per-element full scans returned')

    def test_first_duplicate_and_missing_reference_semantics_are_preserved(self):
        versions = CountingRows([{'id': 'same', 'canonical_song_id': 'c', 'source_song_id': 'a'},
                                 {'id': 'same', 'canonical_song_id': 'c', 'source_song_id': 'b'}])
        elements = [{'id': 'e', 'section_id': 'section', 'song_id': 'a', 'song_version_id': 'same'},
                    {'id': 'missing', 'section_id': 'section', 'song_id': 'a', 'song_version_id': 'absent'}]
        _, issues, warnings = run_fixture(versions, elements)
        self.assertEqual(warnings, [])
        self.assertEqual(issues, [{'type': 'worship-element-missing-song-version', 'id': 'missing',
                                  'song_version_id': 'absent', 'title': None}])


if __name__ == '__main__':
    unittest.main()
