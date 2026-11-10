# S4 – AI Sustainability Coach (explained simply)

Owner: Mustafa Mulla Khil (Member 4). Works together with S1 (data and login), S2 (emission engine) and S3 (analytics).

## 1. What does S4 do?
S1 collects the data, S2 turns it into CO2, S3 shows it on the dashboard. **S4 says what to do about it.**

- It **explains** the footprint: what the biggest sources are and why emissions went up or down.
- It **recommends** concrete reduction measures with an estimated saving, cost and effort.
- It **simulates** "what if?" changes (for example 50% of short-haul flights moved to rail) with S2's engine.
- It **answers questions** in a chat, based on the company's own numbers.
- It **writes learning content** for employees, which a manager approves before others can read it.

S4 uses OpenAI. If there is no API key, or OpenAI is down, S4 still works with built-in rules.

## 2. Words you need
| Word | Meaning |
|---|---|
| Footprint summary | The company's numbers for the last 12 months with data: total, by scope, category, department, facility, monthly trend and targets. Built from S3. |
| Hotspot | One of the biggest emission categories. Recommendations start there. |
| Recommendation | One reduction measure: title, description, "why", estimated saving (t CO2e per year), cost, effort, scope, status. |
| Source `ai` / `rules` | Who proposed it: OpenAI, or the built-in rules / a what-if simulation. |
| Status | `proposed` → `accepted` or `dismissed`; `accepted` → `completed` or `dismissed`; `dismissed` → `proposed`. |
| What-if | A simulated change. S2 calculates it; nothing is saved unless a manager saves it as a recommendation. |
| Fallback | The rule-based answer used when AI isn't available. |

## 3. How it works (step by step)
1. **Summary.** S4 calls S3's functions (`calculate_summary`, `calculate_breakdown`, `calculate_trend`, `calculate_top_sources`, `calculate_targets_status`) for the last 12 months with data. So the coach always quotes **the same numbers as the dashboard**. S4 never calculates emissions itself.
2. **Privacy filter.** Only totals and shares are sent to OpenAI. No names, emails, company name, notes or invoice references.
3. **Recommendations.** In `auto` mode S4 asks OpenAI for up to 5 measures as JSON. Every answer is checked (valid fields, scope, levels). A saving bigger than the category's emissions is cut down to that size. If OpenAI fails, the rule engine is used instead. Titles already on the list are skipped. The new measures are saved as `proposed` and written to the audit log.
4. **What-if.** S4 takes the company's amounts for one category (last 12 months) and builds a "before" and an "after" list. It sends both to S2's `simulate_change`, which uses the real factors and tariffs. If some items have no tariff, no cost saving is shown (no made-up money).
5. **Chat.** Each question is answered with the footprint summary, the open recommendations and the last 10 messages. Messages are saved with their token counts.
6. **Learning.** OpenAI writes a 250–400 word article for a role (admin, manager, contributor). It is saved as `draft`; a manager approves it, then contributors can read it.

## 4. Where is the code?
| Path | What it does |
|---|---|
| `api/app/coach/footprint.py` | Builds the footprint summary from S3 (FR-4.01). |
| `api/app/coach/rules.py` | Rule engine: 14 measures, each tied to emission categories. |
| `api/app/coach/llm.py` | The only place that talks to OpenAI (`LLMClient`, `OpenAIClient`, `get_llm`). |
| `api/app/coach/prompts.py` | Prompt templates. Company data goes inside `<data>` tags. |
| `api/app/coach/schemas.py` | API data shapes and the check for AI answers. |
| `api/app/coach/services/` | `insight_service`, `recommendation_service`, `whatif_service`, `chat_service`, `learning_service`. |
| `api/app/coach/routes/` | API endpoints (below). |
| `api/app/coach/config.py`, `deps.py` | Settings from environment variables; manager/admin role check. |
| `ui/pages_private/coach.py` | Streamlit page "🤖 Coach" with 5 tabs. |
| `tests/test_coach/` | 42 tests (95% coverage of `api/app/coach`). |

S4 uses the S4 tables that were already in the shared schema (`recommendations`, `chat_sessions`, `chat_messages`, `learning_contents`). **No migration is needed.**

## 5. API endpoints (all under `/coach`)
| Method and path | Who | Purpose |
|---|---|---|
| GET `/summary` | any user | Footprint summary used by the coach |
| GET `/insights` | any user | 3–5 explanations (AI, or rules as fallback) |
| GET `/usage` | any user | AI on/off, model, chat tokens used by the organisation |
| POST `/recommendations/generate` | manager, admin | `{"mode": "auto" \| "ai" \| "rules"}` |
| GET `/recommendations` | any user | Filters: `status`, `scope`, `department_id`, `source` |
| GET `/recommendations/{id}` | any user | One recommendation |
| PATCH `/recommendations/{id}/status` | manager, admin | Change status (invalid changes → 409) |
| GET `/what-if/scenarios` | any user | Scenarios, with `available` = company has data for it |
| POST `/what-if` | any user (save: manager, admin) | `{"scenario_id", "change_pct", "save"}` |
| POST / GET `/chat/sessions` | any user | Own conversations only |
| GET / POST `/chat/sessions/{id}/messages` | owner | Read history / ask a question |
| DELETE `/chat/sessions/{id}` | owner | Delete a conversation |
| POST `/learning/generate` | manager, admin | `{"topic", "audience"}` → draft |
| GET `/learning`, `/learning/{id}` | any user | Contributors only see approved content |
| POST `/learning/{id}/approve`, DELETE `/learning/{id}` | manager, admin | Approve / delete |

