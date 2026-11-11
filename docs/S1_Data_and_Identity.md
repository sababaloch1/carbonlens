# S1 – Data & Identity (explained simply)

Owner: Saba Brahmani (Member 1). Works together with S2 (calculations), S3 (analytics) and S4 (AI coach).

## 1. What does S1 do?
S1 is the front door and the filing cabinet of CarbonLens. It handles:
*   **Authentication:** Users log in securely and get a JWT token.
*   **Structure:** Admins set up the company, departments, and facilities.
*   **Data Entry:** Users enter raw activity data (like electricity bills, flights, or meter readings).
*   **Security:** Ensures Company A can never see Company B's data.
*   **Triggering S2:** The moment data is saved, S1 tells the S2 engine to calculate the CO2e.

## 2. Words you need
| Word | Meaning |
|---|---|
| Organization | The company using the app. Everything is tied to an `org_id`. |
| Role | Defines what a user can do: `admin` (full control), `manager` (reports/targets), `contributor` (data entry). |
| Activity Record | One piece of data (e.g., 500 litres of diesel). |
| Meter Reading | Automated data from a physical meter or IoT device. |
| Asset | A physical thing (Facility, Vehicle, or Meter) that gets a unique QR code. |
| JWT | JSON Web Token. A secure digital ID card that expires after 60 minutes. |
| Tenant Isolation | The security rule that stops Company A from seeing Company B's data. |

## 3. How data entry works (step by step)
1. A user logs in and receives a **JWT**. Every request they make includes this token.
2. The user submits data via the Web UI (either a Form, a CSV Upload, or a Meter Reading).
3. FastAPI receives the data and **Pydantic** validates it (e.g., checks if the amount is a number, the unit is valid, and the date makes sense).
4. S1 saves the record to the PostgreSQL database, attaching the user's `org_id` for security.
5. S1 writes an entry to the **AuditLog** (recording who did what).
6. **The Handoff:** S1 calls `engine.calculate(activity_id)` to tell S2 to do the math.

## 4. CSV Imports (Atomicity)
- Users can upload 5,000 rows at once via CSV.
- S1 uses pandas to read the file.
- **All or nothing:** If even ONE row has a typo (e.g., an unknown unit like "bananas"), the entire file is rejected. The user gets a detailed error report (Row 5: unknown unit) and *no* data is saved.
- If all rows are valid, they are bulk-inserted quickly, and S2 is triggered for every row.

## 5. Where is the code?
| Path | What it does |
|---|---|
| `api/app/core/models.py` | The 18 SQLAlchemy database tables (shared by all subsystems). |
| `api/app/core/security.py` | Password hashing (bcrypt) and JWT generation. |
| `api/app/core/deps.py` | Security guards (`get_current_user`, `require_admin`) and Tenant Isolation filters. |
| `api/app/data_identity/routes/auth.py` | Register and Login endpoints. |
| `api/app/data_identity/routes/activities.py` | CRUD for activities, CSV upload, and the S2 handoff. |
| `api/app/data_identity/routes/assets.py` | Assets and Meter Readings endpoints. |
| `api/app/data_identity/routes/users.py` | User invitation and GDPR export/delete. |
| `ui/pages_private/placeholder_data_entry.py` | The Streamlit form for manual data entry. |
| `tests/test_data_identity/` | Unit tests (Tenant Isolation, Auth, Activities, CSV). |

## 6. API Endpoints (all under `/api` or `/auth`)
| Method and path | Who | Purpose |
|---|---|---|
| POST `/auth/register` | anyone | Create a new organization and admin user |
| POST `/auth/login` | anyone | Get a JWT token |
| POST `/users/invite` | admin | Add a manager or contributor to the company |
| POST `/activities/` | any user | Create one manual activity record |
| POST `/activities/import` | any user | Upload a CSV of activities |
| POST `/assets` | admin | Create a physical asset (Facility/Vehicle/Meter) with a QR code |
| POST `/readings` | any user | Submit a meter reading |
| GET `/users/me/export` | any user | GDPR: Download all personal data |
| DELETE `/users/me` | any user | GDPR: Soft-delete the user account |

## 7. CSV Format
Activities template:
`category,amount,unit,period_start,period_end,note`
Example:
`electricity,12000,kWh,2026-01-01,2026-01-31,January bill`

## 8. Security & Tenant Isolation
- **Passwords:** Hashed using bcrypt. The plain text password is never saved or logged.
- **JWT:** Expires after 60 minutes. The token holds the `user_id`, `org_id`, and `role`.
- **Tenant Isolation:** Every single database query includes a `.filter(Model.org_id == current_user.org_id)` check. If a user tries to guess an ID from another company, the system returns a `404 Not Found` (hiding the fact that the record exists at all).
- **Pydantic Validation:** Bad input (e.g., negative amounts) returns a clean `422 Unprocessable Entity` error.

## 9. Testing
We use `pytest` with an in-memory SQLite database for speed.
- **NFR-1.08:** Coverage is above 80% for the backend.
- Key tests include: `test_nfr_1_02_tenant_isolation` (proving Company A can't see Company B) and `test_fr_1_07_csv_validation` (proving bad CSVs are rejected).

## 10. Known limits
- The UI is still missing dedicated screens for inviting users, adding facilities, and GDPR export (the backend APIs for these are fully built and working).
- Data Entry UI is currently named `placeholder_data_entry.py` and will be renamed in a future UI refactor.
- The `__init__.py` files in the folder structure are required for Python packaging and should not be deleted.
