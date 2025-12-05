"""Property-based tests for error handling and retry logic.

This module contains property-based tests that verify the correctness
properties of the ExecutionErrorHandler and RetryWrapper.
"""

import time
from unittest.mock import Mock, MagicMock
from hypothesis import given, settings, strategies as st

from llm_executor.executor_service.error_handlers import (
    ExecutionErrorHandler,
    RetryWrapper,
)
from llm_executor.executor_service.secure_executor import SecureExecutor
from llm_executor.shared.models import ExecutionResult, ExecutionStatus
from llm_executor.shared.exceptions import (
    ExecutionError,
    TimeoutError as ExecutionTimeoutError,
    MemoryError as ExecutionMemoryError,
    NetworkError,
    ResourceExhaustedError,
)


# ============================================================================
# Custom Strategies
# ============================================================================

@st.composite
def request_id_strategy(draw):
    """Generate valid request IDs."""
    prefix = draw(st.sampled_from(["req", "exec", "test", "retry"]))
    number = draw(st.integers(min_value=1, max_value=999999))
    return f"{prefix}-{number}"


@st.composite
def retryable_error_strategy(draw):
    """Generate retryable errors."""
    error_types = [
        ResourceExhaustedError("CPU"),
        ResourceExhaustedError("Memory"),
        ResourceExhaustedError("Disk"),
        RuntimeError("Temporary failure"),
        RuntimeError("Connection reset"),
    ]
    return draw(st.sampled_from(error_types))


@st.composite
def non_retryable_error_strategy(draw):
    """Generate non-retryable errors."""
    error_types = [
        ExecutionTimeoutError(30),
        ExecutionTimeoutError(60),
        ExecutionMemoryError("8Gi"),
        NetworkError(),
    ]
    return draw(st.sampled_from(error_types))


@st.composite
def code_that_fails_then_succeeds(draw):
    """Generate code that simulates failure then success pattern."""
    # This is a placeholder - in real tests we'll use mocks
    patterns = [
        "result = 1 + 1",
        "x = [1, 2, 3]\nresult = sum(x)",
        "result = 'hello' * 5",
    ]
    return draw(st.sampled_from(patterns))


# ============================================================================
# Property 24: Execution retry policy
# Validates: Requirements 9.2
# ============================================================================

# Feature: llm-python-executor, Property 24: Execution retry policy
@given(
    error=retryable_error_strategy(),
    request_id=request_id_strategy(),
    attempt=st.integers(min_value=0, max_value=2),
    max_retries=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=100, deadline=None)
def test_execution_retry_policy(error, request_id, attempt, max_retries):
    """
    Property: For any code execution that fails with a retryable error,
    the Executor Service must retry execution according to the configured
    retry policy (count and backoff).
    
    This test verifies that:
    1. Retryable errors trigger retry
    2. Backoff delay is calculated correctly (2^attempt, max 60s)
    3. Retry count is respected
    4. Error information is preserved
    """
    handler = ExecutionErrorHandler(max_retries=max_retries)
    
    # Verify error is classified as retryable
    assert handler.is_retryable(error), \
        f"Error {type(error).__name__} should be retryable"
    
    # Handle the error
    result = handler.handle_error(error, request_id, attempt)
    
    # If we haven't exceeded max retries, should get retry status
    if attempt < max_retries:
        assert result["status"] == "retry", \
            f"Should retry when attempt {attempt} < max_retries {max_retries}"
        
        assert result["retryable"] is True, \
            "Retryable errors should have retryable=True"
        
        # Verify backoff delay calculation (2^attempt, max 60)
        expected_backoff = min(2 ** attempt, 60)
        assert result["backoff_delay"] == expected_backoff, \
            f"Backoff should be {expected_backoff}s, got {result['backoff_delay']}s"
        
        # Verify attempt count is incremented
        assert result["attempts"] == attempt + 1, \
            f"Attempts should be incremented to {attempt + 1}"
        
        # Verify error information is preserved
        assert "error" in result, \
            "Error message should be included"
        assert "error_type" in result, \
            "Error type should be included"
    
    else:
        # Max retries exceeded
        assert result["status"] == "failed", \
            f"Should fail when attempt {attempt} >= max_retries {max_retries}"
        
        assert result["retryable"] is False, \
            "Should not retry after max retries exceeded"
        
        assert "reason" in result, \
            "Should include reason for failure"
        
        assert "Maximum retry attempts exceeded" in result["reason"], \
            "Reason should mention max retries exceeded"


