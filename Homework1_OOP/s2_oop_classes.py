"""Homework 1 - Object-oriented concepts (S2: Emission Engine, Tuba Jabeen).

Shows: encapsulation (private attributes + properties with validation),
inheritance and polymorphism (two calculators), abstract base class,
magic methods (__str__, __repr__, __eq__, __lt__, __add__, __len__, __iter__).

Run:  python s2_oop_classes.py
"""
import csv
from abc import ABC, abstractmethod
from decimal import Decimal
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"

# unit -> (dimension, ratio to the base unit of that dimension)
UNITS = {
    "kWh": ("energy", Decimal("1")), "MWh": ("energy", Decimal("1000")),
    "kg": ("mass", Decimal("1")), "tonne": ("mass", Decimal("1000")),
    "litre": ("volume", Decimal("1")), "m3": ("volume", Decimal("1000")),
    "km": ("distance", Decimal("1")), "miles": ("distance", Decimal("1.609344")),
    "passenger_km": ("passenger_distance", Decimal("1")), "night": ("night", Decimal("1")),
}


class EmissionError(Exception):
    """Raised when an emission cannot be calculated. We never return 0 silently."""


# ---------------------------------------------------------------- data classes
class EmissionFactor:
    """kg CO2e per one unit of an activity (encapsulated, validated)."""

    def __init__(self, activity_type, region, year, unit, kg_co2e_per_unit, source=""):
        self._activity_type = activity_type
        self._region = region
        self.year = year                      # goes through the setter below
        self.unit = unit
        self.kg_co2e_per_unit = kg_co2e_per_unit
        self._source = source

    @property
    def activity_type(self):
        return self._activity_type

    @property
    def region(self):
        return self._region

    @property
    def year(self):
        return self._year

    @year.setter
    def year(self, value):
        if not 1990 <= int(value) <= 2100:
            raise ValueError("year must be between 1990 and 2100")
        self._year = int(value)

    @property
    def unit(self):
        return self._unit

    @unit.setter
    def unit(self, value):
        if value not in UNITS:
            raise ValueError(f"unknown unit '{value}'")
        self._unit = value

    @property
    def kg_co2e_per_unit(self):
        return self._value

    @kg_co2e_per_unit.setter
    def kg_co2e_per_unit(self, value):
        value = Decimal(str(value))
        if value < 0:
            raise ValueError("a factor cannot be negative")
        self._value = value

    def __repr__(self):
        return (f"EmissionFactor({self._activity_type!r}, {self._region!r}, {self._year}, "
                f"{self._unit!r}, {self._value})")

    def __eq__(self, other):
        return isinstance(other, EmissionFactor) and (
            self._activity_type, self._region, self._year, self._unit, self._value
        ) == (other._activity_type, other._region, other._year, other._unit, other._value)

    def __hash__(self):
        return hash((self._activity_type, self._region, self._year, self._unit))


class Activity:
    """One thing a company did, e.g. used 450 kWh of electricity."""

    def __init__(self, activity_type, amount, unit, year=2026, region="DE"):
        self.activity_type = activity_type
        self.amount = amount
        self.unit = unit
        self.year = year
        self.region = region

    @property
    def amount(self):
        return self._amount

    @amount.setter
    def amount(self, value):
        value = Decimal(str(value))
        if value < 0:
            raise ValueError("amount cannot be negative")
        self._amount = value


class EmissionResult:
    """Result of a calculation. Supports + so results can be summed."""

    def __init__(self, kg_co2e, method, factor=None):
        self._kg = Decimal(kg_co2e)
        self.method = method
        self.factor = factor

    @property
    def kg_co2e(self):
        return self._kg

    @property
    def tonnes(self):
        return self._kg / 1000

    def __add__(self, other):
        return EmissionResult(self._kg + other._kg, "sum")

    def __radd__(self, other):                # makes sum([...]) work (starts with 0)
        return self if other == 0 else self.__add__(other)

    def __lt__(self, other):
        return self._kg < other._kg

    def __str__(self):
        return f"{self._kg.quantize(Decimal('0.0001'))} kg CO2e ({self.method})"


