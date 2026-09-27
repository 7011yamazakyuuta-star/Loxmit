import json
import re
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

from app import Library


ROOT = Path(__file__).resolve().parents[1]


class CatalogMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.keys = []

    def handle_starttag(self, tag, attrs):
        self.keys.extend(value for key, value in attrs if key.startswith('data-i18n'))


class TranslationTests(unittest.TestCase):
    def test_catalog_covers_markup_and_literal_calls(self):
        duplicates = []
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    duplicates.append(key)
                result[key] = value
            return result
        raw = (ROOT / 'static/messages-en.js').read_text(encoding='utf-8')
        catalog = json.loads(raw[raw.index('{'):raw.rindex('}') + 1], object_pairs_hook=pairs)
        self.assertEqual(duplicates, [])
        markup = CatalogMarkup()
        markup.feed((ROOT / 'static/index.html').read_text(encoding='utf-8'))
        missing = set(markup.keys) - set(catalog)
        for file in ('app.js', 'setup.js'):
            source = (ROOT / 'static' / file).read_text(encoding='utf-8')
            for key in re.findall(r"t\('([^'\n]*)'", source):
                if re.search(r'[\u3040-\u9fff]', key) and key not in catalog:
                    missing.add(key)
            for template in re.findall(r't`([^`]*)`', source):
                index = iter(range(30))
                key = re.sub(r'\$\{[^}]*\}', lambda _: '{' + str(next(index)) + '}', template)
                if key not in catalog:
                    missing.add(key)
        self.assertEqual(sorted(missing), [])
        for key, value in catalog.items():
            self.assertTrue(value.strip(), key)
            self.assertEqual(sorted(re.findall(r'\{\d+\}', key)), sorted(re.findall(r'\{\d+\}', value)), key)

    def test_language_persists_without_touching_engine_or_jobs(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Library(directory)
            try:
                self.assertEqual(library.language, 'auto')
                with patch.object(library.setup, 'diagnose', side_effect=AssertionError('No GPU side effect')):
                    self.assertEqual(library.save_language({'language': 'en'}), {'language': 'en'})
                self.assertFalse((Path(directory) / 'settings.json').exists())
                self.assertEqual(library.jobs, {})
                for invalid in ({}, {'language': 'fr'}, {'language': ['en']}, {'language': 'ja', 'hashcat': 'other'}):
                    with self.assertRaises(ValueError):
                        library.save_language(invalid)
                self.assertEqual(library.language, 'en')
            finally:
                library.close()
            restored = Library(directory)
            try:
                self.assertEqual(restored.language, 'en')
            finally:
                restored.close()

    def test_corrupt_preference_uses_browser_default(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'language.json').write_text('[]', encoding='utf-8')
            library = Library(directory)
            try:
                self.assertEqual(library.language, 'auto')
            finally:
                library.close()


if __name__ == '__main__':
    unittest.main()
