"""S2 (Emission Engine) exceptions. They extend Saba's base class in exceptions.py,
so the same Flask error handler can turn them into JSON."""
from exceptions import S2_EmissionCalculationError


class S2_InvalidAmountError(S2_EmissionCalculationError):
    """Amount is missing, not a number, or negative."""


class S2_UnknownUnitError(S2_EmissionCalculationError):
    """Unit is not one the engine knows."""


class S2_IncompatibleUnitError(S2_EmissionCalculationError):
    """Unit cannot be converted to the factor's unit (e.g. litre -> kWh)."""


class S2_FactorNotFoundError(S2_EmissionCalculationError):
    """No emission factor exists for this activity."""