## 6. Requirements

### Functional
| ID | Requirement | Tests |
|---|---|---|
| FR-4.01 | Footprint summary for the last 12 months with data: total, scopes, categories, departments, facilities, top sources, monthly trend, year-on-year change, S3 target status, data quality. Same numbers as S3. | `test_summary_*` |
| FR-4.02 | AI insights: 3–5 short explanations of what drives the footprint, quoting the numbers. | `test_insights_*` |
| FR-4.03 | Rule-based recommendations from the hotspots, with saving, cost, effort and scope. | `test_rules_*`, `test_generate_rules_mode` |
| FR-4.04 | AI recommendations tailored to the company's data, departments and targets, each with a "why". | `test_generate_ai_validates_and_caps_output` |
| FR-4.05 | No duplicate recommendations; list ranked by saving; filter by status, scope, department, source. | `test_generate_twice_skips_duplicates`, `test_list_and_filter` |
| FR-4.06 | Recommendation status workflow with allowed transitions only. | `test_status_lifecycle_and_audit` |
| FR-4.07 | What-if scenarios calculated with S2's engine; can be saved as a recommendation. | `test_fr_4_07_whatif.py` |
| FR-4.08 | Chat assistant grounded in the company's data; conversations saved, listed, deleted. | `test_chat_conversation_is_grounded_and_persisted` |
| FR-4.09 | AI learning content for a topic and role, saved as a draft. | `test_learning_*` |
| FR-4.10 | Approval workflow: managers approve; contributors only see approved content. | `test_learning_generate_approve_and_visibility` |

### Non-functional
| ID | Requirement | Tests |
|---|---|---|
| NFR-4.01 | Graceful degradation: no API key or an OpenAI error never breaks the app (rules / summary fallback; clear 503 for learning). | `test_auto_mode_falls_back_*`, `test_chat_degrades_*`, `test_insights_fall_back_*`, `test_ai_returning_garbage_falls_back` |
| NFR-4.02 | Privacy: only aggregated numbers go to OpenAI. | `test_prompts_contain_no_personal_data` |
| NFR-4.03 | Tenant isolation: own organisation only; chats private to their owner. | `test_other_org_cannot_access_*`, `test_whatif_is_tenant_isolated` |
| NFR-4.04 | Role-based access for generating, status changes, saving what-ifs and approving content. | `test_contributor_cannot_*`, `test_save_as_recommendation_requires_manager`, `test_requires_authentication` |
| NFR-4.05 | Every AI answer is validated; implausible savings are capped. | `test_generate_ai_validates_and_caps_output` |
| NFR-4.06 | Cost control: small default model, token limits, 10-message chat history, token usage stored and shown. | `test_usage_counts_tokens` |
| NFR-4.07 | OpenAI timeout 30 s with 2 retries (configurable). | `test_sdk_errors_become_llm_error` |
| NFR-4.08 | Testable without the network: OpenAI behind one interface, faked in tests. | all of `tests/test_coach` |
| NFR-4.09 | Input safety: chat messages max 2,000 characters; data in `<data>` tags treated as data. | `test_chat_message_length_limit` |
| NFR-4.10 | Auditability: new recommendations and every status change go to S1's audit log. | `test_status_lifecycle_and_audit` |

## 7. How to run
1. Put `OPENAI_API_KEY=sk-...` in the root `.env` (same file as `JWT_SECRET`). Optional: `OPENAI_MODEL` (default `gpt-4o-mini`). Without a key the coach uses the rules.
2. `docker compose up --build`, log in with the demo account, open **🤖 Coach**.
3. Tests: `pytest tests/test_coach --cov=api.app.coach`.

Optional settings (environment variables): `COACH_OPENAI_TIMEOUT` (30), `COACH_OPENAI_RETRIES` (2), `COACH_MAX_TOKENS_RECS` (1200), `COACH_MAX_TOKENS_CHAT` (600), `COACH_CHAT_HISTORY_WINDOW` (10), `COACH_MAX_CHAT_CHARS` (2000), `COACH_MAX_AI_RECS` (5).

## 8. Known limits
- Rule savings are planning estimates (category emissions × a typical reduction share), not guarantees. What-if numbers come from S2 and are exact for the given assumptions.
- The EV scenario assumes 0.18 kWh per km. Fuel cost isn't priced for fleet kilometres, so its cost saving shows "n/a".
- `learning_contents` has no `org_id` in the shared schema, so learning content is one library for all organisations. It contains no company data.
- Target status is S3's verdict for the current year to date.
