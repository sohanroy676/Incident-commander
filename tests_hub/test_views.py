"""v2.3 views: evidence chart payload, what-if toggles and run diff, including hostile input."""

import unittest

from ic_hub.world import HubWorld
from incident_commander.config import VERIFY_TOLERANCE, VERIFY_WINDOW_S

from .support import HubTestCase


class TestChartPayload(HubTestCase):
    def chart(self, alert_id: str, **extra: object) -> dict:
        return self.run_to_end(alert_id, **extra)["result"]["chart"]

    def test_points_baseline_and_deploys_come_from_the_world(self) -> None:
        chart = self.chart("ALRT-9002")
        world = HubWorld()
        alert = world.alert("ALRT-9002")
        self.assertEqual(chart["service"], alert.service)
        self.assertEqual(chart["metric"], alert.metric)
        self.assertEqual(chart["fired_at"], alert.fired_at)
        self.assertEqual(chart["window_start"], alert.fired_at - 1800)
        before_fix = [p for p in chart["points"] if p[0] < chart["executed_at"]]
        expected = world.latency_points(alert.service, chart["window_start"], alert.fired_at, 1e12)
        self.assertEqual(before_fix[: len(expected)], [list(p) for p in expected])
        self.assertEqual(chart["baseline"], world.baselines(alert.service)[0])
        self.assertAlmostEqual(chart["limit"], chart["baseline"] * VERIFY_TOLERANCE)
        deploys = world.deployments(alert.service, chart["window_start"], chart["window_end"], 1e12)
        self.assertEqual([d["at"] for d in chart["deployments"]], [d[0] for d in deploys])

    def test_fix_markers_and_recovery(self) -> None:
        chart = self.chart("ALRT-9002")
        self.assertIsNotNone(chart["executed_at"])
        self.assertGreaterEqual(chart["verify_end"] - chart["executed_at"], VERIFY_WINDOW_S)
        self.assertLessEqual(chart["points"][-1][1], chart["limit"])

    def test_failed_fix_stays_high_after_the_fix(self) -> None:
        chart = self.chart("ALRT-9002", fix_outcome="fix_fails")
        self.assertEqual(chart["points"][-1][1], 3900)
        self.assertGreater(chart["points"][-1][1], chart["limit"])

    def test_no_fix_means_no_fix_markers(self) -> None:
        chart = self.chart("ALRT-9001", mode="silent", deadline_s=0.2)
        self.assertIsNone(chart["executed_at"])
        self.assertIsNone(chart["verify_end"])

    def test_chart_survives_publish(self) -> None:
        run_id = self.start_run("ALRT-9002")
        self.wait_for(run_id)
        reply = self.call("POST", f"/api/runs/{run_id}/publish")
        self.assertEqual(reply.status, 200, reply.body)
        self.assertIsNotNone(reply.json()["chart"])

    def test_page_has_the_chart_container_and_builds_svg_with_dom_calls(self) -> None:
        page = self.call("GET", "/", token=False).body.decode()
        self.assertIn('id="chart"', page)
        script = self.call("GET", "/app.js", token=False).body.decode()
        self.assertIn("createElementNS", script)


class TestWhatIf(HubTestCase):
    def lines(self, alert_id: str, **extra: object) -> list[str]:
        return self.run_to_end(alert_id, **extra)["result"]["decision_lines"]

    def test_stale_deployments_hands_off_like_the_scenario(self) -> None:
        lines = self.lines("ALRT-9001", what_if=["stale_deployments"])
        self.assertIn("no_confident_match", lines[0])
        self.assertFalse(any(x.startswith("DECISION execute") for x in lines), lines)

    def test_backend_down_ends_without_a_match(self) -> None:
        view = self.run_to_end("ALRT-9001", what_if=["tool_failure"])
        self.assertIn("no_confident_match", view["result"]["decision_lines"][0])
        self.assertIn("insufficient_evidence", view["result"]["decision_lines"][0])

    def test_both_toggles_together_still_finish(self) -> None:
        view = self.run_to_end("ALRT-9002", what_if=["stale_deployments", "tool_failure"])
        self.assertEqual(view["status"], "done")

    def test_empty_list_equals_no_toggles(self) -> None:
        self.assertEqual(self.lines("ALRT-9003", what_if=[]), self.lines("ALRT-9003"))

    def test_toggles_do_not_leak_into_the_next_run(self) -> None:
        self.lines("ALRT-9001", what_if=["tool_failure"])
        self.assertIn("verdict=matched", self.lines("ALRT-9001")[0])

    def test_bad_what_if_values_are_rejected(self) -> None:
        bad = (
            ["rm -rf"],
            ["tool_failure", "tool_failure"],
            "tool_failure",
            {"tool_failure": True},
            [1],
            [None],
            ["stale_deployments", "tool_failure", "tool_failure"],
        )
        for value in bad:
            with self.subTest(value=value):
                reply = self.call("POST", "/api/runs", {"alert_id": "ALRT-9001", "what_if": value})
                self.assertEqual(reply.status, 422, reply.body)
                self.assertIn("what_if", reply.json()["fields"])


