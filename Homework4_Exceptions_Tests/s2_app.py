"""Homework 4 - Exceptions and unit tests (S2: Emission Engine, Tuba Jabeen).

A small Flask app (SQLite in memory for tests) with a calculation endpoint.
Every failure raises one of our own S2 exceptions; ONE error handler turns it into JSON
with the right HTTP status. Nothing is ever silently calculated as 0.
"""
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy

from exceptions import CarbonLensException
from s2_exceptions import (S2_FactorNotFoundError, S2_IncompatibleUnitError,
                           S2_InvalidAmountError, S2_UnknownUnitError)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
db = SQLAlchemy(app)

UNITS = {"kWh": ("energy", Decimal(1)), "MWh": ("energy", Decimal(1000)),
         "kg": ("mass", Decimal(1)), "tonne": ("mass", Decimal(1000)),
         "litre": ("volume", Decimal(1)), "m3": ("volume", Decimal(1000)),
         "km": ("distance", Decimal(1)), "miles": ("distance", Decimal("1.609344"))}


class Factor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_type = db.Column(db.String(60), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    kg_co2e_per_unit = db.Column(db.Numeric(14, 6), nullable=False)


with app.app_context():
    db.create_all()


def convert(amount, from_unit, to_unit):
    for u in (from_unit, to_unit):
        if u not in UNITS:
            raise S2_UnknownUnitError(f"Unknown unit '{u}'", status_code=400)
    (d1, r1), (d2, r2) = UNITS[from_unit], UNITS[to_unit]
    if d1 != d2:
        raise S2_IncompatibleUnitError(f"Cannot convert {from_unit} ({d1}) to {to_unit} ({d2})", status_code=422)
    return amount * r1 / r2


def parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise S2_InvalidAmountError("amount must be a number", status_code=400)
    if not amount.is_finite() or amount < 0:
        raise S2_InvalidAmountError("amount must be zero or positive", status_code=400)
    return amount


def calculate_kg(activity_type, amount, unit):
    factor = Factor.query.filter_by(activity_type=activity_type).first()
    if factor is None:
        raise S2_FactorNotFoundError(f"No emission factor for '{activity_type}'", status_code=404)
    converted = convert(parse_amount(amount), unit, factor.unit)
    return (converted * factor.kg_co2e_per_unit).quantize(Decimal("0.0001"))


@app.errorhandler(CarbonLensException)
def handle_error(error):
    return jsonify({"error": error.__class__.__name__, "message": error.message}), error.status_code


@app.route("/s2/factors", methods=["GET"])
def list_factors():
    return jsonify([{"id": f.id, "activity_type": f.activity_type, "unit": f.unit,
                     "kg_co2e_per_unit": float(f.kg_co2e_per_unit)} for f in Factor.query.all()])


@app.route("/s2/factors", methods=["POST"])
def add_factor():
    data = request.get_json(silent=True) or {}
    if not data.get("activity_type") or data.get("unit") is None or data.get("kg_co2e_per_unit") is None:
        raise S2_InvalidAmountError("activity_type, unit and kg_co2e_per_unit are required", status_code=400)
    if data["unit"] not in UNITS:
        raise S2_UnknownUnitError(f"Unknown unit '{data['unit']}'", status_code=400)
    db.session.add(Factor(activity_type=data["activity_type"], unit=data["unit"],
                          kg_co2e_per_unit=parse_amount(data["kg_co2e_per_unit"])))
    db.session.commit()
    return jsonify({"message": "Factor added"}), 201


@app.route("/s2/calculate", methods=["POST"])
def calculate():
    data = request.get_json(silent=True) or {}
    if "amount" not in data or "unit" not in data or "activity_type" not in data:
        raise S2_InvalidAmountError("activity_type, amount and unit are required", status_code=400)
    kg = calculate_kg(data["activity_type"], data["amount"], data["unit"])
    return jsonify({"activity_type": data["activity_type"], "kg_co2e": float(kg)})
