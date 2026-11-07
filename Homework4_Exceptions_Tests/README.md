# Homework 4: Exceptions and Automated Tests

This folder contains three Flask subsystems:

- **S1 / Saba:** student data API in `s1_app.py`
- **S2 / Tuba:** emission-factor and calculation API in `s2_app.py`
- **S3:** analytics and reporting API in `s3_app.py`

## Setup

Open Terminal and go to this folder:

```bash
cd /Users/sameer/Documents/MDT/CarbonLens/carbonlens/Homework4_Exceptions_Tests
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the required packages:

```bash
python -m pip install Flask Flask-SQLAlchemy pytest
```

## Run all tests

Run the complete test suite:

```bash
python -m pytest -q
```

Run one subsystem's tests:

```bash
python -m pytest -q test_s1_app.py       # Saba / S1
python -m pytest -q test_s2_app.py    # Tuba / S2
python -m pytest -q test_s3_app.py    # S3 analytics
```

## Run the Flask applications

Run only one application at a time. Each application uses port `5000`.

### Saba / S1

```bash
python -m flask --app s1_app run
```

Endpoint:

```text
GET  http://127.0.0.1:5000/students
POST http://127.0.0.1:5000/students
```

Example request:

```bash
curl -X POST http://127.0.0.1:5000/students \
  -H "Content-Type: application/json" \
  -d '{"name":"Sameer","course":"MDT"}'
```

### Tuba / S2

```bash
python -m flask --app s2_app run
```

Endpoints:

```text
GET  http://127.0.0.1:5000/s2/factors
POST http://127.0.0.1:5000/s2/factors
POST http://127.0.0.1:5000/s2/calculate
```

Example calculation:

```bash
curl -X POST http://127.0.0.1:5000/s2/calculate \
  -H "Content-Type: application/json" \
  -d '{"activity_type":"electricity","amount":450,"unit":"kWh"}'
```

### S3 analytics

```bash
python -m flask --app s3_app run
```

When S3 starts through `flask run`, it creates one demonstration record if the database is empty.

Endpoints:

```text
GET  http://127.0.0.1:5000/s3/records
POST http://127.0.0.1:5000/s3/records
GET  http://127.0.0.1:5000/s3/report
```

Add an emissions record:

```bash
curl -X POST http://127.0.0.1:5000/s3/records \
  -H "Content-Type: application/json" \
  -d '{"activity_type":"diesel","emission_date":"2026-01-15","kg_co2e":5.25}'
```

View reports in a browser or with `curl`:

```text
http://127.0.0.1:5000/s3/records
http://127.0.0.1:5000/s3/report?metric=total
http://127.0.0.1:5000/s3/report?metric=average
http://127.0.0.1:5000/s3/report?metric=by_activity
http://127.0.0.1:5000/s3/report?start_date=2026-01-01&end_date=2026-12-31
```

## Notes

- The applications use an in-memory SQLite database for the homework tests.
- Data disappears when the Flask server stops.
- Custom exceptions are defined in `exceptions.py`, `s2_exceptions.py`, and `s3_exceptions.py`.
- Flask converts custom exceptions into JSON responses containing `error` and `message`.

  

## System Design
(S1 UML Diagram)
<img width="1621" height="957" alt="Screenshot 2026-11-07 at 7 22 55 PM" src="https://github.com/user-attachments/assets/c3f94dab-096c-4899-9b40-9282c9b799c4" />

## Video Presentation
Watch our 5-minute team presentation here:
 **[Click here to watch the Team Video](PASTE_YOUR_YOUTUBE_LINK_HERE)**



