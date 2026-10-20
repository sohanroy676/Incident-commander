"""Upload validation, adversarial inputs, and an uploaded service run through the pipeline."""

import copy
import unittest

from ic_hub.schema import (
    BUILTIN_ALERTS,
    BUILTIN_SERVICES,
    ValidationError,
    parse_json,
    validate_upload,
)

from .support import HubTestCase

T0 = 1_760_000_100.0  # the demo anchor; 60 s grid


def good_upload() -> dict:
    return {
        "service": {
            "name": "billing-service",
            "baseline_latency_ms": 150,
            "baseline_error_rate": 0.01,
            "latency": {"kind": "step", "base": 150, "at": T0 + 172_000, "level": 1200},
            "error_rate": {"kind": "flat", "level": 0.01},
            "deployments": [{"at": T0 + 171_400, "version": "v3.1.0"}],
            "dependencies": [],
            "effects": {"rollback_deployment": {"success": 160, "fix_fails": 3000}},
        },
        "alert": {
            "alert_id": "UP-1",
            "severity": "high",
            "metric": "latency_ms",
            "summary": "billing latency spike, error rate normal",
            "fired_at": T0 + 172_500,
        },
    }


def check(raw: object) -> ValidationError:
    with_error = None
    try:
        validate_upload(raw, BUILTIN_SERVICES, BUILTIN_ALERTS)
    except ValidationError as exc:
        with_error = exc
    assert with_error is not None, "expected a ValidationError"
    return with_error


class TestParseJson(unittest.TestCase):
    def test_duplicate_keys_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            parse_json(b'{"a": 1, "a": 2}')
        with self.assertRaises(ValidationError):
            parse_json(b'{"x": {"a": 1, "a": 2}}')

    def test_non_finite_literals_are_refused(self) -> None:
        for body in (b"NaN", b'{"a": NaN}', b'{"a": Infinity}', b'{"a": -Infinity}'):
            with self.subTest(body=body), self.assertRaises(ValidationError):
                parse_json(body)

    def test_bad_encoding_and_deep_nesting_are_refused(self) -> None:
        with self.assertRaises(ValidationError):
            parse_json(b"\xff\xfe{}")
        with self.assertRaises(ValidationError):
            parse_json(b"[" * 200_000 + b"]" * 200_000)

    def test_plain_json_passes(self) -> None:
        self.assertEqual(
            parse_json(b'{"a": [1, 2.5, "x", null, true]}'), {"a": [1, 2.5, "x", None, True]}
        )


