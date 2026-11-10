"""FR-4.01 footprint summary (consistent with S3) and FR-4.02 AI insights."""
import pytest

from tests.test_coach.conftest import FakeLLM, add_activity, add_facility, register


def test_summary_uses_s2_results_and_matches_s3(client, org_with_data):
    h = org_with_data["headers"]
    s = client.get("/coach/summary", headers=h).json()
    assert s["total_t_co2e"] == pytest.approx(20.435, abs=0.01)
    assert s["by_scope"]["scope_2"] == pytest.approx(13.794, abs=0.01)
    assert s["by_scope"]["scope_1"] == pytest.approx(5.106, abs=0.01)
    assert s["hotspots"][0]["category"] == "electricity"
    assert s["hotspots"][0]["scope"] == "scope_2"
    assert s["by_department"][0]["department"] == "Operations"
    assert s["period_from"] == "2025-03-01" and s["period_to"] == "2026-02-28"  # last 12 months with data

    # The coach quotes exactly the dashboard's numbers (S3)
    s3 = client.get("/analytics/summary", headers=h,
                    params={"start": s["period_from"], "end": s["period_to"]}).json()
    assert s["total_t_co2e"] == pytest.approx(s3["total_t_co2e"], abs=0.001)


def test_summary_reports_records_without_result(client):
    headers, _ = register(client)
    add_activity(client, headers, "electricity", 1000, "kWh")  # no facility/country -> S2 can't calculate
    s = client.get("/coach/summary", headers=headers).json()
    assert s["total_t_co2e"] == 0
    assert s["data_quality"]["records_without_result"] == 1


def test_summary_includes_s3_target_status(client, org_with_data):
    h = org_with_data["headers"]
    fac = org_with_data["facility"]
    add_activity(client, h, "electricity", 30000, "kWh", "2025-01-01", "2025-01-31", facility_id=fac)
    r = client.post("/analytics/targets", headers=h, json={"baseline_year": 2025, "target_year": 2030, "reduction_pct": 40})
    assert r.status_code == 201, r.text
    t = client.get("/coach/summary", headers=h).json()["targets"][0]
    assert t["baseline_year"] == 2025 and t["as_of_year"] == 2026
    assert t["status"] in ("on_track", "off_track")
    assert t["baseline_t"] == pytest.approx(10.89, abs=0.01)  # 30,000 kWh x 0.363


def test_insights_from_ai(client, org_with_data, use_llm):
    use_llm(FakeLLM(json_response={"insights": ["Electricity is 67% of emissions.", "Gas heating is second."]}))
    r = client.get("/coach/insights", headers=org_with_data["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "ai"
    assert body["insights"][0].startswith("Electricity")
    assert body["summary"]["total_t_co2e"] > 0


def test_insights_rule_fallback_without_ai(client, org_with_data, use_llm):
    use_llm(None)
    body = client.get("/coach/insights", headers=org_with_data["headers"]).json()
    assert body["source"] == "rules"
    assert "electricity" in body["insights"][0]
    assert any("Operations" in i for i in body["insights"])


def test_insights_empty_org(client, use_llm):
    use_llm(FakeLLM())
    headers, _ = register(client)
    add_facility(client, headers)
    body = client.get("/coach/insights", headers=headers).json()
    assert body["warning"] == "No calculated emissions yet."
