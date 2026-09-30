"""Verification Gate: fail-closed + 1-pass corrective rule tests."""
import pytest

from app.orchestrator.verification_gate import VerificationGate


@pytest.fixture
def gate():
    g = VerificationGate()
    # Force structural-only mode for deterministic tests (no network).
    g._model_verify = None  # type: ignore[assignment]
    return g


class TestStructuralCheck:
    def test_empty_output_fails(self, gate):
        ok, reason, out = gate.verify_output.__wrapped__(gate, "task", "") if hasattr(gate.verify_output, '__wrapped__') else (None, None, None)
        # direct structural call instead:
        ok, reason = gate._structural_check("")
        assert not ok
        assert "short" in reason.lower()

    def test_short_output_fails(self, gate):
        ok, reason = gate._structural_check("ok")
        assert not ok

    def test_plausible_prose_without_evidence_fails(self, gate):
        ok, reason = gate._structural_check(
            "I have carefully considered your request and the task is complete. Everything looks great and all requirements have been satisfied fully."
        )
        assert not ok
        assert "evidence" in reason.lower()

    def test_output_with_url_passes(self, gate):
        ok, _ = gate._structural_check("Benchmark complete: see https://example.com/results for the full data.")
        assert ok

    def test_output_with_code_passes(self, gate):
        ok, _ = gate._structural_check("Here is the fix:\n`return json.loads(payload)`")
        assert ok

    def test_output_with_file_path_passes(self, gate):
        ok, _ = gate._structural_check("Wrote the report to /opt/data/handoffs/research/report.md")
        assert ok

    def test_output_with_metric_passes(self, gate):
        ok, _ = gate._structural_check("Latency improved to 240ms across the board.")
        assert ok


class TestOnePassRule:
    async def test_fail_with_no_regenerator_stays_failed(self, gate):
        passed, reason, out = await gate.verify_output("task", "short", regenerate=None)
        assert not passed

    async def test_regen_once_succeeds(self, gate):
        calls = []
        async def regenerate():
            calls.append(1)
            return "See results at https://example.com/evidence"
        passed, reason, out = await gate.verify_output("task", "too short", regenerate=regenerate)
        assert passed
        assert len(calls) == 1
        assert "corrective" in reason.lower()
        assert out == "See results at https://example.com/evidence"

    async def test_regen_failing_again_stays_failed(self, gate):
        async def regenerate():
            return "still no evidence here at all"
        passed, reason, out = await gate.verify_output("task", "too short", regenerate=regenerate)
        assert not passed

    async def test_regen_exception_does_not_crash(self, gate):
        async def regenerate():
            raise RuntimeError("model down")
        passed, reason, out = await gate.verify_output("task", "too short", regenerate=regenerate)
        assert not passed
        assert out == "too short"


class TestModelVerifyFailClosed:
    async def test_unreachable_verifier_fails_closed(self, monkeypatch, tmp_path):
        from app import config
        monkeypatch.setattr(config.settings, "primary_api_key", "sk-test")
        monkeypatch.setattr(config.settings, "primary_base_url", "http://127.0.0.1:1")  # nothing listens

        g = VerificationGate()
        passed, reason, out = await g.verify_output(
            "task",
            "Solid analysis with evidence: https://example.com/data and 120ms latency.",
        )
        assert not passed
        assert "fail" in reason.lower() and "closed" in reason.lower()