# Feature: llm-python-executor, Property 24: Execution retry policy
@given(
    request_id=request_id_strategy(),
    max_retries=st.integers(min_value=1, max_value=3)
)
@settings(max_examples=50, deadline=None)
def test_backoff_calculation(request_id, max_retries):
    """
    Property: For any retry attempt, the backoff delay must follow
    exponential backoff formula: min(2^attempt, 60) seconds.
    
    This test verifies the backoff calculation is correct.
    """
    handler = ExecutionErrorHandler(max_retries=max_retries)
    
    # Test backoff for various attempt numbers
    for attempt in range(max_retries):
        backoff = handler.calculate_backoff(attempt)
        expected = min(2 ** attempt, 60)
        
        assert backoff == expected, \
            f"Backoff for attempt {attempt} should be {expected}s, got {backoff}s"
        
        # Verify backoff never exceeds 60 seconds
        assert backoff <= 60, \
            f"Backoff should never exceed 60s, got {backoff}s"
        
        # Verify backoff is positive
        assert backoff > 0, \
            f"Backoff should be positive, got {backoff}s"


# Feature: llm-python-executor, Property 24: Execution retry policy
@given(
    request_id=request_id_strategy(),
    max_retries=st.integers(min_value=1, max_value=3),
    num_failures=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=20, deadline=None)
def test_retry_wrapper_respects_max_retries(request_id, max_retries, num_failures):
    """
    Property: For any execution that raises retryable exceptions repeatedly,
    the RetryWrapper must respect the max_retries configuration and stop
    retrying after the limit is reached.
    
    This test verifies that:
    1. Retry wrapper attempts up to max_retries times for exceptions
    2. Returns failure after max retries exceeded
    3. Error history is preserved
    
    Note: This test uses mocking to avoid actual sleep delays.
    Note: The RetryWrapper only retries on exceptions, not on FAILED status results.
    """
    # Create mock executor that raises exceptions
    mock_executor = Mock(spec=SecureExecutor)
    
    # Determine how many times it should fail before succeeding
    actual_failures = min(num_failures, max_retries + 1)
    
    # Create a list of exceptions followed by success
    side_effects = []
    for i in range(actual_failures):
        side_effects.append(ResourceExhaustedError("CPU"))
    
    # Add a success result at the end (in case we don't exceed retries)
    side_effects.append(ExecutionResult(
        request_id=request_id,
        stdout="success",
        stderr="",
        exit_code=0,
        duration_ms=100,
        status=ExecutionStatus.SUCCESS
    ))
    
    # Configure mock to return results in sequence
    mock_executor.execute.side_effect = side_effects
    
    # Create retry wrapper and mock time.sleep to avoid delays
    wrapper = RetryWrapper(mock_executor, max_retries=max_retries)
    
    # Mock time.sleep to avoid actual delays
    import unittest.mock
    with unittest.mock.patch('time.sleep'):
        # Execute with retry
        result = wrapper.execute_with_retry("test code", request_id, timeout=5)
    
    # Verify result
    if num_failures <= max_retries:
        # Should eventually succeed
        assert result.status == ExecutionStatus.SUCCESS, \
            f"Should succeed after {num_failures} failures with max_retries={max_retries}"
        
        # Verify correct number of attempts
        assert mock_executor.execute.call_count == num_failures + 1, \
            f"Should attempt {num_failures + 1} times"
    else:
        # Should fail after max retries
        assert result.status == ExecutionStatus.FAILED, \
            f"Should fail after max_retries={max_retries} with {num_failures} failures"
        
        # Verify we attempted max_retries + 1 times (initial + retries)
        assert mock_executor.execute.call_count == max_retries + 1, \
            f"Should attempt {max_retries + 1} times"
        
        # Verify error history is in stderr
        assert "multiple attempts" in result.stderr.lower(), \
            "Stderr should mention multiple attempts"


# ============================================================================
# Property 25: Timeout errors are not retried
# Validates: Requirements 9.4
# ============================================================================

# Feature: llm-python-executor, Property 25: Timeout errors are not retried
@given(
    timeout=st.integers(min_value=1, max_value=60),
    request_id=request_id_strategy(),
    attempt=st.integers(min_value=0, max_value=5)
)
@settings(max_examples=100, deadline=None)
def test_timeout_errors_not_retried(timeout, request_id, attempt):
    """
    Property: For any code execution that fails with a timeout error,
    the system must not automatically retry and must return the timeout
    error to the caller.
    
    This test verifies that:
    1. Timeout errors are classified as non-retryable
    2. Handler returns failed status immediately
    3. No backoff delay is calculated
    4. Error is returned to caller
    """
    handler = ExecutionErrorHandler(max_retries=3)
    
    # Create timeout error
    error = ExecutionTimeoutError(timeout)
    
    # Verify timeout error is not retryable
    assert not handler.is_retryable(error), \
        "Timeout errors should not be retryable"
    
    # Handle the error
    result = handler.handle_error(error, request_id, attempt)
    
    # Verify immediate failure (no retry)
    assert result["status"] == "failed", \
        "Timeout errors should result in immediate failure"
    
    assert result["retryable"] is False, \
        "Timeout errors should have retryable=False"
    
    # Verify no backoff delay
    assert "backoff_delay" not in result, \
        "Non-retryable errors should not have backoff delay"
    
    # Verify error information is preserved
    assert "error" in result, \
        "Error message should be included"
    assert str(timeout) in result["error"], \
        f"Error should mention timeout value {timeout}"
    
    assert result["error_type"] == "TimeoutError", \
        f"Error type should be TimeoutError, got {result['error_type']}"


