"""FR-4.08 chat assistant, FR-4.09 learning content generation, FR-4.10 approval workflow."""
from tests.test_coach.conftest import FakeLLM, invite, register

LEARNING = {"title": "Why electricity matters", "body": "Electricity is often the largest source of emissions. " * 5}


# ---------- FR-4.08 chat ----------
def test_chat_conversation_is_grounded_and_persisted(client, org_with_data, use_llm):
    fake = use_llm(FakeLLM(chat_response="Electricity is your biggest source (13.79 t CO2e)."))
    h = org_with_data["headers"]
    sid = client.post("/coach/chat/sessions", headers=h, json={}).json()["id"]

    r = client.post(f"/coach/chat/sessions/{sid}/messages", headers=h, json={"content": "What is our biggest source?"})
    assert r.status_code == 200, r.text
    reply = r.json()
    assert reply["degraded"] is False
    assert reply["assistant_message"]["content"].startswith("Electricity")
    assert reply["assistant_message"]["tokens_in"] == 120

    # The model received the company's footprint as context
    assert '"total_t_co2e": 20.43' in fake.calls[0]

    client.post(f"/coach/chat/sessions/{sid}/messages", headers=h, json={"content": "And the second?"})
    msgs = client.get(f"/coach/chat/sessions/{sid}/messages", headers=h).json()
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert "What is our biggest source?" in fake.calls[1]  # history is sent on the next turn

    sessions = client.get("/coach/chat/sessions", headers=h).json()
    assert sessions[0]["title"] == "What is our biggest source?"

    assert client.delete(f"/coach/chat/sessions/{sid}", headers=h).status_code == 204
    assert client.get(f"/coach/chat/sessions/{sid}/messages", headers=h).status_code == 404


def test_usage_counts_tokens(client, org_with_data, use_llm):
    use_llm(FakeLLM())
    h = org_with_data["headers"]
    sid = client.post("/coach/chat/sessions", headers=h, json={}).json()["id"]
    client.post(f"/coach/chat/sessions/{sid}/messages", headers=h, json={"content": "Hi"})
    u = client.get("/coach/usage", headers=h).json()
    assert u["chat_messages"] == 2 and u["tokens_in"] == 120 and u["tokens_out"] == 40


# ---------- FR-4.09 / FR-4.10 learning content ----------
def test_learning_generate_approve_and_visibility(client, use_llm):
    fake = use_llm(FakeLLM(json_response=LEARNING))
    admin, _ = register(client)
    contributor = invite(client, admin, "contributor")

    r = client.post("/coach/learning/generate", headers=admin, json={"topic": "Scope 2 basics", "audience": "contributor"})
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["status"] == "draft" and item["topic"] == "Why electricity matters"
    assert "Scope 2 basics" in fake.calls[0]

    # Contributors can't see drafts
    assert all(c["id"] != item["id"] for c in client.get("/coach/learning", headers=contributor).json())
    assert client.get(f"/coach/learning/{item['id']}", headers=contributor).status_code == 404
    # ...and can't approve
    assert client.post(f"/coach/learning/{item['id']}/approve", headers=contributor).status_code == 403

    assert client.post(f"/coach/learning/{item['id']}/approve", headers=admin).json()["status"] == "approved"
    assert any(c["id"] == item["id"] for c in client.get("/coach/learning", headers=contributor).json())


def test_learning_requires_ai(client, use_llm):
    use_llm(None)
    admin, _ = register(client)
    r = client.post("/coach/learning/generate", headers=admin, json={"topic": "Heat pumps", "audience": "manager"})
    assert r.status_code == 503


def test_learning_rejects_unusable_output(client, use_llm):
    use_llm(FakeLLM(json_response={"title": "x", "body": "too short"}))
    admin, _ = register(client)
    r = client.post("/coach/learning/generate", headers=admin, json={"topic": "Heat pumps"})
    assert r.status_code == 502
