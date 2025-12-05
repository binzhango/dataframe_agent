"""OpenTelemetry distributed tracing configuration.

This module provides OpenTelemetry instrumentation for distributed tracing
across service boundaries, with span annotations for key operations.
"""

import os
from typing import Optional, Dict, Any
from contextlib import contextmanager

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import Status, StatusCode, Span
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator


# ============================================================================
# Tracer Configuration
# ============================================================================

# Global tracer instance
_tracer: Optional[trace.Tracer] = None
_tracer_provider: Optional[TracerProvider] = None


def initialize_tracing(
    service_name: str,
    service_version: str = "1.0.0",
    otlp_endpoint: Optional[str] = None,
) -> None:
    """Initialize OpenTelemetry tracing.
    
    Args:
        service_name: Name of the service
        service_version: Version of the service
        otlp_endpoint: OTLP collector endpoint (optional, defaults to env var)
    """
    global _tracer, _tracer_provider
    
    # Get OTLP endpoint from environment if not provided
    if otlp_endpoint is None:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    
    # Create resource with service information
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
    })
    
    # Create tracer provider
    _tracer_provider = TracerProvider(resource=resource)
    
    # Configure OTLP exporter
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    
    # Add batch span processor
    span_processor = BatchSpanProcessor(otlp_exporter)
    _tracer_provider.add_span_processor(span_processor)
    
    # Set global tracer provider
    trace.set_tracer_provider(_tracer_provider)
    
    # Create tracer
    _tracer = trace.get_tracer(__name__)


def get_tracer() -> trace.Tracer:
    """Get the global tracer instance.
    
    Returns:
        Tracer instance
        
    Raises:
        RuntimeError: If tracing has not been initialized
    """
    if _tracer is None:
        raise RuntimeError("Tracing has not been initialized. Call initialize_tracing() first.")
    return _tracer


def instrument_fastapi(app) -> None:
    """Instrument a FastAPI application with OpenTelemetry.
    
    Args:
        app: FastAPI application instance
    """
    FastAPIInstrumentor.instrument_app(app)


def shutdown_tracing() -> None:
    """Shutdown tracing and flush remaining spans."""
    global _tracer_provider
    if _tracer_provider is not None:
        _tracer_provider.shutdown()


# ============================================================================
# Span Context Management
# ============================================================================

@contextmanager
def start_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL,
):
    """Start a new span with optional attributes.
    
    Args:
        name: Span name
        attributes: Optional span attributes
        kind: Span kind (INTERNAL, CLIENT, SERVER, etc.)
        
    Yields:
        Span instance
    """
    tracer = get_tracer()
    with tracer.start_as_current_span(name, kind=kind) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span


def add_span_attribute(key: str, value: Any) -> None:
    """Add an attribute to the current span.
    
    Args:
        key: Attribute key
        value: Attribute value
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute(key, value)


def add_span_event(name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
    """Add an event to the current span.
    
    Args:
        name: Event name
        attributes: Optional event attributes
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.add_event(name, attributes=attributes or {})


def set_span_status(status_code: StatusCode, description: Optional[str] = None) -> None:
    """Set the status of the current span.
    
    Args:
        status_code: Status code (OK, ERROR, UNSET)
        description: Optional status description
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.set_status(Status(status_code, description))


def record_exception(exception: Exception) -> None:
    """Record an exception in the current span.
    
    Args:
        exception: Exception to record
    """
    span = trace.get_current_span()
    if span.is_recording():
        span.record_exception(exception)
        span.set_status(Status(StatusCode.ERROR, str(exception)))


# ============================================================================
# Trace Propagation
# ============================================================================

_propagator = TraceContextTextMapPropagator()


def inject_trace_context(carrier: Dict[str, str]) -> None:
    """Inject trace context into a carrier (e.g., HTTP headers).
    
    Args:
        carrier: Dictionary to inject trace context into
    """
    _propagator.inject(carrier)


def extract_trace_context(carrier: Dict[str, str]) -> None:
    """Extract trace context from a carrier (e.g., HTTP headers).
    
    Args:
        carrier: Dictionary containing trace context
    """
    _propagator.extract(carrier)


# ============================================================================
# Operation-Specific Spans
# ============================================================================

@contextmanager
def trace_code_generation(query: str, request_id: str):
    """Create a span for code generation operation.
    
    Args:
        query: Natural language query
        request_id: Request identifier
        
    Yields:
        Span instance
    """
    with start_span(
        "code_generation",
        attributes={
            "operation": "code_generation",
            "request_id": request_id,
            "query_length": len(query),
        },
        kind=trace.SpanKind.INTERNAL,
    ) as span:
        yield span


@contextmanager
def trace_validation(code: str, request_id: str):
    """Create a span for code validation operation.
    
    Args:
        code: Python code to validate
        request_id: Request identifier
        
    Yields:
        Span instance
    """
    with start_span(
        "code_validation",
        attributes={
            "operation": "validation",
            "request_id": request_id,
            "code_length": len(code),
        },
        kind=trace.SpanKind.INTERNAL,
    ) as span:
        yield span


@contextmanager
def trace_classification(code: str, request_id: str):
    """Create a span for code classification operation.
    
    Args:
        code: Python code to classify
        request_id: Request identifier
        
    Yields:
        Span instance
    """
    with start_span(
        "code_classification",
        attributes={
            "operation": "classification",
            "request_id": request_id,
            "code_length": len(code),
        },
        kind=trace.SpanKind.INTERNAL,
    ) as span:
        yield span


@contextmanager
def trace_execution(code: str, request_id: str, classification: str):
    """Create a span for code execution operation.
    
    Args:
        code: Python code to execute
        request_id: Request identifier
        classification: Code classification (lightweight, heavy)
        
    Yields:
        Span instance
    """
    with start_span(
        "code_execution",
        attributes={
            "operation": "execution",
            "request_id": request_id,
            "code_length": len(code),
            "classification": classification,
        },
        kind=trace.SpanKind.INTERNAL,
    ) as span:
        yield span


@contextmanager
def trace_kubernetes_job(job_id: str, request_id: str):
    """Create a span for Kubernetes Job creation operation.
    
    Args:
        job_id: Job identifier
        request_id: Request identifier
        
    Yields:
        Span instance
    """
    with start_span(
        "kubernetes_job_creation",
        attributes={
            "operation": "kubernetes_job",
            "request_id": request_id,
            "job_id": job_id,
        },
        kind=trace.SpanKind.CLIENT,
    ) as span:
        yield span
