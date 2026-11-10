"""FR-4.07 what-if scenarios, calculated by S2's simulate_change."""
import pytest

from tests.test_coach.conftest import invite, register


def test_list_scenarios(client, org_with_data):
    sc = {s["id"]: s for s in client.get("/coach/what-if/scenarios", headers=org_with_data["headers"]).json()}
    assert sc["flights_to_rail"]["available"] is True
    assert sc["fleet_to_ev"]["available"] is False  # org has no fleet data


def test_flights_to_rail_uses_engine_factors(client, org_with_data):
    r = client.post("/coach/what-if", headers=org_with_data["headers"],
                    json={"scenario_id": "flights_to_rail", "change_pct": 50})
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    # before: 12,000 pkm x 0.12786 = 1.534 t; after: 6,000 x 0.12786 + 6,000 x 0.03092 = 0.953 t
    assert res["before_t_co2e"] == pytest.approx(1.534, abs=0.001)
    assert res["after_t_co2e"] == pytest.approx(0.953, abs=0.001)
    assert res["saving_t_co2e"] == pytest.approx(0.582, abs=0.001)
    assert res["saving_cost_eur"] is None  # no flight/rail tariff in the engine, so no cost claim
    assert r.json()["saved_recommendation"] is None


def test_reduce_electricity_includes_cost_saving(client, org_with_data):
    res = client.post("/coach/what-if", headers=org_with_data["headers"],
                      json={"scenario_id": "reduce_electricity", "change_pct": 10}).json()["result"]
    assert res["saving_t_co2e"] == pytest.approx(1.379, abs=0.001)
    assert res["saving_pct"] == pytest.approx(10.0)
    assert res["saving_cost_eur"] > 0  # S2 has a DE electricity tariff


def test_scenario_without_data_is_rejected(client, org_with_data):
    r = client.post("/coach/what-if", headers=org_with_data["headers"],
                    json={"scenario_id": "fleet_to_ev", "change_pct": 50})
    assert r.status_code == 422


def test_unknown_scenario_and_bad_pct(client, org_with_data):
    h = org_with_data["headers"]
    assert client.post("/coach/what-if", headers=h, json={"scenario_id": "nope"}).status_code == 404
    assert client.post("/coach/what-if", headers=h,
                       json={"scenario_id": "reduce_heating", "change_pct": 150}).status_code == 422


def test_save_as_recommendation_requires_manager(client, org_with_data):
    h = org_with_data["headers"]
    contributor = invite(client, h, "contributor")
    body = {"scenario_id": "reduce_heating", "change_pct": 20, "save": True}
    assert client.post("/coach/what-if", headers=contributor, json=body).status_code == 403

    r = client.post("/coach/what-if", headers=h, json=body)
    assert r.status_code == 200, r.text
    rec = r.json()["saved_recommendation"]
    assert rec["title"] == "Reduce gas heating (20%)" and rec["scope"] == "scope_1"
    assert rec["est_saving_t_co2e"] == pytest.approx(0.61, abs=0.01)  # 20% of 3.039 t
    assert client.post("/coach/what-if", headers=h, json=body).status_code == 409  # not saved twice


def test_whatif_is_tenant_isolated(client, org_with_data):
    other, _ = register(client, org_name="Other")
    r = client.post("/coach/what-if", headers=other, json={"scenario_id": "flights_to_rail", "change_pct": 50})
    assert r.status_code == 422  # sees none of the first org's flights