# Feature: llm-python-executor, Property 25: Timeout errors are not retried
@given(
    request_id=request_id_strategy(),
    timeout=st.integers(min_value=1, max_value=10)
)
@settings(max_examples=50, deadline=None)
def test_retry_wrapper_does_not_retry_timeout(request_id, timeout):
    """
    Property: For any execution that times out, the RetryWrapper must
    return the timeout result immediately without retrying.
    
    This test verifies that timeout results are returned immediately.
    """
    # Create mock executor that returns timeout
    mock_executor = Mock(spec=SecureExecutor)
    mock_executor.execute.return_value = ExecutionResult(
        request_id=request_id,
        stdout="",
        stderr=f"Execution timed out after {timeout} seconds",
        exit_code=-1,
        duration_ms=timeout * 1000,
        status=ExecutionStatus.TIMEOUT
    )
    
    # Create retry wrapper
    wrapper = RetryWrapper(mock_executor, max_retries=3)
    
    # Execute with retry
    result = wrapper.execute_with_retry("test code", request_id, timeout=timeout)
    
    # Verify timeout status is returned
    assert result.status == ExecutionStatus.TIMEOUT, \
        "Timeout status should be returned immediately"
    
    # Verify executor was called only once (no retries)
    assert mock_executor.execute.call_count == 1, \
        "Timeout should not trigger retries"
    
    # Verify timeout information is preserved
    assert result.exit_code == -1, \
        "Timeout should have exit code -1"
    assert "timed out" in result.stderr.lower(), \
        "Stderr should mention timeout"


# Feature: llm-python-executor, Property 25: Timeout errors are not retried
@given(
    error=non_retryable_error_strategy(),
    request_id=request_id_strategy()
)
@settings(max_examples=100, deadline=None)
def test_non_retryable_errors_not_retried(error, request_id):
    """
    Property: For any non-retryable error (timeout, memory, network),
    the system must not retry and must return the error immediately.
    
    This test verifies all non-retryable error types.
    """
    handler = ExecutionErrorHandler(max_retries=3)
    
    # Verify error is not retryable
    assert not handler.is_retryable(error), \
        f"Error {type(error).__name__} should not be retryable"
    
    # Handle the error
    result = handler.handle_error(error, request_id, attempt=0)
    
    # Verify immediate failure
    assert result["status"] == "failed", \
        f"Non-retryable error {type(error).__name__} should fail immediately"
    
    assert result["retryable"] is False, \
        "Non-retryable errors should have retryable=False"
    
    # Verify no backoff delay
    assert "backoff_delay" not in result, \
        "Non-retryable errors should not have backoff delay"


# ============================================================================
# Property 26: Max retries returns failure
# Validates: Requirements 9.5
# ============================================================================

# Feature: llm-python-executor, Property 26: Max retries returns failure
@given(
    request_id=request_id_strategy(),
    max_retries=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=20, deadline=None)
def test_max_retries_returns_failure(request_id, max_retries):
    """
    Property: For any execution that raises exceptions and exhausts all retry
    attempts, the system must return a failure response containing detailed
    error information from all attempts.
    
    This test verifies that:
    1. Failure is returned after max retries
    2. Error history from all attempts is included
    3. Detailed error information is preserved
    4. Status is FAILED
    
    Note: This test uses mocking to avoid actual sleep delays.
    Note: The RetryWrapper only retries on exceptions, not on FAILED status results.
    """
    # Create mock executor that always raises exceptions
    mock_executor = Mock(spec=SecureExecutor)
    
    # Create enough exceptions to exceed max retries
    exceptions = []
    for i in range(max_retries + 2):
        exceptions.append(ResourceExhaustedError("CPU"))
    
    mock_executor.execute.side_effect = exceptions
    
    # Create retry wrapper
    wrapper = RetryWrapper(mock_executor, max_retries=max_retries)
    
    # Mock time.sleep to avoid actual delays
    import unittest.mock
    with unittest.mock.patch('time.sleep'):
        # Execute with retry
        result = wrapper.execute_with_retry("test code", request_id, timeout=5)
    
    # Verify failure status
    assert result.status == ExecutionStatus.FAILED, \
        "Should return FAILED status after max retries exhausted"
    
    # Verify exit code indicates failure
    assert result.exit_code == -1, \
        "Failed execution should have exit code -1"
    
    # Verify error history is in stderr
    assert "multiple attempts" in result.stderr.lower(), \
        "Stderr should mention multiple attempts"
    
    # Verify all attempts are documented
    for i in range(1, max_retries + 2):
        assert f"Attempt {i}" in result.stderr, \
            f"Stderr should document attempt {i}"
    
    # Verify request_id is preserved
    assert result.request_id == request_id, \
        "Request ID should be preserved"
    
    # Verify correct number of attempts (initial + retries)
    assert mock_executor.execute.call_count == max_retries + 1, \
        f"Should attempt {max_retries + 1} times (initial + {max_retries} retries)"


