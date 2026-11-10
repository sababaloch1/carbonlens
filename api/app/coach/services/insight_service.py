"""S4 - Footprint insights (FR-4.01 summary, FR-4.02 AI explanation)."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from api.app.core.enums import RecSource
from api.app.core.models import User

from ..config import get_settings
from ..footprint import FootprintService, FootprintSummary
from ..llm import LLMClient, LLMError
from ..prompts import INSIGHTS_SYSTEM, wrap_data
from ..schemas import InsightsResponse

SCOPE_LABEL = {"scope_1": "Scope 1 (direct)", "scope_2": "Scope 2 (purchased energy)", "scope_3": "Scope 3 (value chain)"}


def rule_insights(summary: FootprintSummary) -> list[str]:
    """Deterministic insights, used when AI is off or fails (NFR-4.01)."""
    if not summary.has_data:
        return ["No calculated emissions yet. Add activity records (or import a CSV) and the engine will calculate them."]
    out = []
    top = summary.hotspots[0]
    out.append(
        f"Your largest source is {top['category'].replace('_', ' ')} with {top['t_co2e']:.2f} t CO2e, "
        f"{top['share_pct']:.1f}% of the total {summary.total_t_co2e:.2f} t CO2e in the last 12 months."
    )
    main_scope = max(summary.by_scope, key=summary.by_scope.get)
    share = 100 * summary.by_scope[main_scope] / summary.total_t_co2e
    out.append(f"{SCOPE_LABEL[main_scope]} is the biggest scope with {share:.1f}% of emissions.")
    if summary.yoy_pct_change is not None:
        direction = "up" if summary.yoy_pct_change > 0 else "down"
        out.append(f"Emissions are {direction} {abs(summary.yoy_pct_change):.1f}% compared with the previous 12 months.")
    named = [d for d in summary.by_department if d["department"] != "Unassigned"]
    if named:
        d = named[0]
        out.append(f"{d['department']} is the highest-emitting department ({d['share_pct']:.1f}%).")
    if summary.targets:
        t = summary.targets[0]
        state = "on track" if t["status"] == "on_track" else "off track"
        out.append(
            f"Target ({t['scope']}, -{t['reduction_pct']:.0f}% by {t['target_year']} vs {t['baseline_year']}): "
            f"{t['actual_t']:.2f} t so far in {t['as_of_year']} against {t['expected_now_t']:.2f} t on the planned path, "
            f"so you are {state}."
        )
    dq = summary.data_quality
    if dq.get("records_without_result"):
        out.append(
            f"{dq['records_without_result']} activity records have no emission result yet (for example a missing "
            "factor or country), so the real total is higher than shown."
        )
    return out[:5]


def get_insights(
    db: Session, user: User, llm: LLMClient | None,
    date_from: date | None = None, date_to: date | None = None,
) -> InsightsResponse:
    summary = FootprintService(db).build(user.org_id, date_from, date_to)
    summary_dict = summary.to_dict()
    if not summary.has_data or llm is None:
        return InsightsResponse(
            source=RecSource.rules, insights=rule_insights(summary), summary=summary_dict,
            warning=None if summary.has_data else "No calculated emissions yet.",
        )
    try:
        data, _ = llm.complete_json(INSIGHTS_SYSTEM, wrap_data(summary.to_prompt_context()),
                                    get_settings().max_tokens_insights)
        items = [str(i).strip() for i in data.get("insights", []) if str(i).strip()]
        if not items:
            raise LLMError("No insights in model response")
        return InsightsResponse(source=RecSource.ai, insights=items[:5], summary=summary_dict)
    except LLMError:
        return InsightsResponse(
            source=RecSource.rules, insights=rule_insights(summary), summary=summary_dict,
            warning="AI was unavailable, so rule-based insights are shown.",
        )
