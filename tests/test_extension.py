"""Compile the shipped parser and exercise the actual Zed queries."""

import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

from tree_sitter import Language, Parser, Query, QueryCursor

ROOT = Path(__file__).resolve().parents[1]


class ExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        library = Path(cls.temp.name) / "wake.so"
        subprocess.run(
            [os.environ.get("CC", "cc"), "-shared", "-fPIC", "-std=c11",
             "-I", str(ROOT / "grammar/src"),
             str(ROOT / "grammar/src/parser.c"),
             str(ROOT / "grammar/src/scanner.c"), "-o", str(library)],
            check=True,
        )
        cls.library = ctypes.CDLL(str(library))
        cls.library.tree_sitter_wake.restype = ctypes.c_void_p
        capsule_new = ctypes.pythonapi.PyCapsule_New
        capsule_new.restype = ctypes.py_object
        capsule_new.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
        capsule = capsule_new(cls.library.tree_sitter_wake(), b"tree_sitter.Language", None)
        cls.language = Language(capsule)
        cls.parser = Parser(cls.language)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def captures(self, query_name, source):
        query = Query(self.language, (ROOT / f"languages/wake/{query_name}.scm").read_text())
        return QueryCursor(query).captures(self.parser.parse(source).root_node)

    def test_language_configuration(self):
        config = tomllib.loads((ROOT / "languages/wake/config.toml").read_text())
        self.assertEqual(config["grammar"], "wake")
        self.assertIn("wake", config["path_suffixes"])
        self.assertEqual(config["line_comments"], ["# "])

    def test_extension_manifest(self):
        manifest = tomllib.loads((ROOT / "extension.toml").read_text())
        self.assertEqual(manifest["schema_version"], 1)
        grammar = manifest["grammars"]["wake"]
        self.assertEqual(grammar["path"], "grammar")
        self.assertRegex(grammar["rev"], r"^[0-9a-f]{40}$")
        self.assertTrue((ROOT / grammar["path"] / "src/parser.c").is_file())

    def test_examples_parse_without_errors(self):
        for path in sorted((ROOT / "examples").glob("*.wake")):
            with self.subTest(path=path.name):
                tree = self.parser.parse(path.read_bytes())
                self.assertFalse(tree.root_node.has_error, str(tree.root_node))

    def test_all_queries_compile(self):
        for path in sorted((ROOT / "languages/wake").glob("*.scm")):
            with self.subTest(query=path.name):
                Query(self.language, path.read_text())

    def test_highlight_categories(self):
        captures = self.captures("highlights", (ROOT / "examples/syntax.wake").read_bytes())
        expected = {
            "keyword": b"require",
            "number": b"42", "string": b"'raw string'", "function": b"greet",
            "type": b"Integer", "boolean": b"True", "constructor": b"Some",
            "property": b"X", "string.regex": b"`.*\\.wake$`", "embedded": b"who",
        }
        for category, text in expected.items():
            with self.subTest(category=category):
                self.assertIn(text, [node.text for node in captures.get(category, [])])
        self.assertTrue(any(n.text.startswith(b"# Syntax showcase")
                            for n in captures["comment"]))

    def test_outline_names(self):
        captures = self.captures("outline", (ROOT / "examples/syntax.wake").read_bytes())
        names = {node.text for node in captures["name"]}
        self.assertTrue({b"showcase", b"greet who", b"Color", b"Point", b"X", b"Y",
                         b"events", b"hello", b"suffix"}.issubset(names), names)

    def test_parenthesis_pair(self):
        source = b'package test\ndef value = (1 + 2)\n'
        captures = self.captures("brackets", source)
        self.assertEqual([n.text for n in captures["open"]], [b"("])
        self.assertEqual([n.text for n in captures["close"]], [b")"])

    def test_incomplete_input_recovers(self):
        source = b'package test\ndef broken = (\ndef after = 42\n'
        tree = self.parser.parse(source)
        self.assertTrue(tree.root_node.has_error)
        self.assertIn(b"def", [n.text for n in self.captures("highlights", source)["keyword"]])

    def test_unterminated_string_does_not_hang(self):
        # Run separately so a scanner regression fails instead of hanging CI.
        script = (
            "import ctypes; from tree_sitter import Language, Parser; "
            f"lib=ctypes.CDLL({str(Path(self.temp.name) / 'wake.so')!r}); "
            "lib.tree_sitter_wake.restype=ctypes.c_void_p; "
            "new=ctypes.pythonapi.PyCapsule_New; new.restype=ctypes.py_object; "
            "new.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_void_p]; "
            "p=Parser(Language(new(lib.tree_sitter_wake(), b'tree_sitter.Language', None))); "
            "assert p.parse(b'package test\\ndef value = \\\"unfinished').root_node.has_error"
        )
        import sys
        subprocess.run([sys.executable, "-c", script], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
