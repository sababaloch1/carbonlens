"""S4 - What-if scenarios (FR-4.07).

Answers questions like "what if we move 50% of short-haul flights to rail?" for the
organisation's own last 12 months of data. The numbers come from S2's
`simulate_change` (same factors and tariffs as real calculations, nothing saved).
A manager can save the result as a recommendation.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.app.core.enums import ActivityCategory as C, AuditAction, Level, RecSource, RecStatus, Scope, Unit
from api.app.core.models import ActivityRecord, Facility, Organization, Recommendation, User
from api.app.data_identity.services import audit_service
from api.app.engine import service as engine

from ..footprint import FootprintService, category_scope, last_12_months
from ..schemas import WhatIfResult

KWH_PER_EV_KM = Decimal("0.18")      # typical electric car / small van consumption
KM_PER_MILE = Decimal("1.609344")


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    source: C
    target: C | None          # None = the activity is reduced, not replaced
    description: str
    cost_level: Level
    effort: Level


SCENARIOS: dict[str, Scenario] = {s.id: s for s in [
    Scenario("reduce_electricity", "Reduce electricity use", C.electricity, None,
             "Efficiency measures (LED, IT shutdown, HVAC tuning) cut electricity use.", Level.medium, Level.low),
    Scenario("reduce_heating", "Reduce gas heating", C.natural_gas, None,
             "Lower set-points, better insulation and heating schedules cut gas use.", Level.medium, Level.medium),
    Scenario("flights_to_rail", "Replace short-haul flights with rail", C.flight_short_haul, C.rail,
             "Short-haul passenger-km are travelled by train instead of plane.", Level.low, Level.low),
    Scenario("reduce_long_haul", "Cut long-haul flights", C.flight_long_haul, None,
             "Video meetings replace part of the long-haul trips.", Level.low, Level.medium),
    Scenario("fleet_to_ev", "Electrify the vehicle fleet", C.fleet_km, C.electricity,
             f"Fleet kilometres are driven by EVs using {KWH_PER_EV_KM} kWh/km of grid electricity.",
             Level.high, Level.medium),
    Scenario("reduce_commute", "Reduce car commuting", C.employee_commute, None,
             "Hybrid work and public-transport incentives cut commuting kilometres.", Level.low, Level.medium),
    Scenario("landfill_to_recycling", "Divert landfill waste to recycling", C.waste_landfill, C.waste_recycled,
             "Waste that went to landfill is separated and recycled instead.", Level.low, Level.medium),
]}


def list_scenarios(db: Session, org_id) -> list[dict]:
    """All scenarios, with `available` = the org has data for it in the last 12 months."""
    present: set = set()
    latest = FootprintService(db).latest_activity_date(org_id)
    if latest is not None:
        start, end = last_12_months(latest)
        present = {
            c for (c,) in db.query(ActivityRecord.category).filter(
                ActivityRecord.org_id == org_id, ActivityRecord.period_start >= start,
                ActivityRecord.period_start <= end,
            ).distinct()
        }
    return [
        {"id": s.id, "title": s.title, "category": s.source.value,
         "replaced_by": s.target.value if s.target else None, "description": s.description,
         "available": s.source in present}
        for s in SCENARIOS.values()
    ]


def _baseline_items(db: Session, org_id, category: C):
    """The org's last-12-month amounts of one category, grouped by unit and country."""
    latest = FootprintService(db).latest_activity_date(org_id)
    if latest is None:
        return [], None
    start, end = last_12_months(latest)
    org_country = db.query(Organization.country_code).filter(Organization.id == org_id).scalar()
    rows = (
        db.query(ActivityRecord.unit, Facility.country_code, func.sum(ActivityRecord.amount))
        .outerjoin(Facility, ActivityRecord.facility_id == Facility.id)
        .filter(ActivityRecord.org_id == org_id, ActivityRecord.category == category,
                ActivityRecord.period_start >= start, ActivityRecord.period_start <= end)
        .group_by(ActivityRecord.unit, Facility.country_code)
        .all()
    )
    items = []
    for unit, fac_country, amount in rows:
        region = (fac_country or org_country or "").upper()
        if not region or not amount:
            continue
        items.append({"category": category.value, "unit": unit.value, "amount": Decimal(amount),
                      "region": region, "year": latest.year})
    return items, latest.year


