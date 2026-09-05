from enum import StrEnum


class SubscriptionHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    ERROR = "error"
    DISABLED = "disabled"
