import os
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class CarbonActivity(db.Model):
    __tablename__ = "carbon_activities"
    id = db.Column(db.Integer, primary_key=True)
    activity = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(30), nullable=False)
    kg_co2e = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {"id": self.id, "activity": self.activity, "category": self.category,
                "amount": self.amount, "unit": self.unit, "kg_co2e": self.kg_co2e}


class CarbonActivityRepository:
    """Database access layer for carbon activity records."""

    @staticmethod
    def all():
        return CarbonActivity.query.order_by(CarbonActivity.id).all()

    @staticmethod
    def create(activity, category, amount, unit, kg_co2e):
        record = CarbonActivity(activity=activity, category=category, amount=amount,
                                unit=unit, kg_co2e=kg_co2e)
        db.session.add(record)
        db.session.commit()
        return record


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "mysql+pymysql://root:rootpassword@localhost:3306/homework_db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    @app.get("/")
    def home():
        return jsonify({"message": "Sameer CarbonLens API", "endpoint": "/activities"})

    @app.get("/activities")
    def activities():
        return jsonify([record.to_dict() for record in CarbonActivityRepository.all()])

    @app.post("/activities")
    def add_activity():
        data = request.get_json(silent=True) or {}
        activity = str(data.get("activity", "")).strip()
        category = str(data.get("category", "")).strip()
        unit = str(data.get("unit", "")).strip()
        try:
            amount = float(data["amount"])
            kg_co2e = float(data["kg_co2e"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "amount and kg_co2e must be numbers"}), 400
        if not activity or not category or not unit or amount < 0 or kg_co2e < 0:
            return jsonify({"error": "activity, category, unit and non-negative values are required"}), 400
        return jsonify(CarbonActivityRepository.create(activity, category, amount, unit, kg_co2e).to_dict()), 201

    return app


app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        if not CarbonActivity.query.first():
            db.session.add(CarbonActivity(
                activity="Electricity usage",
                category="Energy",
                amount=250,
                unit="kWh",
                kg_co2e=105,
            ))
            db.session.commit()
            print("Sample carbon activity created.")
    app.run(debug=True, port=5000)