def _after_items(scenario: Scenario, before: list[dict], share: Decimal) -> list[dict]:
    after = []
    for it in before:
        kept = it["amount"] * (1 - share)
        moved = it["amount"] * share
        if kept > 0:
            after.append({**it, "amount": kept})
        if scenario.target is None or moved <= 0:
            continue
        if scenario.target == C.electricity:  # fleet km -> EV electricity
            km = moved * (KM_PER_MILE if it["unit"] == Unit.miles.value else 1)
            after.append({**it, "category": C.electricity.value, "unit": Unit.kWh.value, "amount": km * KWH_PER_EV_KM})
        else:  # same unit, different category (flights -> rail, landfill -> recycling)
            after.append({**it, "category": scenario.target.value, "amount": moved})
    return after


def run(db: Session, user: User, scenario_id: str, change_pct: float) -> WhatIfResult:
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown scenario '{scenario_id}'")
    before, year = _baseline_items(db, user.org_id, scenario.source)
    if not before:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"No {scenario.source.value.replace('_', ' ')} data in the last 12 months, so this scenario can't be simulated.",
        )
    share = Decimal(str(change_pct)) / Decimal("100")
    result = engine.simulate_change(db, before, _after_items(scenario, before, share))

    errors = result["before"]["errors"] + result["after"]["errors"]
    if result["before"]["total_kg_co2e"] == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "The engine has no emission factor for this data, so it can't be simulated.")
    to_t = lambda kg: round(float(kg) / 1000.0, 3)  # noqa: E731
    # Cost saving only when the engine priced every item on both sides; otherwise it would
    # compare e.g. priced EV electricity with unpriced fleet kilometres.
    priced = all(i["cost_eur"] is not None for side in ("before", "after") for i in result[side]["items"])
    return WhatIfResult(
        scenario_id=scenario.id,
        title=scenario.title,
        change_pct=change_pct,
        year=year,
        before_t_co2e=to_t(result["before"]["total_kg_co2e"]),
        after_t_co2e=to_t(result["after"]["total_kg_co2e"]),
        saving_t_co2e=to_t(result["saving_kg_co2e"]),
        saving_pct=round(float(result["saving_pct"]), 1) if result["saving_pct"] is not None else None,
        saving_cost_eur=round(float(result["saving_cost_eur"]), 2) if priced else None,
        assumptions=scenario.description,
        engine_errors=errors,
    )


def save_as_recommendation(db: Session, user: User, res: WhatIfResult) -> Recommendation:
    scenario = SCENARIOS[res.scenario_id]
    title = f"{scenario.title} ({res.change_pct:g}%)"[:160]
    existing = db.query(Recommendation).filter(
        Recommendation.org_id == user.org_id, func.lower(Recommendation.title) == title.lower()
    ).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "This scenario is already saved as a recommendation")
    cost = f" and about EUR {res.saving_cost_eur:,.0f} per year" if (res.saving_cost_eur or 0) > 0 else ""
    rec = Recommendation(
        org_id=user.org_id, title=title,
        description=(f"{scenario.description}\n\nWhy: simulated with the emission engine on your last 12 months of "
                     f"data, this saves {res.saving_t_co2e:.2f} t CO2e ({res.saving_pct or 0:.1f}% of this "
                     f"category){cost}."),
        est_saving_t_co2e=res.saving_t_co2e, cost_level=scenario.cost_level, effort=scenario.effort,
        scope=Scope(category_scope(scenario.source.value)), status=RecStatus.proposed, source=RecSource.rules,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    audit_service.log_action(db, user.org_id, user.id, "Recommendation", rec.id, AuditAction.create,
                             {"source": "what_if", "scenario": res.scenario_id, "change_pct": res.change_pct})
    return rec
