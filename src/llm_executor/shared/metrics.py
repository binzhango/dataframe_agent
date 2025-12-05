"""Prometheus metrics for monitoring and observability.

This module provides Prometheus metrics for tracking system performance,
including request rates, validation success rates, and execution durations.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from typing import Optional


# ============================================================================
# Request Metrics
# ============================================================================

request_counter = Counter(
    'llm_executor_requests_total',
    'Total number of requests received',
    ['service', 'endpoint', 'method']
)

request_duration = Histogram(
    'llm_executor_request_duration_seconds',
    'Request duration in seconds',
    ['service', 'endpoint', 'method'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
)


# ============================================================================
# Validation Metrics
# ============================================================================

validation_counter = Counter(
    'llm_executor_validations_total',
    'Total number of code validations',
    ['service', 'result']  # result: success, failure
)

validation_duration = Histogram(
    'llm_executor_validation_duration_seconds',
    'Code validation duration in seconds',
    ['service'],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)

validation_retry_counter = Counter(
    'llm_executor_validation_retries_total',
    'Total number of validation retry attempts',
    ['service']
)


# ============================================================================
# Execution Metrics
# ============================================================================

execution_counter = Counter(
    'llm_executor_executions_total',
    'Total number of code executions',
    ['service', 'classification', 'status']  # classification: lightweight, heavy; status: success, failure, timeout
)

execution_duration = Histogram(
    'llm_executor_execution_duration_seconds',
    'Code execution duration in seconds',
    ['service', 'classification'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
)

active_executions = Gauge(
    'llm_executor_active_executions',
    'Number of currently active code executions',
    ['service', 'classification']
)


# ============================================================================
# Classification Metrics
# ============================================================================

classification_counter = Counter(
    'llm_executor_classifications_total',
    'Total number of code classifications',
    ['service', 'result']  # result: lightweight, heavy
)


# ============================================================================
# Kubernetes Job Metrics
# ============================================================================

kubernetes_job_counter = Counter(
    'llm_executor_kubernetes_jobs_total',
    'Total number of Kubernetes Jobs created',
    ['service', 'status']  # status: created, failed
)

kubernetes_job_duration = Histogram(
    'llm_executor_kubernetes_job_duration_seconds',
    'Kubernetes Job execution duration in seconds',
    ['service'],
    buckets=(10.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0)
)


# ============================================================================
# Error Metrics
# ============================================================================

error_counter = Counter(
    'llm_executor_errors_total',
    'Total number of errors',
    ['service', 'error_type', 'component']
)


# ============================================================================
# Health Metrics
# ============================================================================

service_health = Gauge(
    'llm_executor_service_health',
    'Service health status (1 = healthy, 0 = unhealthy)',
    ['service']
)


# ============================================================================
# Helper Functions
# ============================================================================

def record_request(service: str, endpoint: str, method: str) -> None:
    """Record a request metric.
    
    Args:
        service: Service name (llm_service, executor_service)
        endpoint: API endpoint path
        method: HTTP method
    """
    request_counter.labels(service=service, endpoint=endpoint, method=method).inc()


def record_validation(service: str, success: bool, duration_seconds: float) -> None:
    """Record a validation metric.
    
    Args:
        service: Service name
        success: Whether validation succeeded
        duration_seconds: Validation duration in seconds
    """
    result = 'success' if success else 'failure'
    validation_counter.labels(service=service, result=result).inc()
    validation_duration.labels(service=service).observe(duration_seconds)


def record_validation_retry(service: str) -> None:
    """Record a validation retry attempt.
    
    Args:
        service: Service name
    """
    validation_retry_counter.labels(service=service).inc()


def record_execution(
    service: str,
    classification: str,
    status: str,
    duration_seconds: float
) -> None:
    """Record an execution metric.
    
    Args:
        service: Service name
        classification: Code classification (lightweight, heavy)
        status: Execution status (success, failure, timeout)
        duration_seconds: Execution duration in seconds
    """
    execution_counter.labels(
        service=service,
        classification=classification,
        status=status
    ).inc()
    execution_duration.labels(
        service=service,
        classification=classification
    ).observe(duration_seconds)


def record_classification(service: str, result: str) -> None:
    """Record a classification metric.
    
    Args:
        service: Service name
        result: Classification result (lightweight, heavy)
    """
    classification_counter.labels(service=service, result=result).inc()


def record_kubernetes_job(service: str, status: str, duration_seconds: Optional[float] = None) -> None:
    """Record a Kubernetes Job metric.
    
    Args:
        service: Service name
        status: Job status (created, failed)
        duration_seconds: Job duration in seconds (optional)
    """
    kubernetes_job_counter.labels(service=service, status=status).inc()
    if duration_seconds is not None:
        kubernetes_job_duration.labels(service=service).observe(duration_seconds)


def record_error(service: str, error_type: str, component: str) -> None:
    """Record an error metric.
    
    Args:
        service: Service name
        error_type: Type of error
        component: Component where error occurred
    """
    error_counter.labels(service=service, error_type=error_type, component=component).inc()


def set_active_executions(service: str, classification: str, count: int) -> None:
    """Set the number of active executions.
    
    Args:
        service: Service name
        classification: Code classification (lightweight, heavy)
        count: Number of active executions
    """
    active_executions.labels(service=service, classification=classification).set(count)


def set_service_health(service: str, healthy: bool) -> None:
    """Set service health status.
    
    Args:
        service: Service name
        healthy: Whether service is healthy
    """
    service_health.labels(service=service).set(1 if healthy else 0)


def get_metrics() -> tuple[bytes, str]:
    """Get Prometheus metrics in text format.
    
    Returns:
        Tuple of (metrics_bytes, content_type)
    """
    return generate_latest(), CONTENT_TYPE_LATEST
