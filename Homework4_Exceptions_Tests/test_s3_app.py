from datetime import date
from decimal import Decimal

import pytest

from s3_app import EmissionRecord, app, db


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        db.session.add_all([
            EmissionRecord(activity_type="electricity", emission_date=date(2026, 1, 10), kg_co2e=Decimal("10.5")),
            EmissionRecord(activity_type="diesel", emission_date=date(2026, 1, 15), kg_co2e=Decimal("5.25")),
            EmissionRecord(activity_type="electricity", emission_date=date(2026, 2, 1), kg_co2e=Decimal("4.25")),
        ])
        db.session.commit()
    with app.test_client() as test_client:
        yield test_client
    with app.app_context():
        db.drop_all()


def test_1_seeded_records_exist(client):
    assert client.get("/s3/records").status_code == 200
    assert len(client.get("/s3/records").json) == 3


def test_2_record_has_required_fields(client):
    assert {"activity_type", "emission_date", "kg_co2e"}.issubset(client.get("/s3/records").json[0])


def test_3_add_record(client):
    response = client.post("/s3/records", json={"activity_type": "rail", "emission_date": "2026-03-01", "kg_co2e": 2})
    assert response.status_code == 201


def test_4_missing_record_field_is_rejected(client):
    response = client.post("/s3/records", json={"activity_type": "rail"})
    assert response.status_code == 400


def test_5_invalid_date_is_rejected(client):
    response = client.post("/s3/records", json={"activity_type": "rail", "emission_date": "tomorrow", "kg_co2e": 2})
    assert response.json["error"] == "S3_InvalidDateRangeError"


def test_6_negative_emissions_are_rejected(client):
    response = client.post("/s3/records", json={"activity_type": "rail", "emission_date": "2026-03-01", "kg_co2e": -1})
    assert response.json["error"] == "S3_InvalidRecordError"


def test_7_total_report(client):
    response = client.get("/s3/report?metric=total")
    assert response.status_code == 200 and response.json["kg_co2e"] == 20.0


def test_8_average_report(client):
    response = client.get("/s3/report?metric=average")
    assert response.json["kg_co2e"] == pytest.approx(20 / 3)


def test_9_grouped_report(client):
    response = client.get("/s3/report?metric=by_activity")
    assert response.json["kg_co2e_by_activity"] == {"diesel": 5.25, "electricity": 14.75}


def test_10_date_filter(client):
    response = client.get("/s3/report?start_date=2026-02-01")
    assert response.json["kg_co2e"] == 4.25


def test_11_end_date_filter(client):
    response = client.get("/s3/report?end_date=2026-01-15")
    assert response.json["kg_co2e"] == 15.75


def test_12_reversed_dates_are_rejected(client):
    response = client.get("/s3/report?start_date=2026-03-01&end_date=2026-01-01")
    assert response.json["error"] == "S3_InvalidDateRangeError"


def test_13_unknown_metric_is_rejected(client):
    response = client.get("/s3/report?metric=median")
    assert response.json["error"] == "S3_UnsupportedMetricError"


def test_14_empty_date_range_returns_404(client):
    response = client.get("/s3/report?start_date=2027-01-01")
    assert response.status_code == 404 and response.json["error"] == "S3_NoDataError"


def test_15_unknown_route_is_404(client):
    assert client.get("/s3/unknown").status_code == 404


def test_16_report_includes_record_count(client):
    assert client.get("/s3/report").json["record_count"] == 3

