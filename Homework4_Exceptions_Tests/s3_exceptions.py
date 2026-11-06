"""Custom exceptions for the S3 analytics and reporting subsystem."""

from exceptions import S3_AnalyticsReportError


class S3_InvalidRecordError(S3_AnalyticsReportError):
    """Raised when an emissions record is missing or contains invalid data."""


class S3_InvalidDateRangeError(S3_AnalyticsReportError):
    """Raised when the requested reporting date range is invalid."""


class S3_UnsupportedMetricError(S3_AnalyticsReportError):
    """Raised when an analytics metric is not supported."""


class S3_NoDataError(S3_AnalyticsReportError):
    """Raised when a report cannot be produced because no records exist."""