# ------------------------------------------------------------------- catalogue
class FactorCatalog:
    """Holds all factors. Selection rule: same region+year, else nearest year, else GLOBAL."""

    def __init__(self, factors=()):
        self._factors = list(factors)

    @classmethod
    def from_csv(cls, path=SEED_DIR / "factors.csv"):
        with open(path, newline="", encoding="utf-8") as f:
            return cls(EmissionFactor(r["activity_type"], r["region"], r["year"], r["unit"],
                                      r["kg_co2e_per_unit"], r["source"]) for r in csv.DictReader(f))

    def __len__(self):
        return len(self._factors)

    def __iter__(self):
        return iter(self._factors)

    def select(self, activity_type, region, year):
        for wanted_region in (region, "GLOBAL"):
            found = [f for f in self._factors
                     if f.activity_type == activity_type and f.region == wanted_region]
            if found:
                return min(found, key=lambda f: abs(f.year - year))
        raise EmissionError(f"no factor for '{activity_type}' in {region}/GLOBAL")


# ------------------------------------------------------- inheritance + polymorphism
class Calculator(ABC):
    """Base class. Subclasses decide HOW the factor is chosen (polymorphism)."""

    method = "base"

    @abstractmethod
    def factor_for(self, activity):
        """Return the EmissionFactor to use for this activity."""

    def calculate(self, activity):
        factor = self.factor_for(activity)
        from_dim, from_ratio = UNITS[activity.unit]
        to_dim, to_ratio = UNITS[factor.unit]
        if from_dim != to_dim:
            raise EmissionError(f"cannot convert {activity.unit} ({from_dim}) to {factor.unit} ({to_dim})")
        amount_in_factor_unit = activity.amount * from_ratio / to_ratio
        return EmissionResult(amount_in_factor_unit * factor.kg_co2e_per_unit, self.method, factor)


class LocationBasedCalculator(Calculator):
    """Uses the grid/average factor from the catalogue."""

    method = "location_based"

    def __init__(self, catalog):
        self._catalog = catalog

    def factor_for(self, activity):
        return self._catalog.select(activity.activity_type, activity.region, activity.year)


class MarketBasedCalculator(LocationBasedCalculator):
    """Inherits everything; for electricity uses the company's own green-tariff factor."""

    method = "market_based"

    def __init__(self, catalog, green_kg_per_kwh):
        super().__init__(catalog)
        self._green = Decimal(str(green_kg_per_kwh))

    def factor_for(self, activity):
        if activity.activity_type == "electricity":
            return EmissionFactor("electricity", "FACILITY", activity.year, "kWh", self._green, "green tariff")
        return super().factor_for(activity)


# ------------------------------------------------------------------------- demo
if __name__ == "__main__":
    catalog = FactorCatalog.from_csv()
    print(f"Loaded {len(catalog)} emission factors from seed/factors.csv\n")

    work = [Activity("electricity", 450, "kWh"), Activity("diesel", 120, "litre"),
            Activity("fleet_km", 100, "miles")]
    location = LocationBasedCalculator(catalog)
    results = [location.calculate(a) for a in work]
    for a, r in zip(work, results):
        print(f"{a.activity_type:12} {a.amount:>6} {a.unit:6} -> {r}")
    print("TOTAL:", sum(results), "\n")

    green = MarketBasedCalculator(catalog, green_kg_per_kwh="0.05")
    print("Same electricity with a green tariff:", green.calculate(work[0]))

    print("\nError handling (never a silent zero):")
    for bad in (Activity("electricity", 5, "litre"), Activity("rocket_fuel", 1, "kg")):
        try:
            location.calculate(bad)
        except EmissionError as e:
            print("  EmissionError:", e)
