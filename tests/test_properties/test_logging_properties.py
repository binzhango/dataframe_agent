"""Property-based tests for logging functionality.

This module contains property-based tests that verify logging behavior
across the LLM-Driven Secure Python Execution Platform.
"""

import json
import logging
import io
from hypothesis import given, strategies as st, settings
from llm_executor.shared.logging_util import (
    setup_logging,
    get_logger,
    set_request_id,
    clear_request_id,
)


# ============================================================================
# Test Strategies
# ============================================================================

@st.composite
def error_scenarios(draw):
    """Generate error scenarios with different exception types."""
    exception_types = [
        ValueError,
        RuntimeError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
    ]
    
    exc_type = draw(st.sampled_from(exception_types))
    error_message = draw(st.text(min_size=1, max_size=100))
    request_id = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pd'))))
    component = draw(st.sampled_from(["executor_service", "llm_service", "job_runner"]))
    operation = draw(st.sampled_from(["execute_code", "validate_code", "create_job", "upload_result"]))
    
    return {
        "exception_type": exc_type,
        "error_message": error_message,
        "request_id": request_id,
        "component": component,
        "operation": operation,
    }


# ============================================================================
# Property Tests
# ============================================================================

# Feature: llm-python-executor, Property 21: Error logs contain stack traces
@given(scenario=error_scenarios())
@settings(max_examples=100, deadline=None)
def test_error_logs_contain_stack_traces(scenario):
    """
    Property 21: Error logs contain stack traces
    
    For any error that occurs during execution, the error log entry must
    contain a stack_trace field with the complete exception traceback.
    
    This property verifies that:
    1. When an exception is logged with exc_info=True, the log contains stack trace
    2. The stack trace includes the exception type and message
    3. The log entry includes context information (request_id, component, operation)
    
    Validates: Requirements 6.4
    """
    # Create a string buffer to capture log output
    log_buffer = io.StringIO()
    handler = logging.StreamHandler(log_buffer)
    handler.setLevel(logging.ERROR)
    
    # Set up structured logging
    from llm_executor.shared.logging_util import StructuredFormatter
    formatter = StructuredFormatter()
    handler.setFormatter(formatter)
    
    # Get logger and add our handler
    logger = get_logger(__name__, service="test-service")
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.ERROR)
    
    # Set request_id in context
    set_request_id(scenario["request_id"])
    
    try:
        # Raise the exception to generate a real stack trace
        try:
            raise scenario["exception_type"](scenario["error_message"])
        except Exception as e:
            # Log the error with exc_info=True and context information
            logger.error(
                "Test error occurred",
                extra={
                    "request_id": scenario["request_id"],
                    "component": scenario["component"],
                    "operation": scenario["operation"],
                    "error": str(e),
                },
                exc_info=True
            )
        
        # Get the logged output
        log_output = log_buffer.getvalue()
        
        # Parse the JSON log entry
        assert log_output.strip(), "Log output should not be empty"
        log_entry = json.loads(log_output.strip())
        
        # Property 21: Error logs must contain stack_trace field
        assert "stack_trace" in log_entry, \
            "Error log entry must contain 'stack_trace' field"
        
        stack_trace = log_entry["stack_trace"]
        
        # Verify stack trace is not empty
        assert stack_trace, "Stack trace should not be empty"
        
        # Verify stack trace contains exception type
        assert scenario["exception_type"].__name__ in stack_trace, \
            f"Stack trace should contain exception type '{scenario['exception_type'].__name__}'"
        
        # Verify stack trace contains error message (or its repr for special characters)
        # For KeyError and similar, Python may escape the message in the stack trace
        error_msg_in_trace = (
            scenario["error_message"] in stack_trace or
            repr(scenario["error_message"]) in stack_trace or
            str(scenario["error_message"]) in stack_trace
        )
        assert error_msg_in_trace, \
            f"Stack trace should contain the error message or its representation"
        
        # Verify context information is present
        assert log_entry.get("request_id") == scenario["request_id"], \
            "Log entry should contain request_id"
        
        assert log_entry.get("component") == scenario["component"], \
            "Log entry should contain component"
        
        assert log_entry.get("operation") == scenario["operation"], \
            "Log entry should contain operation"
        
        # Verify log level is ERROR
        assert log_entry.get("level") == "ERROR", \
            "Log level should be ERROR"
        
    finally:
        # Clean up
        clear_request_id()
        logger.logger.removeHandler(handler)
        handler.close()


# Feature: llm-python-executor, Property 18: Structured logging includes request ID
@given(
    request_id=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd', 'Pd'))),
    message=st.text(min_size=1, max_size=100)
)
@settings(max_examples=100, deadline=None)
def test_structured_logging_includes_request_id(request_id, message):
    """
    Property 18: Structured logging includes request ID
    
    For any request processed by any component, all log entries related to
    that request must include the request_id field.
    
    This property verifies that:
    1. When request_id is set in context, it appears in all log entries
    2. The request_id is correctly propagated through the logging system
    3. Log entries are properly structured as JSON
    
    Validates: Requirements 5.5, 6.1
    """
    # Create a string buffer to capture log output
    log_buffer = io.StringIO()
    handler = logging.StreamHandler(log_buffer)
    handler.setLevel(logging.INFO)
    
    # Set up structured logging
    from llm_executor.shared.logging_util import StructuredFormatter
    formatter = StructuredFormatter()
    handler.setFormatter(formatter)
    
    # Get logger and add our handler
    logger = get_logger(__name__, service="test-service")
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.INFO)
    
    # Set request_id in context
    set_request_id(request_id)
    
    try:
        # Log a message
        logger.info(message)
        
        # Get the logged output
        log_output = log_buffer.getvalue()
        
        # Parse the JSON log entry
        assert log_output.strip(), "Log output should not be empty"
        log_entry = json.loads(log_output.strip())
        
        # Property 18: Log entry must contain request_id
        assert "request_id" in log_entry, \
            "Log entry must contain 'request_id' field"
        
        assert log_entry["request_id"] == request_id, \
            f"Log entry request_id should be '{request_id}'"
        
        # Verify message is present
        assert log_entry.get("message") == message, \
            "Log entry should contain the message"
        
        # Verify service is present
        assert "service" in log_entry, \
            "Log entry should contain service field"
        
        # Verify timestamp is present
        assert "timestamp" in log_entry, \
            "Log entry should contain timestamp field"
        
        # Verify level is present
        assert "level" in log_entry, \
            "Log entry should contain level field"
        
    finally:
        # Clean up
        clear_request_id()
        logger.logger.removeHandler(handler)
        handler.close()
