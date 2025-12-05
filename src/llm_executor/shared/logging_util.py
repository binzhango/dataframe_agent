"""Structured logging utility for the LLM-Driven Secure Python Execution Platform."""

import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from contextvars import ContextVar

# Context variable to store request_id across async contexts
request_id_context: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class StructuredFormatter(logging.Formatter):
    """Custom formatter that outputs structured JSON logs."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON."""
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": getattr(record, "service", "unknown"),
            "message": record.getMessage(),
        }

        # Standard logging fields to exclude from extra data
        excluded_fields = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs", "message",
            "pathname", "process", "processName", "relativeCreated",
            "thread", "threadName", "exc_info", "exc_text", "stack_info",
            "taskName"
        }

        # Add request_id from context first (highest priority)
        request_id = request_id_context.get()
        if request_id:
            log_data["request_id"] = request_id
        
        # Add extra fields from record (including request_id if not from context)
        for key, value in record.__dict__.items():
            if key not in excluded_fields and value is not None:
                # Skip service and request_id if already set
                if key == "service" and "service" in log_data:
                    continue
                if key == "request_id" and "request_id" in log_data:
                    continue
                log_data[key] = value

        # Add exception info if present
        if record.exc_info:
            log_data["stack_trace"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging(service_name: str, level: str = "INFO") -> None:
    """
    Set up structured logging for a service.

    Args:
        service_name: Name of the service (e.g., "llm-service", "executor-service")
        level: Logging level (default: "INFO")
    """
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Create console handler with structured formatter
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))

    formatter = StructuredFormatter()
    handler.setFormatter(formatter)

    logger.addHandler(handler)

    # Store service name in root logger
    logging.getLogger().service_name = service_name


class CustomLoggerAdapter(logging.LoggerAdapter):
    """Custom LoggerAdapter that properly merges extra fields from both adapter and logging calls."""
    
    def process(self, msg, kwargs):
        """
        Process the logging call to merge extra fields from both the adapter
        and the logging call itself.
        """
        # Get extra from the logging call
        call_extra = kwargs.get("extra", {})
        
        # Merge adapter's extra with call's extra (call's extra takes precedence)
        merged_extra = {**self.extra, **call_extra}
        
        # Update kwargs with merged extra
        kwargs["extra"] = merged_extra
        
        return msg, kwargs


def get_logger(name: str, service: Optional[str] = None) -> logging.LoggerAdapter:
    """
    Get a logger with structured logging support.

    Args:
        name: Logger name (typically __name__)
        service: Service name (optional, uses root logger's service_name if not provided)

    Returns:
        CustomLoggerAdapter with service context
    """
    logger = logging.getLogger(name)

    # Get service name from root logger if not provided
    if service is None:
        service = getattr(logging.getLogger(), "service_name", "unknown")

    # Create custom adapter that properly merges extra fields
    adapter = CustomLoggerAdapter(logger, {"service": service})

    return adapter


def set_request_id(request_id: str) -> None:
    """
    Set the request_id in the current context.

    Args:
        request_id: Request identifier to set
    """
    request_id_context.set(request_id)


def clear_request_id() -> None:
    """Clear the request_id from the current context."""
    request_id_context.set(None)


def get_request_id() -> Optional[str]:
    """
    Get the current request_id from context.

    Returns:
        Current request_id or None
    """
    return request_id_context.get()
