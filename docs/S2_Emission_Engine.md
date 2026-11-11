# S2 – Emission Engine and DevOps (explained simply)

Owner: Tuba Jabeen (Member 2). Works together with S1 (data and login), S3 (analytics) and S4 (AI coach).

## 1. What does S2 do?
S2 turns **activities** (for example "12,000 kWh of electricity") into **CO2 emissions** (kg CO2e) and **cost** (EUR).

    emissions (kg CO2e) = amount x emission factor
    cost (EUR)          = amount x tariff

Example: 12,000 kWh x 0.363 kg/kWh = **4,356 kg CO2e**. This is our reference test.

S2 also runs the project: Docker (one command starts everything) and GitHub Actions (tests run automatically).

## 2. Words you need
| Word | Meaning |
|---|---|
| Activity | One thing a company did, e.g. used 200 m3 gas. Saved by S1. |
| Emission factor | How many kg CO2e one unit causes (kg per kWh, per litre, ...). Comes from an official source. |
| Tariff | What one unit costs in EUR. |
| Scope 1 / 2 / 3 | 1 = own fuel burning, 2 = bought electricity, 3 = everything else (travel, waste, water). |
| Region | Country code (DE) or GLOBAL (fallback for everyone). |
| Version | When a factor changes, a new version is created. The old one is kept. |
| Trace | A short record showing exactly how a result was calculated. |

## 3. How a calculation works (step by step)
1. S1 saves an activity and calls S2 (`safe_calculate_activity`).
2. S2 **converts the unit** if needed (MWh -> kWh, tonne -> kg, m3 -> litre). Only inside the same type of unit (miles to km uses 1 mile = 1.609344 km). km and passenger_km are NOT interchangeable.
3. S2 **picks a factor**: same country and year, else the nearest year in that country, else GLOBAL. Only active factors are used.
4. S2 multiplies: amount x factor. All numbers use `Decimal`, never `float`, so there are no rounding surprises.
5. S2 picks a tariff the same way and computes the cost.
6. S2 stores the result with its trace. If a factor is missing or the unit does not fit, it stores an **error message on the record** and leaves the number empty. It never stores 0.

## 4. Changing factors safely
- A changed factor creates **version + 1**; the old version is deactivated, never deleted (no hard deletes).
- After a change, S2 **recalculates** affected activities. The old results are kept as history (`is_current = False`), the new ones become current.
- `simulate` answers "what if?" and **saves nothing**.

## 5. Where is the code?
| Path | What it does |
|---|---|
| `api/app/engine/core/` | Pure calculation: `units.py` (conversion), `selector.py` (factor/tariff choice), `calculator.py` (the maths), `errors.py`, `types.py`. No database here, so it is easy to test. |
| `api/app/engine/repository.py` | Reads and writes factors, tariffs and results in the database. |
| `api/app/engine/service.py` | Connects everything: calculate, recalculate, simulate. |
| `api/app/engine/importer.py` | Imports factor and tariff CSV files (all or nothing; error per row). |
| `api/app/engine/routes.py` | The API endpoints (below). |
| `api/app/engine/schemas.py` | Shapes of the data going in and out of the API. |
| `seed/` | `factors.csv`, `tariffs.csv`, `run_seed.py` (demo company and starting data). |
| `ui/pages/2_Factors_and_Tariffs.py` | Streamlit page: lists, CSV upload, simulate. |
| `docker-compose.yml`, `api/Dockerfile`, `ui/Dockerfile` | The Docker stack. |
| `.github/workflows/ci.yml` | Automatic tests on every push. |
| `alembic/versions/b7c1d2e3f4a5_...` | Migration: adds the `miles` unit and the green-tariff table. |
| `tests/test_engine/` | 70 tests (calculation core, service, import, API, green tariff). |

## 6. API endpoints (all under `/engine`)
| Method and path | Who | Purpose |
|---|---|---|
| GET `/factors`, GET `/tariffs` | any user | List (filters: type, region, year) |
| POST `/factors`, POST `/tariffs` | admin | Add or update one (creates a new version if it exists) |
| DELETE `/factors/{id}` | admin | Deactivate (soft delete) |
| POST `/factors/import`, `/tariffs/import` | admin | Upload CSV |
| POST `/calculate/{activity_id}` | user | Calculate one activity |
| GET `/results/{activity_id}` | user | Results (`include_history=true` for old ones) |
| POST `/simulate` | user | What-if for a list of items |
| POST `/simulate/compare` | user | Before/after, gives the saving |
| GET / PUT / DELETE `/facilities/{id}/green-tariff` | GET any user, PUT/DELETE admin | A facility's green-tariff factor (market-based Scope 2) |

