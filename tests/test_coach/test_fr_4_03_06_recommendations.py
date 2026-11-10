"""FR-4.03 rules, FR-4.04 AI, FR-4.05 dedupe/ranking/listing, FR-4.06 status workflow."""
import uuid

from api.app.coach.footprint import FootprintSummary
from api.app.coach.rules import generate_rule_recommendations
from api.app.core.models import AuditLog
from tests.conftest import TestingSessionLocal
from tests.test_coach.conftest import FakeLLM, register

AI_RESPONSE = {
    "recommendations": [
        {
            "title": "Sign a renewable PPA for Operations",
            "description": "Contract 100% renewable electricity for the Operations site.",
            "reasoning": "Electricity is the largest source.",
            "category": "electricity",
            "est_saving_t_co2e": 9999,  # implausible: must be capped to the category total
            "cost_level": "low", "effort": "low", "scope": "scope_2", "department": "operations",
        },
        {
            "title": "Move sales trips to rail",
            "description": "Use rail for domestic sales visits instead of short-haul flights.",
            "reasoning": "Short-haul flights are 1.8 t.",
            "category": "flight_short_haul",
            "est_saving_t_co2e": 1.2,
            "cost_level": "low", "effort": "medium", "scope": "scope_3", "department": None,
        },
        {"title": "Bad", "description": "x", "est_saving_t_co2e": -5, "cost_level": "huge"},  # invalid
        {
            "title": "Electrify the ship fleet",
            "description": "Replace the company's cargo ships with electric ones.",
            "category": "refrigerant",  # category the company doesn't have -> dropped
            "est_saving_t_co2e": 3, "cost_level": "high", "effort": "high", "scope": "scope_1",
        },
    ]
}


def _summary(by_category, total):
    return FootprintSummary(None, None, None, None, None, total, {}, by_category, [], [], [], [], None, [], {})


# ---------- FR-4.03 rule engine (unit) ----------
def test_rules_target_hotspots_and_rank_by_saving():
    s = _summary([
        {"category": "electricity", "scope": "scope_2", "t_co2e": 10.0, "share_pct": 80.0},
        {"category": "natural_gas", "scope": "scope_1", "t_co2e": 2.5, "share_pct": 20.0},
    ], 12.5)
    recs = generate_rule_recommendations(s)
    assert recs[0].title == "Switch to a certified renewable electricity tariff"
    assert recs[0].est_saving_t_co2e == 9.0
    assert all(a.est_saving_t_co2e >= b.est_saving_t_co2e for a, b in zip(recs, recs[1:]))
    assert not any("fleet" in r.title.lower() for r in recs)  # no fleet data -> no fleet advice


def test_rules_skip_tiny_categories():
    s = _summary([
        {"category": "electricity", "scope": "scope_2", "t_co2e": 99.0, "share_pct": 99.0},
        {"category": "water", "scope": "scope_3", "t_co2e": 1.0, "share_pct": 1.0},
    ], 100.0)
    assert not any("water" in r.title.lower() for r in generate_rule_recommendations(s, limit=20))


def test_rules_empty_footprint():
    assert generate_rule_recommendations(_summary([], 0.0)) == []


def test_generate_rules_mode(client, org_with_data):
    r = client.post("/coach/recommendations/generate", headers=org_with_data["headers"], json={"mode": "rules"})
    assert r.status_code == 201
    body = r.json()
    assert body["source_used"] == "rules"
    assert len(body["created"]) > 0
    assert "Why:" in body["created"][0]["description"]


# ---------- FR-4.04 AI recommendations ----------
def test_generate_ai_validates_and_caps_output(client, org_with_data, use_llm):
    use_llm(FakeLLM(json_response=AI_RESPONSE))
    r = client.post("/coach/recommendations/generate", headers=org_with_data["headers"], json={"mode": "ai"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_used"] == "ai"
    titles = [c["title"] for c in body["created"]]
    assert titles == ["Sign a renewable PPA for Operations", "Move sales trips to rail"]  # invalid + unknown dropped
    ppa = body["created"][0]
    assert ppa["est_saving_t_co2e"] <= 13.8  # capped at electricity emissions (13.794 t)
    assert ppa["department_id"] == org_with_data["ops"]  # department name mapped to id
    assert "Why: Electricity is the largest source." in ppa["description"]


def test_ai_mode_without_key_returns_503(client, org_with_data, use_llm):
    use_llm(None)
    r = client.post("/coach/recommendations/generate", headers=org_with_data["headers"], json={"mode": "ai"})
    assert r.status_code == 503


def test_generate_without_data(client):
    headers, _ = register(client)
    body = client.post("/coach/recommendations/generate", headers=headers, json={}).json()
    assert body["created"] == [] and "No calculated emissions" in body["warning"]


# ---------- FR-4.05 dedupe ----------
def test_generate_twice_skips_duplicates(client, org_with_data, use_llm):
    use_llm(FakeLLM(json_response=AI_RESPONSE))
    h = org_with_data["headers"]
    first = client.post("/coach/recommendations/generate", headers=h, json={}).json()
    second = client.post("/coach/recommendations/generate", headers=h, json={}).json()
    assert len(first["created"]) == 2
    assert second["created"] == [] and second["skipped_duplicates"] == 2


# ---------- FR-4.05 ranking and listing ----------
def test_list_and_filter(client, org_with_data):
    h = org_with_data["headers"]
    client.post("/coach/recommendations/generate", headers=h, json={"mode": "rules"})
    all_recs = client.get("/coach/recommendations", headers=h).json()
    savings = [r["est_saving_t_co2e"] for r in all_recs]
    assert savings == sorted(savings, reverse=True)
    scope2 = client.get("/coach/recommendations?scope=scope_2", headers=h).json()
    assert scope2 and all(r["scope"] == "scope_2" for r in scope2)
    assert client.get("/coach/recommendations?status=completed", headers=h).json() == []


# ---------- FR-4.06 status workflow ----------
def test_status_lifecycle_and_audit(client, org_with_data):
    h = org_with_data["headers"]
    rec = client.post("/coach/recommendations/generate", headers=h, json={"mode": "rules"}).json()["created"][0]
    url = f"/coach/recommendations/{rec['id']}/status"

    assert client.patch(url, headers=h, json={"status": "completed"}).status_code == 409  # must accept first
    assert client.patch(url, headers=h, json={"status": "accepted"}).json()["status"] == "accepted"
    assert client.patch(url, headers=h, json={"status": "completed"}).json()["status"] == "completed"
    assert client.patch(url, headers=h, json={"status": "proposed"}).status_code == 409  # completed is final

    db = TestingSessionLocal()
    logs = db.query(AuditLog).filter(AuditLog.entity == "Recommendation", AuditLog.entity_id == uuid.UUID(rec["id"])).all()
    db.close()
    changes = [l.changes for l in logs if l.changes and "status" in l.changes]
    assert {"from": "proposed", "to": "accepted"} in [c["status"] for c in changes]
