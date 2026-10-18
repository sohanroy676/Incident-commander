"""The .env parser: formats, hostile input, missing file."""

import tempfile
import unittest
from pathlib import Path

from ic_plus.envfile import load_env, parse_env


class TestParse(unittest.TestCase):
    def test_plain_pairs_comments_and_blanks(self):
        text = "# note\n\nLLM_MODEL=llama3\nLLM_BASE_URL = http://x/v1 \n"
        self.assertEqual(parse_env(text), {"LLM_MODEL": "llama3", "LLM_BASE_URL": "http://x/v1"})

    def test_quotes_export_and_crlf(self):
        text = "export A=\"one two\"\r\nB='x'\r\nC=\r\n"
        self.assertEqual(parse_env(text), {"A": "one two", "B": "x", "C": ""})

    def test_value_may_contain_equals_signs(self):
        self.assertEqual(parse_env("K=a=b=c"), {"K": "a=b=c"})

    def test_garbage_lines_are_ignored(self):
        self.assertEqual(parse_env("no equals here\n=novalue\n\x00\n'\n"), {})

    def test_a_lone_quote_is_kept(self):
        self.assertEqual(parse_env('K="'), {"K": '"'})

    def test_last_duplicate_wins(self):
        self.assertEqual(parse_env("K=1\nK=2"), {"K": "2"})


class TestLoad(unittest.TestCase):
    def test_missing_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_env(Path(d) / "nope"), {})

    def test_directory_or_binary_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_env(Path(d)), {})
            binary = Path(d) / "bin"
            binary.write_bytes(b"\xff\xfe\x00\x80")
            self.assertEqual(load_env(binary), {})

    def test_reads_a_real_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / ".env"
            path.write_text("LLM_MODEL=m\n", encoding="utf-8")
            self.assertEqual(load_env(path), {"LLM_MODEL": "m"})


if __name__ == "__main__":
    unittest.main()
