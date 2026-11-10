"""Non-functional requirements of S4."""
from tests.test_coach.conftest import FakeLLM, add_activity, add_facility, invite, register


# NFR-4.01 graceful degradation
def test_auto_mode_falls_back_to_rules_when_ai_fails(client, org_with_data, use_llm):
    use_llm(FakeLLM(fail=True))
    r = client.post("/coach/recommendations/generate", headers=org_with_data["headers"], json={"mode": "auto"})
    assert r.status_code == 201
    body = r.json()
    assert body["source_used"] == "rules" and body["created"]
    assert "unavailable" in body["warning"]


def test_chat_degrades_instead_of_failing(client, org_with_data, use_llm):
    use_llm(FakeLLM(fail=True))
    h = org_with_data["headers"]
    sid = client.post("/coach/chat/sessions", headers=h, json={}).json()["id"]
    r = client.post(f"/coach/chat/sessions/{sid}/messages", headers=h, json={"content": "Hello"})
    assert r.status_code == 200
    assert r.json()["degraded"] is True
    assert "not available" in r.json()["assistant_message"]["content"]


def test_insights_fall_back_when_ai_fails(client, org_with_data, use_llm):
    use_llm(FakeLLM(fail=True))
    body = client.get("/coach/insights", headers=org_with_data["headers"]).json()
    assert body["source"] == "rules" and body["warning"]


def test_ai_returning_garbage_falls_back(client, org_with_data, use_llm):
    use_llm(FakeLLM(json_response={"something": "else"}))
    body = client.post("/coach/recommendations/generate", headers=org_with_data["headers"], json={}).json()
    assert body["source_used"] == "rules"


# NFR-4.02 privacy: no personal data or free text leaves the system
def test_prompts_contain_no_personal_data(client, org_with_data, use_llm):
    fake = use_llm(FakeLLM(json_response={"insights": ["ok"]}, chat_response="ok"))
    h = org_with_data["headers"]
    client.get("/coach/insights", headers=h)
    client.post("/coach/recommendations/generate", headers=h, json={})
    sid = client.post("/coach/chat/sessions", headers=h, json={}).json()["id"]
    client.post(f"/coach/chat/sessions/{sid}/messages", headers=h, json={"content": "Summarise please"})
    assert len(fake.calls) >= 3
    for prompt in fake.calls:
        assert org_with_data["email"] not in prompt
        assert "Secret Industries" not in prompt
        assert "confidential invoice 4711" not in prompt
        assert "Admin User" not in prompt


# NFR-4.03 tenant isolation
def test_other_org_cannot_access_recommendations_or_chats(client, org_with_data, use_llm):
    use_llm(FakeLLM())
    a = org_with_data["headers"]
    rec = client.post("/coach/recommendations/generate", headers=a, json={"mode": "rules"}).json()["created"][0]
    sid = client.post("/coach/chat/sessions", headers=a, json={}).json()["id"]

    b, _ = register(client, org_name="Other Org")
    add_activity(client, b, "electricity", 10, "kWh", facility_id=add_facility(client, b))
    assert client.get("/coach/recommendations", headers=b).json() == []
    assert client.get(f"/coach/recommendations/{rec['id']}", headers=b).status_code == 404
    assert client.patch(f"/coach/recommendations/{rec['id']}/status", headers=b,
                        json={"status": "accepted"}).status_code == 404
    assert client.get(f"/coach/chat/sessions/{sid}/messages", headers=b).status_code == 404
    assert client.get("/coach/summary", headers=b).json()["total_t_co2e"] < 0.01


# NFR-4.04 role-based access
def test_contributor_cannot_generate_or_change_status(client, org_with_data):
    admin = org_with_data["headers"]
    contributor = invite(client, admin, "contributor")
    manager = invite(client, admin, "manager")
    assert client.post("/coach/recommendations/generate", headers=contributor, json={"mode": "rules"}).status_code == 403
    rec = client.post("/coach/recommendations/generate", headers=manager, json={"mode": "rules"}).json()["created"][0]
    assert client.patch(f"/coach/recommendations/{rec['id']}/status", headers=contributor,
                        json={"status": "accepted"}).status_code == 403
    # contributors can still read recommendations and chat
    assert client.get("/coach/recommendations", headers=contributor).status_code == 200
    assert client.post("/coach/chat/sessions", headers=contributor, json={}).status_code == 201


def test_requires_authentication(client):
    assert client.get("/coach/summary").status_code == 401
    assert client.get("/coach/recommendations").status_code == 401


# NFR-4.09 input limits
def test_chat_message_length_limit(client, org_with_data, use_llm):
    use_llm(FakeLLM())
    h = org_with_data["headers"]
    sid = client.post("/coach/chat/sessions", headers=h, json={}).json()["id"]
    r = client.post(f"/coach/chat/sessions/{sid}/messages", headers=h, json={"content": "x" * 2001})
    assert r.status_code == 422
    r = client.post(f"/coach/chat/sessions/{sid}/messages", headers=h, json={"content": "   "})
    assert r.status_code == 422
