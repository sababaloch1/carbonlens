# Sameer CarbonLens Flask App

This project is a Flask web API connected to MySQL through SQLAlchemy. It stores carbon activities such as electricity usage and returns them as JSON.

## Requirements

- Python 3
- Docker Desktop

## Run the project

Open Terminal and move into this folder:

```bash
cd "/carbonlens/Homework3_Flask/Sameer"
```

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the Python packages:

```bash
python -m pip install -r requirements.txt
```

Start the MySQL database with Docker:

```bash
docker compose up -d
```

Run the Flask application:

```bash
python flask_app.py
```

Keep this Terminal window open. The API runs at:

```text
http://127.0.0.1:5000
```

## View the data

Open this URL in a browser to view all carbon activities:

```text
http://127.0.0.1:5000/activities
```

When the app starts for the first time, it creates the `carbon_activities` table and inserts one sample record if the table is empty.

## Add a new activity

Use this command in a second Terminal window while the Flask app is running:

```bash
curl -X POST http://127.0.0.1:5000/activities \
  -H "Content-Type: application/json" \
  -d '{"activity":"Car travel","category":"Transport","amount":20,"unit":"km","kg_co2e":4.2}'
```

Refresh `/activities` to see the new record.

## Stop the database

When finished, stop the MySQL container with:

```bash
docker compose down
```

The database configuration is MySQL database `homework_db`, username `root`, password `rootpassword`, running on port `3306`.
