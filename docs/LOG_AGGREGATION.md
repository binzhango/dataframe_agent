# Log Aggregation Configuration

This document describes how to configure log aggregation for the LLM-Driven Secure Python Execution Platform using Azure Log Analytics.

## Overview

The platform supports centralized log aggregation through Azure Log Analytics, enabling:
- Centralized log storage and querying
- Configurable retention policies based on log level
- Structured JSON logging for easy parsing and analysis
- Automatic inclusion of context information (request_id, component, operation)
- Stack traces for all error logs

## Configuration

### Environment Variables

To enable Azure Log Analytics integration, set the following environment variables:

```bash
# Azure Log Analytics workspace ID
AZURE_LOG_ANALYTICS_WORKSPACE_ID=your-workspace-id

# Azure Log Analytics shared key
AZURE_LOG_ANALYTICS_SHARED_KEY=your-shared-key

# Custom log type name (optional, default: "LLMExecutorLogs")
AZURE_LOG_ANALYTICS_LOG_TYPE=LLMExecutorLogs

# Log retention policies in days (optional)
LOG_RETENTION_INFO_DAYS=30   # Default: 30 days for INFO logs
LOG_RETENTION_ERROR_DAYS=90  # Default: 90 days for ERROR logs
```

### Programmatic Configuration

You can also configure Azure Log Analytics programmatically:

```python
from llm_executor.shared.logging_util import setup_logging
from llm_executor.shared.config import ExecutorServiceConfig

# Load configuration
config = ExecutorServiceConfig()

# Set up logging with Azure Log Analytics
setup_logging(
    service_name=config.service_name,
    level=config.log_level,
    azure_workspace_id=config.azure_log_analytics_workspace_id,
    azure_shared_key=config.azure_log_analytics_shared_key,
    azure_log_type=config.azure_log_analytics_log_type,
    retention_info_days=config.log_retention_info_days,
    retention_error_days=config.log_retention_error_days,
)
```

## Log Retention Policies

The platform implements different retention policies based on log level:

| Log Level | Default Retention | Configurable |
|-----------|------------------|--------------|
| INFO      | 30 days          | Yes          |
| WARNING   | 30 days          | Yes          |
| ERROR     | 90 days          | Yes          |
| CRITICAL  | 90 days          | Yes          |

Retention policies are automatically applied when logs are sent to Azure Log Analytics. The `retention_days` field is included in each log entry.

## Log Structure

All logs are structured as JSON with the following fields:

### Standard Fields

- `timestamp`: ISO 8601 timestamp in UTC
- `level`: Log level (INFO, WARNING, ERROR, CRITICAL)
- `service`: Service name (llm-service, executor-service, heavy-job-runner)
- `message`: Log message
- `logger_name`: Python logger name
- `module`: Python module name
- `function`: Function name where log was generated
- `line_number`: Line number in source file

### Context Fields

- `request_id`: Unique identifier for the request (automatically included)
- `component`: Component name (e.g., "secure_executor", "kubernetes_job_manager")
- `operation`: Operation name (e.g., "execute_code", "create_job")

### Error Fields

For ERROR and CRITICAL logs:
- `stack_trace`: Complete exception traceback
- `error`: Error message
- `error_type`: Exception type name

### Example Log Entry

```json
{
  "timestamp": "2024-12-05T10:30:00Z",
  "level": "ERROR",
  "service": "executor-service",
  "message": "Code execution failed with exception",
  "logger_name": "llm_executor.executor_service.api",
  "module": "api",
  "function": "execute_snippet",
  "line_number": 245,
  "request_id": "req-123",
  "component": "executor_service",
  "operation": "execute_code",
  "error": "Execution timeout",
  "error_type": "TimeoutError",
  "stack_trace": "Traceback (most recent call last):\n  File ...",
  "retention_days": 90
}
```

## Querying Logs in Azure Log Analytics

Once configured, logs can be queried using Kusto Query Language (KQL):

### Query all error logs for a specific request

```kql
LLMExecutorLogs_CL
| where level_s == "ERROR"
| where request_id_s == "req-123"
| order by timestamp_t desc
```

### Query logs by component

```kql
LLMExecutorLogs_CL
| where component_s == "secure_executor"
| order by timestamp_t desc
| take 100
```

### Query logs with stack traces

```kql
LLMExecutorLogs_CL
| where isnotempty(stack_trace_s)
| order by timestamp_t desc
```

### Aggregate error counts by service

```kql
LLMExecutorLogs_CL
| where level_s == "ERROR"
| summarize count() by service_s, bin(timestamp_t, 1h)
| render timechart
```

## Troubleshooting

### Logs not appearing in Azure Log Analytics

1. Verify workspace ID and shared key are correct
2. Check network connectivity to Azure
3. Verify the service has internet access
4. Check console logs for Azure Log Analytics handler errors

### High log volume

If log volume is too high:
1. Increase log level to WARNING or ERROR
2. Reduce retention periods
3. Implement log sampling for high-frequency events

### Missing context fields

Ensure `set_request_id()` is called at the start of request processing:

```python
from llm_executor.shared.logging_util import set_request_id, clear_request_id

# At request start
set_request_id(request_id)

try:
    # Process request
    pass
finally:
    # At request end
    clear_request_id()
```

## Security Considerations

- Store Azure Log Analytics credentials securely (use environment variables or secrets management)
- Never log sensitive data (passwords, API keys, PII)
- Use HTTPS for all Azure Log Analytics communication
- Rotate shared keys regularly
- Implement proper access controls on Azure Log Analytics workspace

## Requirements Validation

This log aggregation implementation satisfies:

- **Requirement 6.4**: Comprehensive error logging with stack traces and context information
- **Property 21**: Error logs contain stack traces
- **Property 18**: Structured logging includes request ID

All error handlers in the codebase use `exc_info=True` to include stack traces, and context information (request_id, component, operation) is included in all error logs.
