"""
S4 - Footprint context builder (FR-4.01).

The coach does not calculate emissions itself. It reuses:
  * S3 analytics (summary, breakdown, trend, top sources, target status), so every
    number the coach quotes is exactly the number the dashboard shows;
  * S2 emission results underneath them (current, location-based).

The result is one aggregated summary. It is the ONLY company data the coach sends
to OpenAI (NFR-4.02): totals and shares, never names, emails, notes or evidence.

Period: the last 12 months that have data (ending at the latest activity month),
so estimated savings are yearly figures.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.app.analytics.breakdown import calculate_breakdown
from api.app.analytics.sources import calculate_top_sources
from api.app.analytics.summary import calculate_summary
from api.app.analytics.targets import calculate_targets_status
from api.app.analytics.trend import calculate_trend
from api.app.core.enums import ActivityCategory, Scope
from api.app.core.models import ActivityRecord, Organization

# GHG Protocol scope of each activity category (same as S2's factor table).
CATEGORY_SCOPE: dict[str, str] = {
    ActivityCategory.electricity.value: Scope.scope_2.value,
    ActivityCategory.natural_gas.value: Scope.scope_1.value,
    ActivityCategory.diesel.value: Scope.scope_1.value,
    ActivityCategory.petrol.value: Scope.scope_1.value,
    ActivityCategory.fleet_km.value: Scope.scope_1.value,
    ActivityCategory.refrigerant.value: Scope.scope_1.value,
}


def category_scope(category: str) -> str:
    return CATEGORY_SCOPE.get(category, Scope.scope_3.value)


def last_12_months(latest: date) -> tuple[date, date]:
    """First day 11 months before `latest`'s month, and the last day of `latest`'s month."""
    y, m = latest.year, latest.month - 11
    while m <= 0:
        m += 12
        y -= 1
    end = date(latest.year, latest.month, calendar.monthrange(latest.year, latest.month)[1])
    return date(y, m, 1), end


@dataclass
class FootprintSummary:
    industry: str | None
    country_code: str | None
    employee_count: int | None
    period_from: date | None
    period_to: date | None
    total_t_co2e: float
    by_scope: dict[str, float]
    by_category: list[dict]
    by_department: list[dict]
    by_facility: list[dict]
    top_sources: list[dict]
    monthly: list[dict]
    yoy_pct_change: float | None
    targets: list[dict]
    data_quality: dict
    total_cost_eur: float | None = None
    org_name: str = field(default="", repr=False)

    @property
    def hotspots(self) -> list[dict]:
        return self.by_category[:3]

    @property
    def has_data(self) -> bool:
        return self.total_t_co2e > 0

    def category_t(self, category: ActivityCategory | str) -> float:
        key = category.value if isinstance(category, ActivityCategory) else category
        for row in self.by_category:
            if row["category"] == key:
                return row["t_co2e"]
        return 0.0

    def to_dict(self) -> dict:
        return {
            "organization": {
                "name": self.org_name,
                "industry": self.industry,
                "country_code": self.country_code,
                "employee_count": self.employee_count,
            },
            "period_from": self.period_from.isoformat() if self.period_from else None,
            "period_to": self.period_to.isoformat() if self.period_to else None,
            "total_t_co2e": self.total_t_co2e,
            "total_cost_eur": self.total_cost_eur,
            "by_scope": self.by_scope,
            "by_category": self.by_category,
            "by_department": self.by_department,
            "by_facility": self.by_facility,
            "top_sources": self.top_sources,
            "hotspots": self.hotspots,
            "monthly": self.monthly,
            "yoy_pct_change": self.yoy_pct_change,
            "targets": self.targets,
            "data_quality": self.data_quality,
        }

    def to_prompt_context(self) -> dict:
        """Privacy-safe view for the LLM (NFR-4.02): aggregates only, no company name."""
        d = self.to_dict()
        d["organization"].pop("name", None)
        return d


def _share(t: float, total: float) -> float:
    return round(100.0 * t / total, 1) if total else 0.0


class FootprintService:
    def __init__(self, db: Session):
        self.db = db

    def latest_activity_date(self, org_id: UUID) -> date | None:
        return (
            self.db.query(func.max(ActivityRecord.period_start))
            .filter(ActivityRecord.org_id == org_id)
            .scalar()
        )

    def build(self, org_id: UUID, date_from: date | None = None, date_to: date | None = None) -> FootprintSummary:
        org = self.db.query(Organization).filter(Organization.id == org_id).first()
        latest = self.latest_activity_date(org_id)
        if date_from is None and date_to is None and latest is not None:
            date_from, date_to = last_12_months(latest)

        s = calculate_summary(self.db, org_id, start=date_from, end=date_to)
        total = s["total_t_co2e"]

        by_category = [
            {"category": r["label"], "scope": category_scope(r["label"]),
             "t_co2e": round(r["t_co2e"], 3), "share_pct": _share(r["t_co2e"], total)}
            for r in calculate_breakdown(self.db, org_id, by="category", start=date_from, end=date_to)
        ]
        by_department = [
            {"department": r["label"], "t_co2e": round(r["t_co2e"], 3), "share_pct": _share(r["t_co2e"], total)}
            for r in calculate_breakdown(self.db, org_id, by="department", start=date_from, end=date_to)
        ]
        by_facility = [
            {"facility": r["label"], "t_co2e": round(r["t_co2e"], 3), "share_pct": _share(r["t_co2e"], total)}
            for r in calculate_breakdown(self.db, org_id, by="facility", start=date_from, end=date_to)
        ]
        top_sources = [
            {"category": r["category"], "facility": r["facility"], "t_co2e": round(r["t_co2e"], 3)}
            for r in calculate_top_sources(self.db, org_id, limit=5, start=date_from, end=date_to)
        ]

        monthly, yoy = [], None
        if latest is not None:
            trend = calculate_trend(self.db, org_id, anchor_date=date_to or latest)
            monthly = [{"month": m["month"], "t_co2e": round(m["t_co2e"], 3)} for m in trend["months"]]
            yoy = trend["pct_change"]

        targets = []
        if latest is not None:
            for t in calculate_targets_status(self.db, org_id, as_of_year=latest.year):
                targets.append({
                    "scope": t["scope"] or "all",
                    "baseline_year": t["baseline_year"],
                    "target_year": t["target_year"],
                    "reduction_pct": t["reduction_pct"],
                    "baseline_t": t["baseline_t"],
                    "target_t": t["target_t"],
                    "as_of_year": latest.year,
                    "expected_now_t": t["expected_now"],
                    "actual_t": t["actual_t"],
                    "status": t["status"],  # S3's verdict: on_track / off_track
                })

        return FootprintSummary(
            industry=org.industry if org else None,
            country_code=org.country_code if org else None,
            employee_count=org.employee_count if org else None,
            period_from=date_from,
            period_to=date_to,
            total_t_co2e=round(total, 3),
            by_scope={k: round(v, 3) for k, v in s["by_scope"].items()},
            by_category=by_category,
            by_department=by_department,
            by_facility=by_facility,
            top_sources=top_sources,
            monthly=monthly,
            yoy_pct_change=yoy,
            targets=targets,
            data_quality={
                "records_without_result": s["failed_records"],
                "cost_complete": s["cost_complete"],
            },
            total_cost_eur=s["total_cost_eur"],
            org_name=org.name if org else "",
        )