class TestValidateUpload(unittest.TestCase):
    def test_a_good_upload_builds_a_spec_and_an_alert(self) -> None:
        upload = validate_upload(good_upload(), BUILTIN_SERVICES, BUILTIN_ALERTS)
        self.assertEqual(upload.service.name, "billing-service")
        self.assertEqual(upload.alert.service, "billing-service")
        self.assertEqual(upload.service.latency(T0 + 172_000 - 1), 150.0)
        self.assertEqual(upload.service.latency(T0 + 172_000), 1200.0)
        self.assertEqual(upload.effects["rollback_deployment"]["success"], 160.0)

    def test_builtin_names_clash(self) -> None:
        for name in sorted(BUILTIN_SERVICES):
            raw = good_upload()
            raw["service"]["name"] = name
            self.assertIn("service.name", check(raw).fields)
        for alert_id in sorted(BUILTIN_ALERTS):
            raw = good_upload()
            raw["alert"]["alert_id"] = alert_id
            self.assertIn("alert.alert_id", check(raw).fields)

    def test_huge_or_tiny_times_are_bounded(self) -> None:
        for path, value in (
            (("alert", "fired_at"), 0),
            (("alert", "fired_at"), 1e18),
            (("alert", "fired_at"), -T0),
            (("service", "anchor"), 0),
        ):
            raw = good_upload()
            raw[path[0]][path[1]] = value
            self.assertTrue(check(raw).fields, path)
        raw = good_upload()
        raw["service"]["latency"] = {"kind": "ramp", "base": 1, "start": 0, "end": T0, "level": 9}
        self.assertIn("service.latency.start", check(raw).fields)

    def test_fired_at_must_sit_on_the_grid(self) -> None:
        raw = good_upload()
        raw["alert"]["fired_at"] = T0 + 172_501
        self.assertIn("alert.fired_at", check(raw).fields)

    def test_non_numbers_are_refused(self) -> None:
        for bad in (True, "12", None, [1], {"a": 1}, float("inf"), float("-inf"), 1e999):
            raw = good_upload()
            raw["service"]["baseline_latency_ms"] = bad
            with self.subTest(bad=bad):
                self.assertIn("service.baseline_latency_ms", check(raw).fields)

    def test_levels_and_baselines_are_bounded(self) -> None:
        cases = (
            ("baseline_latency_ms", 0),
            ("baseline_latency_ms", -1),
            ("baseline_latency_ms", 1e9),
            ("baseline_error_rate", 0),
            ("baseline_error_rate", 1.5),
        )
        for key, value in cases:
            raw = good_upload()
            raw["service"][key] = value
            with self.subTest(key=key, value=value):
                self.assertIn(f"service.{key}", check(raw).fields)

    def test_series_shapes(self) -> None:
        raw = good_upload()
        raw["service"]["latency"] = {"kind": "sine", "level": 1}
        self.assertIn("service.latency", check(raw).fields)
        raw["service"]["latency"] = {"kind": "flat"}
        self.assertIn("service.latency.level", check(raw).fields)
        raw["service"]["latency"] = {"kind": "flat", "level": 5, "extra": 1}
        self.assertIn("service.latency.extra", check(raw).fields)
        raw["service"]["latency"] = {"kind": "ramp", "base": 1, "start": T0, "end": T0, "level": 9}
        self.assertIn("service.latency.end", check(raw).fields)

    def test_unknown_fields_are_refused(self) -> None:
        for where in ("service", "alert"):
            raw = good_upload()
            raw[where]["surprise"] = 1
            self.assertIn(f"{where}.surprise", check(raw).fields)
        raw = good_upload()
        raw["extra"] = {}
        self.assertIn("upload.extra", check(raw).fields)

    def test_top_level_must_be_an_object(self) -> None:
        for raw in ([], "x", 3, None):
            self.assertTrue(check(raw).fields)

    def test_dependencies_must_exist_and_not_loop(self) -> None:
        raw = good_upload()
        raw["service"]["dependencies"] = ["ghost-service"]
        self.assertIn("service.dependencies[0]", check(raw).fields)
        raw["service"]["dependencies"] = ["billing-service"]
        self.assertIn("service.dependencies[0]", check(raw).fields)
        raw["service"]["dependencies"] = ["payment-service", "payment-service"]
        self.assertIn("service.dependencies", check(raw).fields)
        raw["service"]["dependencies"] = ["payment-service"] * 6
        self.assertIn("service.dependencies", check(raw).fields)
        raw["service"]["dependencies"] = ["payment-service"]
        validate_upload(raw, BUILTIN_SERVICES, BUILTIN_ALERTS)

    def test_effects_must_name_real_actions_and_both_outcomes(self) -> None:
        raw = good_upload()
        raw["service"]["effects"] = {"format_disk": {"success": 1, "fix_fails": 2}}
        self.assertIn("service.effects.format_disk", check(raw).fields)
        raw["service"]["effects"] = {"restart_service": {"success": 1}}
        self.assertIn("service.effects.restart_service.fix_fails", check(raw).fields)
        raw["service"]["effects"] = {"restart_service": {"success": -1, "fix_fails": 2}}
        self.assertIn("service.effects.restart_service.success", check(raw).fields)

    def test_deployments_are_bounded(self) -> None:
        raw = good_upload()
        raw["service"]["deployments"] = [{"at": T0, "version": "v1"}] * 11
        self.assertIn("service.deployments", check(raw).fields)
        raw["service"]["deployments"] = [{"at": T0, "version": "<script>"}]
        self.assertIn("service.deployments[0].version", check(raw).fields)

    def test_text_fields_are_constrained(self) -> None:
        for key, value in (
            ("alert_id", "has space"),
            ("alert_id", ""),
            ("alert_id", "x" * 33),
            ("severity", "apocalyptic"),
            ("metric", "cpu"),
            ("summary", ""),
            ("summary", "x" * 201),
            ("summary", "line\nbreak"),
            ("summary", "bell\x07"),
        ):
            raw = good_upload()
            raw["alert"][key] = value
            with self.subTest(key=key, value=value):
                self.assertIn(f"alert.{key}", check(raw).fields)

    def test_service_name_pattern(self) -> None:
        for name in ("Billing", "a", "1abc", "has space", "../x", "x" * 41, "bill_ing"):
            raw = good_upload()
            raw["service"]["name"] = name
            with self.subTest(name=name):
                self.assertIn("service.name", check(raw).fields)

    def test_all_problems_are_reported_together(self) -> None:
        raw = good_upload()
        raw["service"]["baseline_latency_ms"] = -1
        raw["alert"]["severity"] = "x"
        raw["alert"]["fired_at"] = 5
        self.assertGreaterEqual(len(check(raw).fields), 3)

    def test_validation_does_not_mutate_its_input(self) -> None:
        raw = good_upload()
        before = copy.deepcopy(raw)
        validate_upload(raw, BUILTIN_SERVICES, BUILTIN_ALERTS)
        self.assertEqual(raw, before)


