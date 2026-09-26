import json
import re
import unittest
from pathlib import Path


class ElectronRuntimeFilesTests(unittest.TestCase):
    def test_top_level_runtime_scripts_are_packaged(self):
        root = Path(__file__).resolve().parents[1]
        includes = json.loads((root / 'package.json').read_text())['build']['files']
        index_html = (root / 'index.html').read_text()
        static_scripts = re.findall(r'<script src="\./([^?"/]+\.js)', index_html)
        runtime_scripts = re.findall(r'"(mindex(?:\.[A-Za-z0-9_-]+)+\.js|app\.js)"', index_html)
        scripts = sorted(set(static_scripts + runtime_scripts))
        for script in scripts:
            with self.subTest(script=script):
                packaged_by_glob = script.startswith('vendor/') and 'vendor/**/*' in includes
                self.assertTrue(script in includes or packaged_by_glob)
                self.assertTrue((root / script).is_file())

    def test_release_manifest_is_packaged_and_matches_loader_fallback(self):
        root = Path(__file__).resolve().parents[1]
        includes = json.loads((root / 'package.json').read_text())['build']['files']
        manifest = root / 'mindex-release.json'
        index_html = (root / 'index.html').read_text()

        self.assertIn('mindex-release.json', includes)
        version = json.loads(manifest.read_text())['version']
        self.assertRegex(version, r'^[0-9A-Za-z._-]{4,80}$')
        self.assertIn(f'const fallbackVersion = "{version}"', index_html)


if __name__ == '__main__':
    unittest.main()
