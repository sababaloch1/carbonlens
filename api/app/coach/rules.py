"""
S4 - Rule-based recommendation engine (FR-4.03).

Deterministic recommendations derived from the organisation's emission
hotspots. They work without OpenAI, so the coach always has an answer
(NFR-4.01), and they act as a sanity baseline for the AI suggestions.

Estimated saving = category emissions x typical reduction share of the measure.
The reduction shares are conservative, literature-style planning values,
not guarantees.
"""
from __future__ import annotations

from dataclasses import dataclass

from api.app.core.enums import ActivityCategory as C, Level, Scope

from .footprint import FootprintSummary


@dataclass(frozen=True)
class Rule:
    categories: tuple[C, ...]
    title: str
    description: str
    reduction_share: float  # fraction of the categories' emissions this measure can cut
    cost_level: Level
    effort: Level
    scope: Scope
    min_share_pct: float = 3.0  # only fire if these categories are >= this % of the footprint


RULES: list[Rule] = [
    Rule((C.electricity,), "Switch to a certified renewable electricity tariff",
         "Move all sites to a green electricity contract with guarantees of origin (or a PPA). "
         "This removes most market-based Scope 2 emissions with little operational change.",
         0.90, Level.low, Level.low, Scope.scope_2),
    Rule((C.electricity,), "Upgrade lighting to LED with occupancy sensors",
         "Replace remaining fluorescent/halogen lighting with LED and add presence and daylight sensors "
         "in offices, corridors and storage areas.",
         0.10, Level.medium, Level.low, Scope.scope_2),
    Rule((C.electricity,), "Cut standby and after-hours IT power",
         "Enable automatic shutdown for PCs, screens and printers outside working hours and review "
         "server-room cooling set-points.",
         0.05, Level.low, Level.low, Scope.scope_2),
    Rule((C.natural_gas,), "Replace gas boilers with heat pumps",
         "Plan the replacement of gas heating with air- or ground-source heat pumps at the next boiler "
         "renewal, starting with the largest site.",
         0.60, Level.high, Level.high, Scope.scope_1),
    Rule((C.natural_gas,), "Optimise heating set-points and schedules",
         "Lower set-points by 1 degree C, align heating schedules with occupancy and fix "
         "hydraulic balancing. About 6% saving per degree is typical.",
         0.08, Level.low, Level.low, Scope.scope_1),
    Rule((C.diesel, C.petrol, C.fleet_km), "Transition the company fleet to electric vehicles",
         "Replace combustion vehicles with EVs as leases end, starting with high-mileage urban cars, "
         "and install workplace charging.",
         0.50, Level.high, Level.medium, Scope.scope_1),
    Rule((C.diesel, C.petrol, C.fleet_km), "Eco-driving training and route optimisation",
         "Train drivers in eco-driving and use route planning to cut idle time and empty kilometres.",
         0.08, Level.low, Level.low, Scope.scope_1),
    Rule((C.refrigerant,), "Leak checks and low-GWP refrigerants",
         "Introduce quarterly leak detection on cooling equipment and switch to low-GWP refrigerants "
         "(e.g. R-32, R-290) during maintenance.",
         0.50, Level.medium, Level.medium, Scope.scope_1),
    Rule((C.flight_short_haul,), "Replace short-haul flights with rail",
         "Make rail the default for trips under about 700 km or 6 hours. Most European short-haul "
         "routes have rail alternatives with far lower emissions.",
         0.70, Level.low, Level.low, Scope.scope_3),
    Rule((C.flight_long_haul,), "Video-first travel policy and economy-class flying",
         "Require approval for long-haul trips that could be held virtually, and book economy class, "
         "which has a much smaller footprint per passenger than business class.",
         0.30, Level.low, Level.medium, Scope.scope_3),
    Rule((C.hotel_night,), "Prefer certified green hotels",
         "Add eco-certified hotels to the travel booking tool as preferred options.",
         0.15, Level.low, Level.low, Scope.scope_3),
    Rule((C.employee_commute,), "Hybrid work and sustainable commuting incentives",
         "Offer hybrid-work days, a public transport ticket subsidy (e.g. Deutschlandticket) and "
         "bike-leasing to cut car commuting.",
         0.20, Level.low, Level.medium, Scope.scope_3),
    Rule((C.waste_landfill,), "Divert landfill waste to recycling",
         "Introduce separated waste streams (paper, plastics, organics) at all sites and agree "
         "recycling with the waste contractor.",
         0.50, Level.low, Level.medium, Scope.scope_3),
    Rule((C.water,), "Install water-saving fixtures",
         "Fit flow restrictors and dual-flush toilets and monitor meters for leaks.",
         0.20, Level.low, Level.low, Scope.scope_3),
]


@dataclass
class RuleRecommendation:
    title: str
    description: str
    est_saving_t_co2e: float
    cost_level: Level
    effort: Level
    scope: Scope
    reasoning: str


def generate_rule_recommendations(summary: FootprintSummary, limit: int = 6) -> list[RuleRecommendation]:
    """Return the rules that apply to this footprint, ranked by estimated saving."""
    if not summary.has_data:
        return []
    out: list[RuleRecommendation] = []
    for rule in RULES:
        cat_t = sum(summary.category_t(c) for c in rule.categories)
        share = 100.0 * cat_t / summary.total_t_co2e if summary.total_t_co2e else 0.0
        if cat_t <= 0 or share < rule.min_share_pct:
            continue
        saving = round(cat_t * rule.reduction_share, 2)
        if saving <= 0:
            continue
        cats = ", ".join(c.value.replace("_", " ") for c in rule.categories)
        reasoning = (
            f"{cats.capitalize()} accounts for {cat_t:.2f} t CO2e ({share:.1f}% of your footprint). "
            f"This measure typically cuts about {int(rule.reduction_share * 100)}% of those emissions."
        )
        out.append(RuleRecommendation(
            rule.title, rule.description, saving, rule.cost_level, rule.effort, rule.scope, reasoning,
        ))
    out.sort(key=lambda r: r.est_saving_t_co2e, reverse=True)
    return out[:limit]
