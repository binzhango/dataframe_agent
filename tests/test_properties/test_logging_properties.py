"""Property-based tests for structured logging utility.

Feature: llm-python-executor, Property 18: Structured logging includes request ID
Validates: Requirements 5.5, 6.1
"""

import json
import logging
from io import StringIO
from hypothesis import given, settings, strategies as st

from llm_executor.shared.logging_util import (
    setup_logging,
    get_logger,
    set_request_id,
    clear_request_id,
    StructuredFormatter,
)


@st.composite
def request_ids(draw):
    """Generate valid request IDs."""
    prefix = draw(st.sampled_from(["req", "request", "job", "exec"]))
    number = draw(st.integers(min_value=1, max_value=999999))
    return f"{prefix}-{number}"


@st.composite
def log_messages(draw):
    """Generate log messages."""
    return draw(st.text(min_size=1, max_size=200))


@st.composite
def service_names(draw):
    """Generate service names."""
    return draw(st.sampled_from([
        "llm-service",
        "executor-service",
        "heavy-job-runner",
        "test-service"
    ]))


# Feature: llm-python-executor, Property 18: Structured logging includes request ID
@given(
    request_id=request_ids(),
    message=log_messages(),
    service_name=service_names()
)
@settings(max_examples=100)
def test_structured_logging_includes_request_id(request_id, message, service_name):
    """
    Property: For any request processed by any component, all log entries
    related to that request must include the request_id field.
    
    This test verifies that when a request_id is set in the context,
    all subsequent log entries include that request_id in the structured output.
    """
    # Set up logging with a string buffer to capture output
    log_buffer = StringIO()
    handler = logging.StreamHandler(log_buffer)
    handler.setFormatter(StructuredFormatter())
    
    logger = logging.getLogger(f"test_logger_{request_id}")
    logger.setLevel(logging.INFO)
    logger.handlers = []
    logger.addHandler(handler)
    
    # Create adapter with service context
    adapter = logging.LoggerAdapter(logger, {"service": service_name})
    
    # Set request_id in context
    set_request_id(request_id)
    
    try:
        # Log a message
        adapter.info(message)
        
        # Get the logged output
        log_output = log_buffer.getvalue()
        
        # Parse the JSON log entry
        log_entry = json.loads(log_output.strip())
        
        # Verify request_id is present in the log entry
        assert "request_id" in log_entry, f"request_id missing from log entry: {log_entry}"
        assert log_entry["request_id"] == request_id, \
            f"Expected request_id '{request_id}', got '{log_entry['request_id']}'"
        
        # Verify other required fields are present
        assert "timestamp" in log_entry, "timestamp missing from log entry"
        assert "level" in log_entry, "level missing from log entry"
        assert "service" in log_entry, "service missing from log entry"
        assert "message" in log_entry, "message missing from log entry"
        
        # Verify service name is correct
        assert log_entry["service"] == service_name, \
            f"Expected service '{service_name}', got '{log_entry['service']}'"
        
        # Verify message is correct
        assert log_entry["message"] == message, \
            f"Expected message '{message}', got '{log_entry['message']}'"
    
    finally:
        # Clean up
        clear_request_id()
        logger.handlers = []


@given(
    request_id=request_ids(),
    message=log_messages(),
    service_name=service_names()
)
@settings(max_examples=100)
def test_structured_logging_without_request_id_context(request_id, message, service_name):
    """
    Property: When request_id is passed as a log record attribute (not context),
    it should still appear in the structured log output.
    
    This ensures backward compatibility and flexibility in how request_id is provided.
    """
    # Set up logging with a string buffer to capture output
    log_buffer = StringIO()
    handler = logging.StreamHandler(log_buffer)
    handler.setFormatter(StructuredFormatter())
    
    logger = logging.getLogger(f"test_logger_attr_{request_id}")
    logger.setLevel(logging.INFO)
    logger.handlers = []
    logger.addHandler(handler)
    
    # Create adapter with service context
    adapter = logging.LoggerAdapter(logger, {"service": service_name})
    
    # Clear any existing request_id from context
    clear_request_id()
    
    try:
        # Log a message with request_id as extra field
        adapter.info(message, extra={"request_id": request_id})
        
        # Get the logged output
        log_output = log_buffer.getvalue()
        
        # Parse the JSON log entry
        log_entry = json.loads(log_output.strip())
        
        # Verify request_id is present in the log entry
        assert "request_id" in log_entry, f"request_id missing from log entry: {log_entry}"
        assert log_entry["request_id"] == request_id, \
            f"Expected request_id '{request_id}', got '{log_entry['request_id']}'"
    
    finally:
        # Clean up
        logger.handlers = []


@given(
    request_id=request_ids(),
    service_name=service_names()
)
@settings(max_examples=100)
def test_request_id_context_isolation(request_id, service_name):
    """
    Property: Request IDs set in context should be properly isolated
    and clearable without affecting other logging.
    """
    # Set up logging
    log_buffer = StringIO()
    handler = logging.StreamHandler(log_buffer)
    handler.setFormatter(StructuredFormatter())
    
    logger = logging.getLogger(f"test_logger_isolation_{request_id}")
    logger.setLevel(logging.INFO)
    logger.handlers = []
    logger.addHandler(handler)
    
    adapter = logging.LoggerAdapter(logger, {"service": service_name})
    
    try:
        # Set request_id
        set_request_id(request_id)
        
        # Log with request_id
        adapter.info("Message with request_id")
        log_output_1 = log_buffer.getvalue()
        log_entry_1 = json.loads(log_output_1.strip())
        
        assert log_entry_1["request_id"] == request_id
        
        # Clear request_id
        clear_request_id()
        log_buffer.truncate(0)
        log_buffer.seek(0)
        
        # Log without request_id
        adapter.info("Message without request_id")
        log_output_2 = log_buffer.getvalue()
        
        if log_output_2.strip():
            log_entry_2 = json.loads(log_output_2.strip())
            # request_id should not be present after clearing
            assert "request_id" not in log_entry_2 or log_entry_2.get("request_id") is None
    
    finally:
        # Clean up
        clear_request_id()
        logger.handlers = []
