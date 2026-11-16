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
        config = tomllib.loads((ROOT / "languages/wake/config.toml").read_text())
        self.assertIn(config["name"], manifest["language_servers"]["wake"]["languages"])
        cargo = tomllib.loads((ROOT / "Cargo.toml").read_text())
        self.assertEqual(manifest["version"], cargo["package"]["version"])

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

    def test_multiline_strings_close_before_following_definitions(self):
        source = (ROOT / "examples/multiline.wake").read_bytes()
        tree = self.parser.parse(source)
        self.assertFalse(tree.root_node.has_error, str(tree.root_node))
        captures = self.captures("highlights", source)
        strings = captures["string"]
        for marker in [b"def after", b"def finished"]:
            position = source.index(marker)
            self.assertFalse(any(n.start_byte <= position < n.end_byte for n in strings))
            self.assertIn(position, [n.start_byte for n in captures["keyword"]])
        self.assertEqual(len([n for n in strings if n.text.startswith(b'"""')]), 2)

    def test_multiline_interpolation_does_not_capture_shell_braces(self):
        source = (ROOT / "examples/multiline.wake").read_bytes()
        captures = self.captures("highlights", source)
        embedded = [n.text for n in captures.get("embedded", [])]
        self.assertIn(b'format "hello {name}"', embedded)
        self.assertIn(b"format name", embedded)
        self.assertNotIn(b" echo 'missing source'; exit 1; ", embedded)

    def test_legacy_heredoc_and_empty_strings_still_parse(self):
        source = (b'package test\ndef empty = ""\ndef old = "%\n'
                  b'  echo %{format "nested"}\n%"\ndef after = 42\n')
        tree = self.parser.parse(source)
        self.assertFalse(tree.root_node.has_error, str(tree.root_node))
        captures = self.captures("highlights", source)
        self.assertIn(b'""', [n.text.strip() for n in captures["string"]])
        self.assertIn(b'format "nested"', [n.text for n in captures["embedded"]])
        after = source.index(b"def after")
        self.assertFalse(any(n.start_byte <= after < n.end_byte for n in captures["string"]))

    def test_multiline_empty_crlf_and_indentation(self):
        for body in [b"", b'  echo "quoted" {raw} \\\n', b"  Unicode: \xe4\xb8\xad\xe6\x96\x87\n"]:
            for newline in [b"\n", b"\r\n"]:
                source = (b'package test\ndef value =\n  """\n' + body
                          + b'  """\ndef after = 42\n').replace(b"\n", newline)
                with self.subTest(body=body, newline=newline):
                    tree = self.parser.parse(source)
                    self.assertFalse(tree.root_node.has_error, str(tree.root_node))
                    strings = self.captures("highlights", source)["string"]
                    self.assertEqual(len(strings), 1)
                    self.assertTrue(strings[0].text.startswith(b'"""'))
                    after = source.index(b"def after")
                    self.assertFalse(any(n.start_byte <= after < n.end_byte for n in strings))

    def test_multiline_incremental_edit_keeps_following_code_outside_string(self):
        source = b'package test\ndef script =\n  """\n  echo "hello"\n  """\ndef after = 42\n'
        tree = self.parser.parse(source)
        at = source.index(b"hello")
        row = source[:at].count(b"\n")
        column = at - source.rfind(b"\n", 0, at) - 1
        tree.edit(start_byte=at, old_end_byte=at + 5, new_end_byte=at + 5,
                  start_point=(row, column), old_end_point=(row, column + 5),
                  new_end_point=(row, column + 5))
        edited = source[:at] + b"world" + source[at + 5:]
        updated = self.parser.parse(edited, tree)
        self.assertFalse(updated.root_node.has_error, str(updated.root_node))
        self.assertEqual(str(updated.root_node), str(self.parser.parse(edited).root_node))
        query = Query(self.language, (ROOT / "languages/wake/highlights.scm").read_text())
        strings = QueryCursor(query).captures(updated.root_node)["string"]
        after = edited.index(b"def after")
        self.assertFalse(any(n.start_byte <= after < n.end_byte for n in strings))

    def test_multiline_closing_delimiter_can_be_deleted_and_restored(self):
        source = b'package test\ndef script =\n  """\n  echo "hello"\n  """\ndef after = 42\n'
        tree = self.parser.parse(source)
        at = source.rindex(b'"""')
        row = source[:at].count(b"\n")
        column = at - source.rfind(b"\n", 0, at) - 1
        tree.edit(start_byte=at, old_end_byte=at + 3, new_end_byte=at,
                  start_point=(row, column), old_end_point=(row, column + 3),
                  new_end_point=(row, column))
        incomplete = source[:at] + source[at + 3:]
        tree = self.parser.parse(incomplete, tree)
        self.assertTrue(tree.root_node.has_error)
        tree.edit(start_byte=at, old_end_byte=at, new_end_byte=at + 3,
                  start_point=(row, column), old_end_point=(row, column),
                  new_end_point=(row, column + 3))
        restored = self.parser.parse(source, tree)
        self.assertFalse(restored.root_node.has_error, str(restored.root_node))
        self.assertEqual(str(restored.root_node), str(self.parser.parse(source).root_node))

    def test_multiline_nested_interpolation_survives_incremental_edit(self):
        source = (ROOT / "examples/multiline.wake").read_bytes()
        tree = self.parser.parse(source)
        at = source.index(b"name}")
        row = source[:at].count(b"\n")
        column = at - source.rfind(b"\n", 0, at) - 1
        tree.edit(start_byte=at, old_end_byte=at + 4, new_end_byte=at + 5,
                  start_point=(row, column), old_end_point=(row, column + 4),
                  new_end_point=(row, column + 5))
        edited = source[:at] + b"other" + source[at + 4:]
        updated = self.parser.parse(edited, tree)
        self.assertFalse(updated.root_node.has_error, str(updated.root_node))
        self.assertEqual(str(updated.root_node), str(self.parser.parse(edited).root_node))
        query = Query(self.language, (ROOT / "languages/wake/highlights.scm").read_text())
        captures = QueryCursor(query).captures(updated.root_node)
        self.assertIn(b'format "hello {other}"', [n.text for n in captures["embedded"]])
        after = edited.index(b"def finished")
        self.assertFalse(any(n.start_byte <= after < n.end_byte for n in captures["string"]))

    def test_scanner_serialization_is_bounded_and_resets_empty_state(self):
        create = self.library.tree_sitter_wake_external_scanner_create
        create.restype = ctypes.c_void_p
        destroy = self.library.tree_sitter_wake_external_scanner_destroy
        destroy.argtypes = [ctypes.c_void_p]
        serialize = self.library.tree_sitter_wake_external_scanner_serialize
        serialize.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        serialize.restype = ctypes.c_uint
        deserialize = self.library.tree_sitter_wake_external_scanner_deserialize
        deserialize.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint]
        payload = create()
        try:
            state = bytes([32]) + bytes(range(32)) + bytes([24]) + (b'\x01' + bytes(32)) * 24
            deserialize(payload, state, len(state))
            buffer = ctypes.create_string_buffer(1024)
            length = serialize(payload, buffer)
            self.assertEqual(buffer.raw[:length], state)
            for malformed in [b'', b'\xff', b'\xff\x00', b'\x00\xff', state[:-1]]:
                deserialize(payload, malformed, len(malformed))
                length = serialize(payload, buffer)
                self.assertEqual(buffer.raw[:length], b'\x00\x00')
        finally:
            destroy(payload)

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

    def test_unterminated_multiline_string_does_not_hang(self):
        import sys
        script = (
            "import ctypes; from tree_sitter import Language, Parser; "
            f"lib=ctypes.CDLL({str(Path(self.temp.name) / 'wake.so')!r}); "
            "lib.tree_sitter_wake.restype=ctypes.c_void_p; "
            "new=ctypes.pythonapi.PyCapsule_New; new.restype=ctypes.py_object; "
            "new.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_void_p]; "
            "p=Parser(Language(new(lib.tree_sitter_wake(), b'tree_sitter.Language', None))); "
            "assert p.parse(b'package test\\ndef value =\\n  \"\"\"\\n  unfinished').root_node.has_error"
        )
        subprocess.run([sys.executable, "-c", script], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
