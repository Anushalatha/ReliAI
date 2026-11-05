import re
from typing import Any

from app.providers.base import InvalidProviderOutput, ProviderExecutionError

SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*['\"]?[^'\"\s,;]+"),
)


def sanitize_error_message(message: str) -> str:
    sanitized = message
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized[:1000]


def classify_execution_error(error: Exception) -> str:
    name = type(error).__name__.casefold()
    message = str(error).casefold()
    if isinstance(error, TimeoutError) or "timeout" in name or "timed out" in message:
        return "timeout"
    if "ratelimit" in name or re.search(r"rate[_ -]?limit", message) or "429" in message:
        return "rate_limit"
    if isinstance(error, InvalidProviderOutput):
        return "invalid_output"
    if isinstance(error, ProviderExecutionError):
        return "provider_error"
    return "unknown_error"


def sanitized_error_details(error: Exception, category: str) -> dict[str, Any]:
    return {
        "category": category,
        "exception_type": type(error).__name__,
    }
