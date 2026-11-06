"""Homework 3 - Web API + database access layer (S2: Emission Engine, Tuba Jabeen).

Flask API on top of MySQL (Docker). Table: emission_factors (loaded from seed/factors.csv).
Endpoints:
    GET  /s2/factors                 list all factors  (optional ?activity_type=diesel)
    GET  /s2/factors/<id>            one factor
    POST /s2/calculate               {"activity_type","amount","unit","region"} -> kg CO2e

Run MySQL:  docker compose up -d      (see docker-compose.yml, port 3307)
Run API:    python s2_app.py          (port 5001)
For a quick test without MySQL:  set S2_DATABASE_URL=sqlite:///:memory:
"""
import csv
import os
from decimal import Decimal
from pathlib import Path

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy

SEED = Path(__file__).resolve().parents[1] / "seed" / "factors.csv"
RATIO = {"kWh": 1, "MWh": 1000, "kg": 1, "tonne": 1000, "litre": 1, "m3": 1000,
         "km": 1, "miles": Decimal("1.609344"), "passenger_km": 1, "night": 1}
DIMENSION = {"kWh": "energy", "MWh": "energy", "kg": "mass", "tonne": "mass", "litre": "volume",
             "m3": "volume", "km": "distance", "miles": "distance", "passenger_km": "passenger_km",
             "night": "night"}

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "S2_DATABASE_URL", "mysql+pymysql://root:rootpassword@localhost:3307/homework_s2")
db = SQLAlchemy(app)


class EmissionFactorRow(db.Model):
    __tablename__ = "emission_factors"
    id = db.Column(db.Integer, primary_key=True)
    activity_type = db.Column(db.String(60), nullable=False, index=True)
    region = db.Column(db.String(20), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    kg_co2e_per_unit = db.Column(db.Numeric(14, 6), nullable=False)
    source = db.Column(db.String(500))

    def to_dict(self):
        return {"id": self.id, "activity_type": self.activity_type, "region": self.region,
                "year": self.year, "unit": self.unit,
                "kg_co2e_per_unit": float(self.kg_co2e_per_unit), "source": self.source}


# ---------------------------------------------------------- access layer
class FactorRepository:
    """All database access for factors lives here, routes never write SQL."""

    @staticmethod
    def all(activity_type=None):
        q = EmissionFactorRow.query
        if activity_type:
            q = q.filter_by(activity_type=activity_type)
        return q.order_by(EmissionFactorRow.id).all()

    @staticmethod
    def get(factor_id):
        return db.session.get(EmissionFactorRow, factor_id)

    @staticmethod
    def best_match(activity_type, region, year):
        for r in (region, "GLOBAL"):
            rows = EmissionFactorRow.query.filter_by(activity_type=activity_type, region=r).all()
            if rows:
                return min(rows, key=lambda f: abs(f.year - year))
        return None

    @staticmethod
    def seed_from_csv():
        if EmissionFactorRow.query.first():
            return 0
        with open(SEED, newline="", encoding="utf-8") as f:
            rows = [EmissionFactorRow(activity_type=r["activity_type"], region=r["region"],
                                      year=int(r["year"]), unit=r["unit"],
                                      kg_co2e_per_unit=Decimal(r["kg_co2e_per_unit"]),
                                      source=r["source"][:500]) for r in csv.DictReader(f)]
        db.session.add_all(rows)
        db.session.commit()
        return len(rows)


def init_db():
    with app.app_context():
        db.create_all()
        FactorRepository.seed_from_csv()


# --------------------------------------------------------------- endpoints
@app.get("/s2/factors")
def list_factors():
    rows = FactorRepository.all(request.args.get("activity_type"))
    return jsonify([r.to_dict() for r in rows])


@app.get("/s2/factors/<int:factor_id>")
def one_factor(factor_id):
    row = FactorRepository.get(factor_id)
    if row is None:
        return jsonify({"error": "factor not found"}), 404
    return jsonify(row.to_dict())

@app.get("/s2/calculate")
def calculate_help():
       return jsonify({"message": "Send a POST request with JSON: "
                       "{\"activity_type\": \"electricity\", \"amount\": 450, \"unit\": \"kWh\"}"})



@app.post("/s2/calculate")
def calculate():
    data = request.get_json(silent=True) or {}
    try:
        activity, unit = data["activity_type"], data["unit"]
        amount = Decimal(str(data["amount"]))
    except (KeyError, ArithmeticError):
        return jsonify({"error": "activity_type, amount and unit are required"}), 400
    if amount < 0 or unit not in RATIO:
        return jsonify({"error": "amount must be >= 0 and unit must be known"}), 400
    factor = FactorRepository.best_match(activity, data.get("region", "DE"), int(data.get("year", 2026)))
    if factor is None:
        return jsonify({"error": f"no emission factor for '{activity}'"}), 404
    if DIMENSION[unit] != DIMENSION[factor.unit]:
        return jsonify({"error": f"cannot convert {unit} to {factor.unit}"}), 422
    kg = amount * Decimal(str(RATIO[unit])) / Decimal(str(RATIO[factor.unit])) * factor.kg_co2e_per_unit
    return jsonify({"activity_type": activity, "amount": float(amount), "unit": unit,
                    "factor_id": factor.id, "kg_co2e": float(kg.quantize(Decimal("0.0001")))})


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5001)