## 7. CSV formats
Factors: `activity_type,region,year,unit,kg_co2e_per_unit,scope,ghg_category,source`
Tariffs: `activity_type,region,year,unit,eur_per_unit,source`
`source` is required: every number must name where it came from. If one row is wrong the whole file is rejected and the errors are listed.

## 8. Data sources
- Factors: DESNZ (UK government) GHG Conversion Factors 2026, stored as GLOBAL. Electricity: Umweltbundesamt 2024 (0.363 kg/kWh, DE). Each `source` names the sheet and cell.
- Tariffs: electricity BDEW Strompreisanalyse April 2026; diesel and petrol ADAC 21.10.2026. Natural gas and water tariffs are not included (no suitable source yet).

## 9. How to run
1. Copy `.env.example` to `.env` in the project root (next to `docker-compose.yml`) and set `JWT_SECRET`. Never commit `.env`. The other values have working defaults; `OPENAI_API_KEY` is only needed for the AI coach.
2. `docker compose up --build`. The API container runs the migrations and the seed by itself.
3. API docs: http://localhost:8000/docs. UI: http://localhost:8501. Database port on your PC: 5433.
4. Log in with the demo account: `user2acc@carbonlens.local` / `user2account`. The seed also loads about 240 demo activities.
5. Optional database viewer: `docker compose --profile tools up` then http://localhost:8080 (System: PostgreSQL, Server: `db`).
6. Fresh start (deletes data; needed after changing the database password): `docker compose down -v`.
7. Tests: `pytest` (Python 3.12 recommended). The app needs `JWT_SECRET` in the environment; CI sets a test value.

## 10. Market-based Scope 2 (green tariff)
- Location-based (grid factor) is always calculated for electricity.
- If the facility has a green-tariff factor (kg CO2e per kWh from the supplier, with a source), a **second result** with `method = market_based` is stored. Cost stays only on the location-based result.
- The location-based result is the main one. Anyone summing results (S3) must not add both: filter on `method`.
- Changing or removing the green tariff recalculates that facility's electricity and keeps the old results as history.

## 11. Known limits
- New activity types (NFR-2.07) are only partly data-driven: a new type needs one list entry, one migration and one factor row.
- Natural gas and water have no tariff yet, so those records get emissions but no cost.
- DESNZ factors are UK-based; they are a fallback, not German values.
- The Streamlit page has its own login box until S3's shell shares its token.

## 12. Requirements of S2
### Functional
| ID | Requirement |
|---|---|
| FR-2.01 | Store and list emission factors (filter by type, region, year). |
| FR-2.02 | Import factors and tariffs from CSV; all rows are saved or none, with an error per row. |
| FR-2.03 | Convert units inside the same unit family (MWh to kWh, tonne to kg, m3 to litre, miles to km). |
| FR-2.04 | Give every result a scope (1, 2 or 3) and a GHG category. |
| FR-2.05 | Calculate and save kg CO2e and cost (EUR) for an activity. |
| FR-2.06 | Choose the factor by country and year, else nearest year, else GLOBAL. |
| FR-2.07 | Calculate market-based Scope 2 from a facility's green-tariff factor next to the location-based result. |
| FR-2.08 | Recalculate affected activities after a factor or tariff change and keep old results as history. |
| FR-2.09 | Store a trace (factor, unit conversion, formula) with every result. |
| FR-2.10 | Simulate what-if scenarios and compare before and after without saving anything. |

### Non-functional
| ID | Requirement |
|---|---|
| NFR-2.01 | Deterministic: the same input always gives the same result. |
| NFR-2.02 | Exact arithmetic with `Decimal`, no `float`; rounding only for display. |
| NFR-2.03 | The calculation core has no web or database imports, so it is testable alone. |
| NFR-2.04 | Bulk recalculation loads factors and tariffs once per category. |
| NFR-2.05 | Every factor and tariff names its source (and year). |
| NFR-2.06 | The reference example (12,000 kWh x 0.363 = 4,356 kg CO2e) is covered by an automated test. |
| NFR-2.07 | New activity types can be added with little change (see known limits). |
| NFR-2.08 | Versioning: old factors, tariffs and results are kept; no hard deletes. |
| NFR-2.09 | Reproducible deployment: one `docker compose up` starts everything and CI runs the tests on every push. |
| NFR-2.10 | Calculation problems are stored as an error message on the record and never as 0. |
