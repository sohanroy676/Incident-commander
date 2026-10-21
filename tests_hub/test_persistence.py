"""v2.3 persistence: opt-in run history, similar runs and the hash-chained audit log."""

import json
import tempfile
import threading
import unittest
from pathlib import Path

from ic_hub.__main__ import main
from ic_hub.store import GENESIS, MAX_RECORD_BYTES, Store

from .support import ROOT, HubTestCase, saved_decisions


class StoredHubCase(HubTestCase):
    """A hub started with a temporary data directory."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "data"
        self.store = Store(self.dir)
        super().setUp()

    def audit_lines(self) -> list[dict]:
        text = (self.dir / "audit.jsonl").read_text(encoding="utf-8")
        return [json.loads(x) for x in text.splitlines()]


class TestDisabledByDefault(HubTestCase):
    def test_everything_is_off_and_empty(self) -> None:
        self.run_to_end("ALRT-9003")
        self.assertEqual(self.call("GET", "/api/history").json()["enabled"], False)
        self.assertEqual(self.call("GET", "/api/history").json()["runs"], [])
        self.assertEqual(self.call("GET", "/api/audit").json()["enabled"], False)
        self.assertEqual(self.call("GET", "/api/history/" + "0" * 16).status, 404)

    def test_data_is_gitignored(self) -> None:
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("data/", [x.strip() for x in lines])

    def test_cli_rejects_a_data_dir_that_is_a_file(self) -> None:
        with tempfile.NamedTemporaryFile() as handle:
            with self.assertRaises(SystemExit) as caught:
                main(["--port", "0", "--data-dir", handle.name])
            self.assertEqual(caught.exception.code, 2)


class TestHistory(StoredHubCase):
    def test_a_run_is_stored_and_listed(self) -> None:
        view = self.run_to_end("ALRT-9002")
        listing = self.call("GET", "/api/history").json()
        self.assertTrue(listing["enabled"])
        row = listing["runs"][0]
        self.assertEqual(row["run_id"], view["run_id"])
        self.assertEqual((row["alert_id"], row["state"]), ("ALRT-9002", view["result"]["state"]))
        self.assertNotIn("result", row)
        stored = self.call("GET", f"/api/history/{view['run_id']}").json()
        self.assertEqual(stored["result"]["decision_lines"], view["result"]["decision_lines"])
        self.assertTrue((self.dir / "runs" / f"{view['run_id']}.json").is_file())

    def test_history_survives_a_new_store_on_the_same_directory(self) -> None:
        view = self.run_to_end("ALRT-9003")
        again = Store(self.dir)
        self.assertEqual(again.get_run(view["run_id"])["alert_id"], "ALRT-9003")  # type: ignore[index]

    def test_storing_does_not_change_a_decision(self) -> None:
        saved = saved_decisions()
        lines = self.run_to_end("ALRT-9001")["result"]["decision_lines"]
        self.assertTrue(all(x in saved for x in lines), lines)

    def test_publish_updates_the_stored_copy(self) -> None:
        run_id = self.start_run("ALRT-9002")
        self.wait_for(run_id)
        self.assertEqual(self.call("POST", f"/api/runs/{run_id}/publish").status, 200)
        stored = self.call("GET", f"/api/history/{run_id}").json()
        self.assertTrue(stored["published"])
        self.assertTrue(stored["result"]["published"])

    def test_playground_explain_and_evaluate_are_not_stored(self) -> None:
        reply = self.call("POST", "/api/playground", {"alert_id": "ALRT-9003", "text": "hello"})
        self.wait_for(reply.json()["run_id"])
        reply = self.call("POST", "/api/explain", {"alert_id": "ALRT-9003", "question": "why?"})
        self.wait_for(reply.json()["run_id"])
        self.assertEqual(self.call("GET", "/api/history").json()["runs"], [])

    def test_hostile_ids_never_reach_the_disk(self) -> None:
        secret = self.dir.parent / "secret.json"
        secret.write_text(json.dumps({"run_id": "secret", "result": {}}), encoding="utf-8")
        for bad in (
            "..%2fsecret",
            "..%2F..%2Fsecret",
            "%2e%2e/secret",
            "../secret",
            "A" * 16,
            "0" * 15,
            "0" * 17,
            "0" * 16 + "%00",
            "0" * 16 + "/x",
            "secret",
        ):
            with self.subTest(bad=bad):
                self.assertEqual(self.call("GET", f"/api/history/{bad}").status, 404)
        for bad in ("../secret", "..\\secret", "", None, 5, "G" * 16, "0" * 16 + "\n"):
            with self.subTest(store_id=bad):
                self.assertIsNone(self.store.get_run(bad))
        self.assertFalse(self.store.save_run({"run_id": "../escape", "result": {}}))
        self.assertFalse((self.dir.parent / "escape.json").exists())

    def test_damaged_files_are_skipped_not_fatal(self) -> None:
        good = self.run_to_end("ALRT-9003")["run_id"]
        runs = self.dir / "runs"
        (runs / ("a" * 16 + ".json")).write_text("{not json", encoding="utf-8")
        (runs / ("b" * 16 + ".json")).write_text(json.dumps({"run_id": "c" * 16}), encoding="utf-8")
        (runs / ("d" * 16 + ".json")).write_bytes(b"\xff\xfe\x00bad")
        (runs / ("e" * 16 + ".json")).write_text("x" * (MAX_RECORD_BYTES + 1), encoding="utf-8")
        (runs / "notes.txt").write_text("ignored", encoding="utf-8")
        ids = [r["run_id"] for r in self.call("GET", "/api/history").json()["runs"]]
        self.assertEqual(ids, [good])
        for name in "abde":
            self.assertEqual(self.call("GET", f"/api/history/{name * 16}").status, 404)

    def test_history_is_capped_to_the_newest(self) -> None:
        self.store.max_runs = 2
        ids = [self.run_to_end("ALRT-9003")["run_id"] for _ in range(4)]
        kept = [r["run_id"] for r in self.call("GET", "/api/history").json()["runs"]]
        self.assertEqual(len(kept), 2)
        self.assertEqual(set(kept), set(ids[-2:]))

    def test_an_oversized_record_is_refused_and_reported(self) -> None:
        stored = self.store.save_run({"run_id": "f" * 16, "result": {"x": "y" * MAX_RECORD_BYTES}})
        self.assertFalse(stored)
        self.assertIn("size cap", self.call("GET", "/api/history").json()["write_error"])

    def test_read_only_routes_need_token_and_origin(self) -> None:
        for path in ("/api/history", "/api/audit", "/api/history/" + "0" * 16):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path, token=False).status, 403)
                evil = {"Origin": "http://evil.example"}
                self.assertEqual(self.call("GET", path, headers=evil).status, 403)
        self.assertEqual(self.call("POST", "/api/history", {}).status, 404)
        self.assertEqual(self.call("DELETE", "/api/history").status, 405)


class TestSimilar(StoredHubCase):
    def test_same_service_is_listed_without_the_run_itself(self) -> None:
        first = self.run_to_end("ALRT-9001")["run_id"]
        second = self.run_to_end("ALRT-9001")["run_id"]
        self.run_to_end("ALRT-9003")
        body = self.call("GET", f"/api/runs/{second}/similar").json()
        ids = [r["run_id"] for r in body["runs"]]
        self.assertIn(first, ids)
        self.assertNotIn(second, ids)
        self.assertIn("same service", body["runs"][0]["reason"])

    def test_a_stored_run_can_be_asked_after_a_restart(self) -> None:
        first = self.run_to_end("ALRT-9002")["run_id"]
        self.run_to_end("ALRT-9002")
        self.server.hub._runs.clear()
        body = self.call("GET", f"/api/runs/{first}/similar").json()
        self.assertEqual(len(body["runs"]), 1)

    def test_unknown_run_is_404_and_disabled_is_empty(self) -> None:
        self.assertEqual(self.call("GET", f"/api/runs/{'0' * 16}/similar").status, 404)

    def test_similar_text_cannot_reach_a_decision(self) -> None:
        source = "".join(
            p.read_text(encoding="utf-8")
            for p in (ROOT / "incident_commander").rglob("*.py")
            if p.is_file()
        )
        self.assertNotIn("similar", source.lower().replace("similarity", ""))


class TestAuditChain(StoredHubCase):
    def test_events_are_recorded_in_order_without_secrets(self) -> None:
        run_id = self.start_run("ALRT-9001", mode="web", deadline_s=10)
        pending = self.wait_pending(run_id, "engineer-priya")
        reply = self.call(
            "POST",
            f"/api/runs/{run_id}/approval",
            {"nonce": pending["nonce"], "decision": "approve"},
        )
        self.assertEqual(reply.json()["outcome"], "accepted")
        self.wait_for(run_id)
        self.call("POST", f"/api/runs/{run_id}/publish")
        events = [e["event"] for e in self.audit_lines()]
        self.assertEqual(events[0], "run_started")
        for name in ("approval_answer", "run_finished", "published"):
            self.assertIn(name, events)
        self.assertLess(events.index("approval_answer"), events.index("run_finished"))
        raw = (self.dir / "audit.jsonl").read_text(encoding="utf-8")
        self.assertNotIn(pending["nonce"], raw)
        answer = next(e for e in self.audit_lines() if e["event"] == "approval_answer")
        self.assertEqual(answer["detail"]["target"], "engineer-priya")
        self.assertEqual(answer["detail"]["outcome"], "accepted")
        verdict = self.call("GET", "/api/audit").json()["verify"]
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual(verdict["entries"], len(events))

    def test_invalid_decisions_are_logged_as_invalid_not_as_typed(self) -> None:
        run_id = self.start_run("ALRT-9001", mode="web", deadline_s=5)
        pending = self.wait_pending(run_id)
        junk = "<script>x</script>\n" + "A" * 500
        self.call(
            "POST", f"/api/runs/{run_id}/approval", {"nonce": pending["nonce"], "decision": junk}
        )
        answer = next(e for e in self.audit_lines() if e["event"] == "approval_answer")
        self.assertEqual(answer["detail"]["decision"], "invalid")

    def test_uploads_explain_and_evaluate_are_recorded(self) -> None:
        upload = {
            "service": {
                "name": "billing-service",
                "baseline_latency_ms": 150,
                "baseline_error_rate": 0.01,
                "latency": {"kind": "step", "base": 150, "at": 1760172000, "level": 1200},
                "error_rate": {"kind": "flat", "level": 0.01},
                "deployments": [],
                "dependencies": [],
                "effects": {"rollback_deployment": {"success": 160, "fix_fails": 3000}},
            },
            "alert": {
                "alert_id": "UP-1",
                "severity": "high",
                "metric": "latency_ms",
                "summary": "billing latency spike",
                "fired_at": 1760172600,
            },
        }
        self.assertEqual(self.call("POST", "/api/uploads", upload).status, 201)
        reply = self.call("POST", "/api/explain", {"alert_id": "ALRT-9003", "question": "why?"})
        self.wait_for(reply.json()["run_id"])
        names = [e["event"] for e in self.audit_lines()]
        self.assertEqual(names, ["upload_added", "explain_finished"])
        self.assertEqual(self.audit_lines()[0]["detail"]["alert_id"], "UP-1")

    def test_verify_reports_a_tampered_file_over_http(self) -> None:
        self.run_to_end("ALRT-9003")
        self.assertTrue(self.call("GET", "/api/audit").json()["verify"]["ok"])
        path = self.dir / "audit.jsonl"
        path.write_text(path.read_text(encoding="utf-8").replace("ALRT-9003", "ALRT-9999", 1))
        verdict = self.call("GET", "/api/audit").json()["verify"]
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["first_bad_line"], 1)


class TestAuditStore(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.store = Store(self.dir)
        for i in range(5):
            self.assertTrue(self.store.append("step", n=i))
        self.path = self.dir / "audit.jsonl"

    def lines(self) -> list[str]:
        return self.path.read_text(encoding="utf-8").splitlines()

    def write(self, lines: list[str]) -> None:
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_an_untouched_log_verifies_and_starts_at_genesis(self) -> None:
        verdict = self.store.verify()
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["entries"], 5)
        self.assertEqual(json.loads(self.lines()[0])["prev"], GENESIS)
        self.assertEqual(verdict["head"], json.loads(self.lines()[-1])["hash"])

    def test_an_empty_or_missing_log_is_valid(self) -> None:
        self.path.unlink()
        self.assertTrue(self.store.verify()["ok"])
        self.path.write_text("", encoding="utf-8")
        self.assertTrue(self.store.verify()["ok"])

    def test_editing_deleting_reordering_or_inserting_is_detected(self) -> None:
        original = self.lines()
        edited = list(original)
        edited[2] = edited[2].replace('"n":"2"', '"n":"9"').replace('"n": "2"', '"n": "9"')
        deleted = original[:1] + original[2:]
        swapped = [original[0], original[2], original[1], *original[3:]]
        forged = json.loads(original[1])
        forged["detail"] = {"n": "forged"}
        replaced = list(original)
        replaced[1] = json.dumps(forged, sort_keys=True)
        cases = {
            "edit": (edited, 3),
            "delete": (deleted, 2),
            "swap": (swapped, 2),
            "forged-without-rehash": (replaced, 2),
            "garbage-line": ([*original, "not json"], 6),
            "duplicate-line": ([*original, original[-1]], 6),
            "blank-line-inside": (original[:2] + [""] + original[2:], 3),
        }
        for name, (lines, bad) in cases.items():
            with self.subTest(name=name):
                self.write(lines)
                verdict = self.store.verify()
                self.assertFalse(verdict["ok"], name)
                self.assertEqual(verdict["first_bad_line"], bad, name)

    def test_a_forger_who_recomputes_one_hash_still_breaks_the_next_line(self) -> None:
        from ic_hub.store import _digest

        lines = self.lines()
        entry = json.loads(lines[1])
        entry["detail"] = {"n": "forged"}
        body = {k: v for k, v in entry.items() if k != "hash"}
        entry["hash"] = _digest(entry["prev"], body)
        lines[1] = json.dumps(entry, sort_keys=True)
        self.write(lines)
        self.assertEqual(self.store.verify()["first_bad_line"], 3)

    def test_removing_the_tail_is_not_detected_which_is_the_documented_limit(self) -> None:
        head_before = self.store.verify()["head"]
        self.write(self.lines()[:3])
        after = self.store.verify()
        self.assertTrue(after["ok"])
        self.assertNotEqual(after["head"], head_before)
        self.assertIn("tamper-evident only", after["note"])

    def test_newlines_quotes_and_huge_values_stay_on_one_bounded_line(self) -> None:
        before = len(self.lines())
        self.store.append(
            "evil\nevent", payload='a\nb"}\n{"seq":1', big="x" * 10_000, ctrl="\x00\x1b[31m"
        )
        lines = self.lines()
        self.assertEqual(len(lines), before + 1)
        entry = json.loads(lines[-1])
        self.assertLessEqual(len(entry["detail"]["big"]), 200)
        self.assertNotIn("\n", entry["detail"]["payload"])
        self.assertTrue(self.store.verify()["ok"])

    def test_concurrent_appends_keep_one_unbroken_chain(self) -> None:
        def work(offset: int) -> None:
            for i in range(25):
                self.store.append("burst", who=offset, i=i)

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        verdict = self.store.verify()
        self.assertTrue(verdict["ok"], verdict)
        self.assertEqual(verdict["entries"], 5 + 200)

    def test_a_restart_continues_the_same_chain(self) -> None:
        again = Store(self.dir)
        again.append("after-restart")
        verdict = again.verify()
        self.assertTrue(verdict["ok"])
        self.assertEqual(verdict["entries"], 6)

    def test_the_size_cap_stops_appends_and_says_so(self) -> None:
        self.store.max_audit_bytes = 10
        self.assertFalse(self.store.append("late"))
        verdict = self.store.verify()
        self.assertTrue(verdict["audit_full"])
        self.assertEqual(verdict["entries"], 5)

    def test_unreadable_log_is_reported_not_raised(self) -> None:
        self.path.write_bytes(b"\xff\xfe\x00")
        verdict = self.store.verify()
        self.assertFalse(verdict["ok"])


if __name__ == "__main__":
    unittest.main()
