"""Zero-token intent classifier: canonical routing table tests."""
from app.mechanical_triage import classify_incoming_intent, triage_inbox_items


class TestCommandPrefixes:
    def test_slash_research(self):
        r = classify_incoming_intent("/research competitor pricing")
        assert r["route"] == "researcher"
        assert r["tier"] == "worker"

    def test_slash_write(self):
        r = classify_incoming_intent("/write changelog for v2")
        assert r["route"] == "writer"

    def test_slash_seo(self):
        assert classify_incoming_intent("/seo keyword audit")["route"] == "seo"

    def test_slash_ops(self):
        assert classify_incoming_intent("/ops triage tickets")["route"] == "ops"

    def test_slash_code(self):
        r = classify_incoming_intent("/fix the auth bug")
        assert r["route"] == "coder"
        assert r["tier"] == "primary"

    def test_slash_find_routes_to_researcher(self):
        assert classify_incoming_intent("/find papers on RAG")["route"] == "researcher"


class TestHeuristics:
    def test_natural_research(self):
        assert classify_incoming_intent("compare the pricing of these two stacks")["route"] == "researcher"

    def test_natural_writer(self):
        assert classify_incoming_intent("draft a release note for v1.1")["route"] == "writer"

    def test_natural_ops(self):
        assert classify_incoming_intent("show open issues in the sprint")["route"] == "ops"

    def test_natural_coder(self):
        assert classify_incoming_intent("this function has a bug in the parser")["route"] == "coder"

    def test_url_ingest(self):
        r = classify_incoming_intent("summarize https://example.com/article")
        assert r["route"] == "researcher"
        assert r["action"] == "url_ingest"
        assert r["urls"] == ["https://example.com/article"]

    def test_ambiguous_defaults_to_atlas_primary(self):
        r = classify_incoming_intent("what should we do this quarter?")
        assert r["route"] == "atlas"
        assert r["tier"] == "primary"


class TestInboxTriage:
    def test_noise_filtered(self):
        items = [{"subject": "Daily digest", "sender": "noreply@x.com"}]
        out = triage_inbox_items(items)
        assert len(out["automated_noise"]) == 1
        assert out["actionable_todos"] == []

    def test_urgent_flagged(self):
        items = [{"subject": "URGENT: payment failed", "sender": "billing@x.com"}]
        out = triage_inbox_items(items)
        assert len(out["urgent_notifications"]) == 1

    def test_normal_becomes_todo(self):
        items = [{"subject": "Team offsite planning", "sender": "hr@x.com"}]
        out = triage_inbox_items(items)
        assert len(out["actionable_todos"]) == 1
