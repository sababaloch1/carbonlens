"""Shared fixtures for S4 (AI Sustainability Coach) tests.

Real S1 -> S2 -> S3 flow: activities are created through the API, S2 calculates them
with the seed factors, S3 aggregates them, and the coach reads S3.
No test talks to OpenAI: `get_llm` is overridden with FakeLLM (NFR-4.08).
"""
import uuid
from pathlib import Path

import pytest

from api.app.analytics.cache import analytics_cache
from api.app.coach.llm import LLMError, LLMUsage, get_llm
from api.app.engine.importer import load_seed_files
from api.app.main import app
from tests.conftest import TestingSessionLocal

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"


class FakeLLM:
    """Records every prompt and returns canned answers (or raises LLMError)."""

    model = "fake-model"

    def __init__(self, json_response=None, chat_response="Your biggest source is electricity.", fail=False):
        self.json_response = json_response or {}
        self.chat_response = chat_response
        self.fail = fail
        self.calls: list[str] = []

    def complete_json(self, system, user, max_tokens):
        self.calls.append(system + "\n" + user)
        if self.fail:
            raise LLMError("simulated outage")
        return self.json_response, LLMUsage(100, 50)

    def chat(self, messages, max_tokens):
        self.calls.append("\n".join(m["content"] for m in messages))
        if self.fail:
            raise LLMError("simulated outage")
        return self.chat_response, LLMUsage(120, 40)


@pytest.fixture(scope="module", autouse=True)
def seed_factors(client):
    """Load S2's real emission factors and tariffs into the test database."""
    db = TestingSessionLocal()
    load_seed_files(db, SEED_DIR)
    db.close()


@pytest.fixture(autouse=True)
def fresh_analytics_cache():
    analytics_cache.clear()  # S3 caches results for 5 minutes; tests need fresh numbers
    yield
    analytics_cache.clear()


@pytest.fixture
def use_llm():
    """Install a FakeLLM (or None = AI not configured) for the duration of a test."""
    def _install(llm):
        app.dependency_overrides[get_llm] = lambda: llm
        return llm
    yield _install
    app.dependency_overrides.pop(get_llm, None)


def register(client, org_name="Coach Org"):
    """Register a new org + admin and return (headers, email)."""
    email = f"{uuid.uuid4().hex[:10]}@test.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Admin User", "org_name": org_name,
    })
    assert r.status_code in (200, 201), r.text
    token = client.post("/auth/login", data={"username": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email


def add_facility(client, headers, name="Dortmund HQ", country="DE"):
    r = client.post("/facilities", headers=headers, json={"name": name, "city": "Dortmund", "country_code": country})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def invite(client, admin_headers, role):
    email = f"{uuid.uuid4().hex[:10]}@test.com"
    r = client.post("/users/invite", headers=admin_headers, json={
        "email": email, "password": "password123", "full_name": f"{role} user", "role": role,
    })
    assert r.status_code == 201, r.text
    token = client.post("/auth/login", data={"username": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def add_activity(client, headers, category, amount, unit, start="2026-01-01", end="2026-01-31",
                 facility_id=None, department_id=None, note=None):
    body = {"category": category, "amount": amount, "unit": unit, "period_start": start, "period_end": end}
    if facility_id:
        body["facility_id"] = facility_id
    if department_id:
        body["department_id"] = department_id
    if note:
        body["note"] = note
    r = client.post("/activities/", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def org_with_data(client):
    """An org whose activities S2 has calculated with the seed factors.

    electricity 38,000 kWh x 0.363 (DE)   = 13.794 t  (scope 2)
    natural gas 1,500 m3 x 2.02633        =  3.039 t  (scope 1)
    diesel        800 l  x 2.58354        =  2.067 t  (scope 1)
    short-haul 12,000 pkm x 0.12786       =  1.534 t  (scope 3)
    total                                 = 20.435 t
    """
    headers, email = register(client, org_name="Secret Industries GmbH")
    fac = add_facility(client, headers)
    ops = client.post("/departments", headers=headers, json={"name": "Operations"}).json()["id"]
    sales = client.post("/departments", headers=headers, json={"name": "Sales"}).json()["id"]
    add_activity(client, headers, "electricity", 20000, "kWh", facility_id=fac, department_id=ops,
                 note="confidential invoice 4711")
    add_activity(client, headers, "electricity", 18000, "kWh", "2026-02-01", "2026-02-28", facility_id=fac,
                 department_id=ops)
    add_activity(client, headers, "natural_gas", 1500, "m3", facility_id=fac, department_id=ops)
    add_activity(client, headers, "diesel", 800, "litre", facility_id=fac, department_id=sales)
    add_activity(client, headers, "flight_short_haul", 12000, "passenger_km", facility_id=fac, department_id=sales)
    return {"headers": headers, "email": email, "ops": ops, "sales": sales, "facility": fac}
