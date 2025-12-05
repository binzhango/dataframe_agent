"""Structured logging utility for the LLM-Driven Secure Python Execution Platform."""

import logging
import json
import sys
import hashlib
import hmac
import base64
import requests
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List
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


def setup_logging(
    service_name: str,
    level: str = "INFO",
    azure_workspace_id: Optional[str] = None,
    azure_shared_key: Optional[str] = None,
    azure_log_type: str = "LLMExecutorLogs",
    retention_info_days: int = 30,
    retention_error_days: int = 90,
) -> None:
    """
    Set up structured logging for a service.
    
    This function configures:
    - Console logging with structured JSON format
    - Optional Azure Log Analytics integration for log aggregation
    - Configurable retention policies for different log levels

    Args:
        service_name: Name of the service (e.g., "llm-service", "executor-service")
        level: Logging level (default: "INFO")
        azure_workspace_id: Azure Log Analytics workspace ID (optional)
        azure_shared_key: Azure Log Analytics shared key (optional)
        azure_log_type: Custom log type name (default: "LLMExecutorLogs")
        retention_info_days: Retention period for INFO logs (default: 30 days)
        retention_error_days: Retention period for ERROR logs (default: 90 days)
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
    
    # Configure Azure Log Analytics if credentials are provided
    if azure_workspace_id and azure_shared_key:
        configure_azure_log_analytics(
            workspace_id=azure_workspace_id,
            shared_key=azure_shared_key,
            log_type=azure_log_type,
            retention_info_days=retention_info_days,
            retention_error_days=retention_error_days,
        )


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


class AzureLogAnalyticsHandler(logging.Handler):
    """
    Custom logging handler that sends logs to Azure Log Analytics.
    
    This handler implements log aggregation for centralized monitoring
    and supports configurable retention policies.
    
    Requirements:
    - 6.4: Implement log aggregation configuration for Azure Log Analytics
    - Set up log retention policies (30 days INFO, 90 days ERROR)
    """
    
    def __init__(
        self,
        workspace_id: str,
        shared_key: str,
        log_type: str = "LLMExecutorLogs",
        retention_info_days: int = 30,
        retention_error_days: int = 90,
    ):
        """
        Initialize Azure Log Analytics handler.
        
        Args:
            workspace_id: Azure Log Analytics workspace ID
            shared_key: Azure Log Analytics shared key
            log_type: Custom log type name
            retention_info_days: Retention period for INFO logs (default: 30 days)
            retention_error_days: Retention period for ERROR logs (default: 90 days)
        """
        super().__init__()
        self.workspace_id = workspace_id
        self.shared_key = shared_key
        self.log_type = log_type
        self.retention_info_days = retention_info_days
        self.retention_error_days = retention_error_days
        
        # Azure Log Analytics endpoint
        self.endpoint = f"https://{workspace_id}.ods.opinsights.azure.com/api/logs?api-version=2016-04-01"
    
    def emit(self, record: logging.LogRecord):
        """
        Emit a log record to Azure Log Analytics.
        
        Args:
            record: Log record to emit
        """
        try:
            # Format the log record
            log_entry = self._format_log_entry(record)
            
            # Send to Azure Log Analytics
            self._send_to_azure(log_entry)
        
        except Exception as e:
            # Don't let logging errors break the application
            self.handleError(record)
    
    def _format_log_entry(self, record: logging.LogRecord) -> Dict[str, Any]:
        """
        Format log record for Azure Log Analytics.
        
        Args:
            record: Log record to format
        
        Returns:
            Dictionary with log data
        """
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": getattr(record, "service", "unknown"),
            "message": record.getMessage(),
            "logger_name": record.name,
            "module": record.module,
            "function": record.funcName,
            "line_number": record.lineno,
        }
        
        # Add request_id from context
        request_id = request_id_context.get()
        if request_id:
            log_data["request_id"] = request_id
        
        # Add extra fields from record
        excluded_fields = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs", "message",
            "pathname", "process", "processName", "relativeCreated",
            "thread", "threadName", "exc_info", "exc_text", "stack_info",
            "taskName", "service"
        }
        
        for key, value in record.__dict__.items():
            if key not in excluded_fields and value is not None:
                if key == "request_id" and "request_id" in log_data:
                    continue
                log_data[key] = value
        
        # Add exception info if present
        if record.exc_info:
            formatter = logging.Formatter()
            log_data["stack_trace"] = formatter.formatException(record.exc_info)
        
        # Add retention policy based on log level
        if record.levelno >= logging.ERROR:
            log_data["retention_days"] = self.retention_error_days
        else:
            log_data["retention_days"] = self.retention_info_days
        
        return log_data
    
    def _send_to_azure(self, log_entry: Dict[str, Any]):
        """
        Send log entry to Azure Log Analytics.
        
        Args:
            log_entry: Log data to send
        """
        # Convert log entry to JSON
        body = json.dumps([log_entry])
        
        # Build signature for authentication
        content_length = len(body)
        rfc1123date = datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S GMT')
        
        string_to_hash = f"POST\n{content_length}\napplication/json\nx-ms-date:{rfc1123date}\n/api/logs"
        bytes_to_hash = bytes(string_to_hash, encoding="utf-8")
        decoded_key = base64.b64decode(self.shared_key)
        encoded_hash = base64.b64encode(
            hmac.new(decoded_key, bytes_to_hash, digestmod=hashlib.sha256).digest()
        ).decode()
        
        authorization = f"SharedKey {self.workspace_id}:{encoded_hash}"
        
        # Build headers
        headers = {
            "content-type": "application/json",
            "Authorization": authorization,
            "Log-Type": self.log_type,
            "x-ms-date": rfc1123date,
        }
        
        # Send request to Azure Log Analytics
        response = requests.post(
            self.endpoint,
            data=body,
            headers=headers,
            timeout=10,
        )
        
        # Check response
        if response.status_code not in (200, 202):
            raise Exception(
                f"Failed to send logs to Azure Log Analytics: {response.status_code} - {response.text}"
            )


def configure_azure_log_analytics(
    workspace_id: str,
    shared_key: str,
    log_type: str = "LLMExecutorLogs",
    retention_info_days: int = 30,
    retention_error_days: int = 90,
) -> None:
    """
    Configure Azure Log Analytics integration for centralized logging.
    
    This function adds an Azure Log Analytics handler to the root logger,
    enabling log aggregation with configurable retention policies.
    
    Requirements:
    - 6.4: Implement log aggregation configuration for Azure Log Analytics
    - Set up log retention policies (30 days INFO, 90 days ERROR)
    
    Args:
        workspace_id: Azure Log Analytics workspace ID
        shared_key: Azure Log Analytics shared key
        log_type: Custom log type name (default: "LLMExecutorLogs")
        retention_info_days: Retention period for INFO logs (default: 30 days)
        retention_error_days: Retention period for ERROR logs (default: 90 days)
    """
    if not workspace_id or not shared_key:
        # Skip configuration if credentials are not provided
        return
    
    logger = logging.getLogger()
    
    # Create Azure Log Analytics handler
    azure_handler = AzureLogAnalyticsHandler(
        workspace_id=workspace_id,
        shared_key=shared_key,
        log_type=log_type,
        retention_info_days=retention_info_days,
        retention_error_days=retention_error_days,
    )
    
    # Set formatter
    azure_handler.setFormatter(StructuredFormatter())
    
    # Add handler to root logger
    logger.addHandler(azure_handler)
    
    logging.info(
        "Azure Log Analytics integration configured",
        extra={
            "workspace_id": workspace_id,
            "log_type": log_type,
            "retention_info_days": retention_info_days,
            "retention_error_days": retention_error_days,
        }
    )