class TestUploadsOverHttp(HubTestCase):
    def test_upload_lists_and_runs_with_its_own_effects(self) -> None:
        reply = self.call("POST", "/api/uploads", good_upload())
        self.assertEqual(reply.status, 201, reply.body)
        alerts = {a["alert_id"]: a for a in self.call("GET", "/api/alerts").json()["alerts"]}
        self.assertEqual(alerts["UP-1"]["source"], "upload")
        self.assertEqual(alerts["ALRT-9001"]["source"], "demo")
        self.assertEqual(alerts["ALRT-9101"]["source"], "golden")
        result = self.run_to_end("UP-1")["result"]
        lines = result["decision_lines"]
        self.assertTrue(lines[0].startswith("DECISION verdict alert=UP-1 verdict=matched"), lines)
        self.assertTrue(
            any("action=rollback_deployment" in x and "status=executed" in x for x in lines)
        )
        verify = next(x for x in lines if x.startswith("DECISION verify"))
        self.assertIn("status=resolved", verify)  # the uploaded effect (160 ms) took hold
        self.assertIn("observed_ms=160", verify)

    def test_fix_fails_uses_the_uploaded_failure_level(self) -> None:
        self.call("POST", "/api/uploads", good_upload())
        lines = self.run_to_end("UP-1", fix_outcome="fix_fails")["result"]["decision_lines"]
        verify = next(x for x in lines if x.startswith("DECISION verify"))
        self.assertIn("status=reopened", verify)
        self.assertIn("observed_ms=3000", verify)

    def test_second_upload_with_the_same_name_is_refused(self) -> None:
        self.assertEqual(self.call("POST", "/api/uploads", good_upload()).status, 201)
        again = self.call("POST", "/api/uploads", good_upload())
        self.assertEqual(again.status, 422)
        self.assertIn("service.name", again.json()["fields"])

    def test_http_level_rejections(self) -> None:
        cases = (
            (b'{"service": {"name": "a", "name": "b"}}', 400),
            (b'{"service": {"baseline_latency_ms": NaN}}', 400),
            (b"not json", 400),
            (b"[1,2]", 422),
            (b"[" * 100_000, 400),
        )
        for body, status in cases:
            with self.subTest(body=body[:30]):
                reply = self.call("POST", "/api/uploads", body)
                self.assertEqual(reply.status, status, reply.body[:200])
                self.assertIn("error", reply.json())

    def test_upload_cap(self) -> None:
        for i in range(20):
            raw = good_upload()
            raw["service"]["name"] = f"svc-{i}"
            raw["alert"]["alert_id"] = f"UP-{i}"
            self.assertEqual(self.call("POST", "/api/uploads", raw).status, 201)
        raw = good_upload()
        raw["service"]["name"] = "svc-over"
        raw["alert"]["alert_id"] = "UP-over"
        self.assertEqual(self.call("POST", "/api/uploads", raw).status, 422)


if __name__ == "__main__":
    unittest.main()
