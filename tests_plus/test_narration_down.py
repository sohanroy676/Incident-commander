"""Once the server is down, later alerts skip the call but still leave an llm_unavailable trace event."""

import argparse
import contextlib
import io
import unittest

from ic_plus.__main__ import _Narration
from ic_plus.narrator import UNAVAILABLE_LINE
from tests_plus.fake_llm import unused_url
from tests_plus.test_narrator import case_for, kinds


class TestNarrationDown(unittest.TestCase):
    def test_every_case_after_the_first_failure_is_traced_and_makes_no_request(self):
        args = argparse.Namespace(llm="local", llm_url=unused_url(), model="m")
        narration = _Narration(args)
        cases = [case_for("ALRT-9003"), case_for("ALRT-9003")]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            for case in cases:
                narration.show(case)
        self.assertEqual(out.getvalue().count(UNAVAILABLE_LINE), 2)
        for case in cases:
            self.assertEqual(kinds(case).count("llm_unavailable"), 1)
        self.assertTrue(narration.down)

    def test_llm_off_leaves_the_trace_untouched(self):
        case = case_for("ALRT-9003")
        before = kinds(case)
        with contextlib.redirect_stdout(io.StringIO()):
            _Narration(argparse.Namespace(llm="off", llm_url=None, model=None)).show(case)
        self.assertEqual(kinds(case), before)


if __name__ == "__main__":
    unittest.main()