# Feature: llm-python-executor, Property 26: Max retries returns failure
@given(
    request_id=request_id_strategy(),
    max_retries=st.integers(min_value=1, max_value=3),
    error=retryable_error_strategy()
)
@settings(max_examples=20, deadline=None)
def test_max_retries_with_exceptions(request_id, max_retries, error):
    """
    Property: For any execution that raises retryable exceptions and
    exhausts all retry attempts, the system must return a failure response
    with detailed error information.
    
    This test verifies exception handling during retries.
    Note: This test uses mocking to avoid actual sleep delays.
    """
    # Create mock executor that always raises the error
    mock_executor = Mock(spec=SecureExecutor)
    mock_executor.execute.side_effect = error
    
    # Create retry wrapper
    wrapper = RetryWrapper(mock_executor, max_retries=max_retries)
    
    # Mock time.sleep to avoid actual delays
    import unittest.mock
    with unittest.mock.patch('time.sleep'):
        # Execute with retry
        result = wrapper.execute_with_retry("test code", request_id, timeout=5)
    
    # Verify failure status
    assert result.status == ExecutionStatus.FAILED, \
        "Should return FAILED status after max retries exhausted"
    
    # Verify error information is in stderr
    assert len(result.stderr) > 0, \
        "Stderr should contain error information"
    
    assert "multiple attempts" in result.stderr.lower(), \
        "Stderr should mention multiple attempts"
    
    # Verify error type is documented
    assert type(error).__name__ in result.stderr, \
        f"Stderr should mention error type {type(error).__name__}"
    
    # Verify correct number of attempts
    assert mock_executor.execute.call_count == max_retries + 1, \
        f"Should attempt {max_retries + 1} times"


# Feature: llm-python-executor, Property 26: Max retries returns failure
@given(
    request_id=request_id_strategy(),
    max_retries=st.integers(min_value=2, max_value=4),
    success_on_attempt=st.integers(min_value=1, max_value=3)
)
@settings(max_examples=20, deadline=None)
def test_success_before_max_retries(request_id, max_retries, success_on_attempt):
    """
    Property: For any execution that succeeds before exhausting max retries,
    the system must return the successful result.
    
    This test verifies that retry stops on success.
    Note: This test uses mocking to avoid actual sleep delays.
    Note: The RetryWrapper only retries on exceptions, not on FAILED status results.
    """
    # Only test cases where success happens before max retries
    if success_on_attempt > max_retries:
        success_on_attempt = max_retries
    
    # Create mock executor that raises exceptions then succeeds
    mock_executor = Mock(spec=SecureExecutor)
    
    side_effects = []
    # Add exceptions
    for i in range(success_on_attempt):
        side_effects.append(ResourceExhaustedError("CPU"))
    
    # Add success
    side_effects.append(ExecutionResult(
        request_id=request_id,
        stdout="success",
        stderr="",
        exit_code=0,
        duration_ms=100,
        status=ExecutionStatus.SUCCESS
    ))
    
    mock_executor.execute.side_effect = side_effects
    
    # Create retry wrapper
    wrapper = RetryWrapper(mock_executor, max_retries=max_retries)
    
    # Mock time.sleep to avoid actual delays
    import unittest.mock
    with unittest.mock.patch('time.sleep'):
        # Execute with retry
        result = wrapper.execute_with_retry("test code", request_id, timeout=5)
    
    # Verify success
    assert result.status == ExecutionStatus.SUCCESS, \
        f"Should succeed on attempt {success_on_attempt + 1}"
    
    # Verify correct number of attempts
    assert mock_executor.execute.call_count == success_on_attempt + 1, \
        f"Should attempt {success_on_attempt + 1} times"
    
    # Verify success output
    assert result.stdout == "success", \
        "Should return success output"
    assert result.exit_code == 0, \
        "Should have exit code 0"
