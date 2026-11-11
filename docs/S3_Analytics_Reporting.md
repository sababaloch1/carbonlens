# S3 – Analytics and Reporting

Owner: Sameer (Member 3). Works together with S1 (data and identity), S2 (emission engine) and S4 (AI sustainability coach).

## 1. What does S3 do?

S3 reads the current emission results created by S2 and turns them into information that people can use:

- Emissions dashboard summaries and KPIs
- Twelve-month trends and year-over-year comparison
- Breakdowns by scope, category, department and facility
- Top emission sources and activity records
- Sustainability score
- Decarbonization targets and progress
- CSV and PDF reports
- Live facility meter monitoring
- Monthly anomaly detection

S3 does not calculate emissions itself and does not write to `emission_results`. S2 owns the calculation; S3 aggregates and presents the results.

## 2. Shared S3 rules

Every analytics query follows these rules:

1. Filter data by the authenticated user's `org_id` for tenant isolation.
2. Read only current results (`is_current = true`).
3. Ignore results whose `kg_co2e` is null.
4. Include location-based Scope 2 results and results with no method; do not add market-based and location-based results together.
5. Aggregate totals in SQL with `sum()` and `group_by()` rather than Python loops.
6. Convert kilograms to tonnes by dividing by 1,000.
7. Return empty or clearly marked results when an organization has no data.

The common query builder is in `api/app/analytics/base.py`. Summary, trend, breakdown and top-source calculations use a five-minute in-memory cache keyed by organization and arguments (`api/app/analytics/cache.py`).

## 3. How the data flows

1. S1 stores activities and meter readings for an organization.
2. S2 selects factors and tariffs, calculates emissions and costs, and stores `EmissionResult` rows.
3. S3 receives the authenticated user's organization from the JWT/dependency layer.
4. S3 runs SQL aggregation over current results and related activity, facility, department or meter tables.
5. FastAPI returns JSON or a CSV/PDF response.
6. Streamlit calls the API and renders KPIs, tables, charts and downloads.
7. S4 reuses S3 calculation functions so the coach and dashboard show the same numbers.

## 4. Features and implementation

| Feature | API implementation | UI | Tests |
|---|---|---|---|
| Summary | `summary.py`, `GET /analytics/summary` | `ui/pages_private/dashboard.py` | `tests/test_analytics/test_summary.py` |
| Trend and YoY | `trend.py`, `GET /analytics/trend` | `ui/pages_private/dashboard.py` | `tests/test_analytics/test_trend.py` |
| Breakdowns | `breakdown.py`, `GET /analytics/breakdown` | `ui/pages_private/dashboard.py` | `tests/test_analytics/test_breakdown.py` |
| Top sources | `sources.py`, `GET /analytics/top-sources` | `ui/pages_private/dashboard.py` | `tests/test_analytics/test_sources.py` |
| Sustainability score | `score.py`, `GET /analytics/score` | `ui/pages_private/score.py` | `tests/test_analytics/test_score.py` |
| Targets | `targets.py`, `/analytics/targets*` | `ui/pages_private/targets.py` | `tests/test_analytics/test_targets.py` |
| Reports | `reports.py`, `/analytics/report.csv` and `/analytics/report.pdf` | `ui/pages_private/reports.py` | `tests/test_analytics/test_reports.py` |
| Live monitor | `live.py`, `GET /analytics/live` | `ui/pages_private/live_monitor.py` | `tests/test_analytics/test_live.py` |
| Anomalies | `anomaly.py`, `GET /analytics/anomalies` | dashboard warnings | `tests/test_analytics/test_anomaly.py` |

All subrouters are registered by `api/app/analytics/routes.py`, under the `/analytics` prefix.

## 5. Feature details

### Summary

`calculate_summary()` returns total tonnes, total cost, totals by scope, calculation counts, failed calculations and data-quality information. Optional start and end dates filter the organization's activity period.

### Trend

`calculate_trend()` builds the latest twelve months, groups results with SQL year/month extraction, fills missing months with zero, and calculates year-over-year change where enough history exists.

### Breakdowns and sources

`calculate_breakdown()` groups by scope, activity category, department or facility. Missing department/facility names are shown as `Unassigned`. `calculate_top_sources()` groups activity categories and facilities, orders by total emissions, and limits the result.

### Sustainability score

`calculate_sustainability_score()` combines four dimensions worth 25 points each:

- Year-over-year trend
- Target trajectory progress
- Data completeness
- Carbon intensity per employee

The score is persisted with its component details for transparency.

### Targets

Managers and admins can create targets. S3 calculates a linear reduction trajectory from the baseline year to the target year and compares actual year-to-date emissions with the expected path. Contributors can view but not create targets.

### Reports

CSV and PDF reports reuse S3 summary, breakdown, top-source and anomaly calculations. This avoids having a second, inconsistent reporting calculation path.

### Live monitor

`calculate_live_emissions()` joins today's meter readings to assets, facilities and current emission results. It groups today's tonnes by facility, includes unassigned assets, applies organization isolation, and returns an UTC `as_of` timestamp. The UI can refresh automatically every 60 seconds.

### Anomalies

S3 aggregates monthly totals and flags unusually high or low months against the historical average. The implementation requires enough history before producing a meaningful anomaly result.

## 6. Important data ownership issue

Standard `EmissionFactor` and `RegionTariff` rows currently have no `org_id`. The Factors & Tariffs page therefore displays shared reference data to every organization, and factor/tariff changes can affect calculations across organizations.

This is acceptable only if factors and tariffs are intentionally global reference data. If each organization must manage its own values, add `org_id`, apply organization filters to reads and writes, and include organization ownership in versioning and imports.

Facility green tariffs are different: they belong to a facility and are therefore organization-specific through the facility relationship.

## 7. Where is the code?

| Path | Responsibility |
|---|---|
| `api/app/analytics/routes.py` | Registers all S3 routers under `/analytics` |
| `api/app/analytics/base.py` | Shared tenant and current-result query rules |
| `api/app/analytics/cache.py` | Five-minute analytics cache and index recommendations |
| `api/app/analytics/summary.py` | Summary KPIs and data quality |
| `api/app/analytics/trend.py` | Twelve-month trend and YoY comparison |
| `api/app/analytics/breakdown.py` | Scope/category/department/facility grouping |
| `api/app/analytics/sources.py` | Top sources and detailed records |
| `api/app/analytics/score.py` | Sustainability score |
| `api/app/analytics/targets.py` | Target creation and progress status |
| `api/app/analytics/reports.py` | CSV and PDF exports |
| `api/app/analytics/live.py` | Today's facility meter emissions |
| `api/app/analytics/anomaly.py` | Monthly anomaly detection |
| `ui/pages_private/` | Streamlit dashboard pages |
| `tests/test_analytics/` | S3 unit and integration tests |

## 8. Verification

The complete project test suite passes with **173 tests passed**. The live PostgreSQL deployment was also smoke-tested: admin login, `/analytics/live`, API health, database health and the Streamlit UI all responded successfully.

The suite currently emits deprecation warnings for older `datetime.utcnow()` calls; these do not cause test failures.

## 9. How to run

1. Set `JWT_SECRET` in the root `.env` file.
2. Run `docker compose up --build`.
3. Open the UI at `http://localhost:8501` or API docs at `http://localhost:8000/docs`.
4. Run tests with `pytest`.

