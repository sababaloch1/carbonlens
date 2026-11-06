"""Homework 1 OOP classes for S3: Analytics and Reporting."""

from datetime import date
from typing import Dict, Iterable, List, Optional


class EmissionsSummary:
    """Encapsulates a period summary of an organisation's emissions."""

    def __init__(self, period_start: Optional[date] = None,
                 period_end: Optional[date] = None,
                 total_t_co2e: float = 0.0,
                 by_scope: Optional[Dict[str, float]] = None,
                 failed_records: int = 0,
                 total_cost_eur: float = 0.0):
        self._period_start = period_start
        self._period_end = period_end
        self.total_t_co2e = total_t_co2e
        self._by_scope = dict(by_scope or {"scope_1": 0.0, "scope_2": 0.0, "scope_3": 0.0})
        self.failed_records = failed_records
        self.total_cost_eur = total_cost_eur

    def initialize(self, period_start: date, period_end: date) -> None:
        if period_end < period_start:
            raise ValueError("period_end must not be before period_start")
        self._period_start, self._period_end = period_start, period_end

    @property
    def period_start(self): return self._period_start
    @period_start.setter
    def period_start(self, value): self._period_start = value

    @property
    def period_end(self): return self._period_end
    @period_end.setter
    def period_end(self, value): self._period_end = value

    @property
    def total_t_co2e(self): return self._total_t_co2e
    @total_t_co2e.setter
    def total_t_co2e(self, value):
        if float(value) < 0: raise ValueError("total emissions cannot be negative")
        self._total_t_co2e = float(value)

    @property
    def by_scope(self): return dict(self._by_scope)
    @by_scope.setter
    def by_scope(self, value): self._by_scope = dict(value)

    @property
    def failed_records(self): return self._failed_records
    @failed_records.setter
    def failed_records(self, value):
        if int(value) < 0: raise ValueError("failed_records cannot be negative")
        self._failed_records = int(value)

    @property
    def total_cost_eur(self): return self._total_cost_eur
    @total_cost_eur.setter
    def total_cost_eur(self, value):
        if float(value) < 0: raise ValueError("cost cannot be negative")
        self._total_cost_eur = float(value)


class EmissionsTrend:
    """Stores chronological monthly emissions and calculates year-over-year change."""

    def __init__(self, months: Optional[Iterable[Dict[str, float]]] = None,
                 previous_year_total: float = 0.0):
        self._months: List[Dict[str, float]] = []
        self._previous_year_total = 0.0
        self.initialize(months or [], previous_year_total)

    def initialize(self, months, previous_year_total=0.0):
        self.months = months
        self.previous_year_total = previous_year_total

    @property
    def months(self): return [dict(item) for item in self._months]
    @months.setter
    def months(self, value):
        self._months = [{"month": str(item["month"]), "t_co2e": float(item["t_co2e"])} for item in value]

    @property
    def previous_year_total(self): return self._previous_year_total
    @previous_year_total.setter
    def previous_year_total(self, value):
        if float(value) < 0: raise ValueError("previous year total cannot be negative")
        self._previous_year_total = float(value)

    @property
    def current_total(self): return round(sum(item["t_co2e"] for item in self._months), 4)

    @property
    def pct_change(self):
        if self._previous_year_total == 0: return None
        return round((self.current_total - self._previous_year_total) / self._previous_year_total * 100, 2)


class SustainabilityScore:
    """Encapsulates the 0-100 score and its four reporting components."""

    def __init__(self, score: float = 0.0, components: Optional[Dict[str, float]] = None):
        self._score = 0.0
        self._components: Dict[str, float] = {}
        self.initialize(score, components or {})

    def initialize(self, score, components):
        self.score = score
        self.components = components

    @property
    def score(self): return self._score
    @score.setter
    def score(self, value):
        if not 0 <= float(value) <= 100: raise ValueError("score must be between 0 and 100")
        self._score = round(float(value), 1)

    @property
    def components(self): return dict(self._components)
    @components.setter
    def components(self, value):
        if any(float(points) < 0 or float(points) > 25 for points in value.values()):
            raise ValueError("each score component must be between 0 and 25")
        self._components = {str(name): float(points) for name, points in value.items()}

    def recalculate(self):
        self.score = sum(self._components.values())
        return self._score


def demo():
    """Small presentation-ready demonstration of the S3 classes."""

    print("--- EmissionsSummary ---")
    summary = EmissionsSummary(total_t_co2e=12.5)
    summary.initialize(date(2026, 1, 1), date(2026, 1, 31))
    summary.total_cost_eur = 1250.00       # setter
    print("Total emissions (getter):", summary.total_t_co2e)
    print("Reporting period (getter):", summary.period_start, "to", summary.period_end)
    print("Total cost (getter):", summary.total_cost_eur)

    print("\n--- EmissionsTrend ---")
    trend = EmissionsTrend(
        [{"month": "2026-01", "t_co2e": 10.0}, {"month": "2026-02", "t_co2e": 15.0}],
        previous_year_total=20.0,
    )
    print("Current total (calculated getter):", trend.current_total)
    print("YoY change (calculated getter):", trend.pct_change, "%")
    trend.previous_year_total = 25.0       # setter
    print("Updated YoY change:", trend.pct_change, "%")

    print("\n--- SustainabilityScore ---")
    score = SustainabilityScore(
        components={"trend": 20, "targets": 15, "completeness": 25, "intensity": 10}
    )
    print("Initial score (getter):", score.score)
    print("Recalculated score:", score.recalculate())
    score.score = 75.0                    # setter
    print("Updated score (getter):", score.score)

    print("\n--- Validation ---")
    try:
        summary.total_t_co2e = -1
    except ValueError as error:
        print("Invalid value rejected:", error)


if __name__ == "__main__":
    demo()
