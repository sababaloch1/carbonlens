"""S3 Analytics and Reporting subsystem for CarbonLens."""

from datetime import date
from decimal import Decimal, InvalidOperation
import os

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy

from exceptions import CarbonLensException
from s3_exceptions import (
    S3_InvalidDateRangeError,
    S3_InvalidRecordError,
    S3_NoDataError,
    S3_UnsupportedMetricError,
)

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class EmissionRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    activity_type = db.Column(db.String(60), nullable=False)
    emission_date = db.Column(db.Date, nullable=False)
    kg_co2e = db.Column(db.Numeric(14, 4), nullable=False)


with app.app_context():
    db.create_all()
    # Add one demonstration record when launched with ``flask run``.
    # Do not seed during pytest collection; tests create their own data.
    if os.environ.get("FLASK_RUN_FROM_CLI") == "true" and EmissionRecord.query.count() == 0:
        db.session.add(EmissionRecord(
            activity_type="electricity",
            emission_date=date.today(),
            kg_co2e=Decimal("10.5"),
        ))
        db.session.commit()


@app.errorhandler(CarbonLensException)
def handle_s3_error(error):
    return jsonify({"error": error.__class__.__name__, "message": error.message}), error.status_code


def parse_date(value, field_name="date"):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise S3_InvalidDateRangeError(
            f"{field_name} must use YYYY-MM-DD format", status_code=400
        )


def parse_emissions(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise S3_InvalidRecordError("kg_co2e must be a number", status_code=400)
    if not amount.is_finite() or amount < 0:
        raise S3_InvalidRecordError("kg_co2e must be zero or positive", status_code=400)
    return amount


def filtered_records(start_date=None, end_date=None):
    query = EmissionRecord.query
    if start_date:
        query = query.filter(EmissionRecord.emission_date >= start_date)
    if end_date:
        query = query.filter(EmissionRecord.emission_date <= end_date)
    return query.order_by(EmissionRecord.emission_date, EmissionRecord.id).all()


def build_report(records, metric="total"):
    if metric not in {"total", "by_activity", "average"}:
        raise S3_UnsupportedMetricError(
            f"Unsupported metric '{metric}'", status_code=400
        )
    if not records:
        raise S3_NoDataError("No emissions data exists for this report", status_code=404)

    amounts = [Decimal(str(record.kg_co2e)) for record in records]
    total = sum(amounts, Decimal("0"))
    if metric == "total":
        return {"metric": metric, "kg_co2e": float(total), "record_count": len(records)}
    if metric == "average":
        return {"metric": metric, "kg_co2e": float(total / len(records)), "record_count": len(records)}

    grouped = {}
    for record, amount in zip(records, amounts):
        grouped[record.activity_type] = grouped.get(record.activity_type, Decimal("0")) + amount
    return {
        "metric": metric,
        "kg_co2e_by_activity": {key: float(value) for key, value in sorted(grouped.items())},
        "record_count": len(records),
    }


@app.route("/s3/records", methods=["POST"])
def add_record():
    data = request.get_json(silent=True) or {}
    required = {"activity_type", "emission_date", "kg_co2e"}
    if not required.issubset(data) or not data.get("activity_type"):
        raise S3_InvalidRecordError(
            "activity_type, emission_date and kg_co2e are required", status_code=400
        )
    record = EmissionRecord(
        activity_type=data["activity_type"],
        emission_date=parse_date(data["emission_date"], "emission_date"),
        kg_co2e=parse_emissions(data["kg_co2e"]),
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"message": "Emission record added", "id": record.id}), 201


@app.route("/s3/records", methods=["GET"])
def list_records():
    records = EmissionRecord.query.order_by(EmissionRecord.emission_date, EmissionRecord.id).all()
    return jsonify([
        {"id": r.id, "activity_type": r.activity_type,
         "emission_date": r.emission_date.isoformat(), "kg_co2e": float(r.kg_co2e)}
        for r in records
    ])


@app.route("/s3/report", methods=["GET"])
def report():
    start = request.args.get("start_date")
    end = request.args.get("end_date")
    if start and end:
        start_date, end_date = parse_date(start, "start_date"), parse_date(end, "end_date")
        if start_date > end_date:
            raise S3_InvalidDateRangeError("start_date cannot be after end_date", status_code=400)
    else:
        start_date = parse_date(start, "start_date") if start else None
        end_date = parse_date(end, "end_date") if end else None
    records = filtered_records(start_date, end_date)
    return jsonify(build_report(records, request.args.get("metric", "total")))

