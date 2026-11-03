import pytest
from decimal import Decimal

from s2_app import Factor, app, calculate_kg, convert, db
from s2_exceptions import (S2_FactorNotFoundError, S2_IncompatibleUnitError,
                           S2_InvalidAmountError, S2_UnknownUnitError)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        db.session.add_all([Factor(activity_type="electricity", unit="kWh", kg_co2e_per_unit=Decimal("0.363")),
                            Factor(activity_type="diesel", unit="litre", kg_co2e_per_unit=Decimal("2.58354"))])
        db.session.commit()
    with app.test_client() as c:
        yield c
    with app.app_context():
        db.drop_all()


# --- Tests 1-5: database model --------------------------------------------------
def test_1_factor_is_saved_with_id(client):
    with app.app_context():
        f = Factor(activity_type="rail", unit="km", kg_co2e_per_unit=Decimal("0.035"))
        db.session.add(f)
        db.session.commit()
        assert f.id is not None


def test_2_seeded_rows_are_found(client):
    with app.app_context():
        assert Factor.query.count() == 2


def test_3_activity_type_is_required(client):
    with app.app_context():
        with pytest.raises(Exception):
            db.session.add(Factor(activity_type=None, unit="kWh", kg_co2e_per_unit=Decimal("1")))
            db.session.commit()
        db.session.rollback()


def test_4_factor_value_is_required(client):
    with app.app_context():
        with pytest.raises(Exception):
            db.session.add(Factor(activity_type="x", unit="kWh", kg_co2e_per_unit=None))
            db.session.commit()
        db.session.rollback()


def test_5_decimal_precision_is_kept(client):
    with app.app_context():
        f = Factor.query.filter_by(activity_type="diesel").first()
        assert Decimal(str(f.kg_co2e_per_unit)) == Decimal("2.58354")


# --- Tests 6-10: API endpoints --------------------------------------------------
def test_6_list_factors(client):
    res = client.get("/s2/factors")
    assert res.status_code == 200 and len(res.json) == 2


def test_7_add_factor(client):
    res = client.post("/s2/factors", json={"activity_type": "rail", "unit": "km", "kg_co2e_per_unit": "0.035"})
    assert res.status_code == 201


def test_8_calculate_electricity(client):
    res = client.post("/s2/calculate", json={"activity_type": "electricity", "amount": 450, "unit": "kWh"})
    assert res.status_code == 200 and res.json["kg_co2e"] == 163.35


def test_9_calculate_converts_units(client):
    res = client.post("/s2/calculate", json={"activity_type": "electricity", "amount": 1, "unit": "MWh"})
    assert res.json["kg_co2e"] == 363.0


def test_10_unknown_route_is_404(client):
    assert client.get("/s2/nothing").status_code == 404


# --- Tests 11-15: exception handling ---------------------------------------------
def test_11_missing_fields_gives_400(client):
    res = client.post("/s2/calculate", json={"amount": 5})
    assert res.status_code == 400 and res.json["error"] == "S2_InvalidAmountError"


def test_12_negative_amount_is_rejected(client):
    res = client.post("/s2/calculate", json={"activity_type": "diesel", "amount": -1, "unit": "litre"})
    assert res.status_code == 400 and "positive" in res.json["message"]


def test_13_unknown_unit_gives_400(client):
    res = client.post("/s2/calculate", json={"activity_type": "diesel", "amount": 1, "unit": "bucket"})
    assert res.status_code == 400 and res.json["error"] == "S2_UnknownUnitError"


def test_14_incompatible_unit_gives_422(client):
    res = client.post("/s2/calculate", json={"activity_type": "electricity", "amount": 5, "unit": "litre"})
    assert res.status_code == 422 and res.json["error"] == "S2_IncompatibleUnitError"


def test_15_missing_factor_gives_404_not_zero(client):
    res = client.post("/s2/calculate", json={"activity_type": "unobtainium", "amount": 5, "unit": "kg"})
    assert res.status_code == 404 and res.json["error"] == "S2_FactorNotFoundError"
    assert "kg_co2e" not in res.json


# --- Extra: direct tests of the functions (no HTTP) -----------------------------------
def test_16_convert_miles_to_km():
    assert convert(Decimal(10), "miles", "km") == Decimal("16.09344")


def test_17_functions_raise_the_right_exceptions(client):
    with app.app_context():
        with pytest.raises(S2_InvalidAmountError):
            calculate_kg("diesel", "abc", "litre")
        with pytest.raises(S2_UnknownUnitError):
            convert(Decimal(1), "bucket", "kg")
        with pytest.raises(S2_IncompatibleUnitError):
            convert(Decimal(1), "kg", "kWh")
        with pytest.raises(S2_FactorNotFoundError):
            calculate_kg("nothing", 1, "kg")