class TestDiff(HubTestCase):
    def finished(self, alert_id: str, **extra: object) -> str:
        run_id = self.start_run(alert_id, **extra)
        self.wait_for(run_id)
        return run_id

    def diff(self, a: object, b: object):
        return self.call("POST", "/api/diff", {"a": a, "b": b})

    def test_same_alert_twice_has_no_differences(self) -> None:
        a, b = self.finished("ALRT-9002"), self.finished("ALRT-9002")
        body = self.diff(a, b).json()
        self.assertTrue(body["same_decisions"])
        self.assertEqual(body["only_in_a"], [])
        self.assertEqual(body["only_in_b"], [])

    def test_success_versus_failed_fix_differs(self) -> None:
        a = self.finished("ALRT-9002")
        b = self.finished("ALRT-9002", fix_outcome="fix_fails")
        body = self.diff(a, b).json()
        self.assertFalse(body["same_decisions"])
        self.assertEqual(body["handoff_reason"], [None, "reopened"])
        self.assertTrue(any("reopened" in x for x in body["only_in_b"]))

    def test_unknown_run_is_404(self) -> None:
        a = self.finished("ALRT-9003")
        self.assertEqual(self.diff(a, "0" * 16).status, 404)

    def test_hostile_ids_are_rejected(self) -> None:
        a = self.finished("ALRT-9003")
        for bad in ("../../etc/passwd", "A" * 16, "0" * 15, "", None, 7, ["x"], a + "\n"):
            with self.subTest(bad=bad):
                reply = self.diff(a, bad)
                self.assertEqual(reply.status, 422, reply.body)

    def test_unknown_fields_and_non_objects_are_rejected(self) -> None:
        a = self.finished("ALRT-9003")
        self.assertEqual(self.call("POST", "/api/diff", {"a": a, "b": a, "c": 1}).status, 422)
        self.assertEqual(self.call("POST", "/api/diff", [a, a]).status, 422)

    def test_playground_runs_cannot_be_compared(self) -> None:
        a = self.finished("ALRT-9003")
        reply = self.call("POST", "/api/playground", {"alert_id": "ALRT-9003", "text": "hello"})
        play = reply.json()["run_id"]
        self.wait_for(play)
        self.assertEqual(self.diff(a, play).status, 409)

    def test_running_run_is_a_conflict(self) -> None:
        a = self.finished("ALRT-9003")
        waiting = self.start_run("ALRT-9001", mode="web", deadline_s=5)
        self.wait_pending(waiting)
        self.assertEqual(self.diff(a, waiting).status, 409)

    def test_diff_enforces_token_origin_and_method(self) -> None:
        a = self.finished("ALRT-9003")
        body = {"a": a, "b": a}
        self.assertEqual(self.call("POST", "/api/diff", body, token=False).status, 403)
        self.assertEqual(
            self.call("POST", "/api/diff", body, headers={"Origin": "http://evil.example"}).status,
            403,
        )
        self.assertEqual(self.call("GET", "/api/diff").status, 404)
        self.assertEqual(
            self.call("POST", "/api/diff", body, content_type="text/plain").status, 415
        )


if __name__ == "__main__":
    unittest.main()
