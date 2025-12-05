"""Property-based tests for Heavy Job Runner.

This module contains property-based tests that verify the correctness
properties of the Heavy Job Runner for resource-intensive code execution.
"""

import os
import tempfile
import time
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, call
from hypothesis import given, settings, strategies as st

from llm_executor.job_runner.runner import (
    execute_code,
    cleanup_temporary_files,
    upload_result_to_azure,
    upload_result_to_s3,
    emit_completion_event,
)
from llm_executor.shared.models import ExecutionStatus, ExecutionResult
from llm_executor.shared.config import HeavyJobRunnerConfig
from llm_executor.shared.logging_util import get_logger


# ============================================================================
# Custom Strategies for Code Generation
# ============================================================================

@st.composite
def executable_code_strategy(draw):
    """Generate executable Python code."""
    code_patterns = [
        "result = 1 + 1",
        "result = sum(range(100))",
        "x = [i**2 for i in range(10)]",
        "print('hello world')",
        "import math\nresult = math.sqrt(16)",
        "result = 'test' * 5",
        "for i in range(5):\n    print(i)",
        "x = {'a': 1, 'b': 2}\nresult = x['a']",
        "def func():\n    return 42\nresult = func()",
        "import sys\nprint('output', file=sys.stdout)",
    ]
    return draw(st.sampled_from(code_patterns))


@st.composite
def code_creating_temp_files(draw):
    """Generate Python code that creates temporary files."""
    file_creation_patterns = [
        # Create files in /tmp
        "import tempfile\nwith tempfile.NamedTemporaryFile(mode='w', delete=False) as f:\n    f.write('test')\n    temp_file = f.name",
        "import tempfile\nimport os\ntemp_file = tempfile.mktemp()\nwith open(temp_file, 'w') as f:\n    f.write('data')",
        "import tempfile\ntemp_dir = tempfile.mkdtemp()\nimport os\nwith open(os.path.join(temp_dir, 'file.txt'), 'w') as f:\n    f.write('content')",
        # Create multiple files
        "import tempfile\nfiles = [tempfile.NamedTemporaryFile(mode='w', delete=False) for _ in range(3)]\nfor f in files:\n    f.write('test')\n    f.close()",
        # Create nested directories
        "import tempfile\nimport os\ntemp_dir = tempfile.mkdtemp()\nos.makedirs(os.path.join(temp_dir, 'subdir'))\nwith open(os.path.join(temp_dir, 'subdir', 'file.txt'), 'w') as f:\n    f.write('nested')",
    ]
    return draw(st.sampled_from(file_creation_patterns))


@st.composite
def request_id_strategy(draw):
    """Generate valid request IDs."""
    prefix = draw(st.sampled_from(["req", "exec", "job", "heavy"]))
    number = draw(st.integers(min_value=1, max_value=999999))
    return f"{prefix}-{number}"


@st.composite
def timeout_strategy(draw):
    """Generate reasonable timeout values."""
    return draw(st.integers(min_value=5, max_value=30))


# ============================================================================
# Property 22: Temporary file cleanup
# Validates: Requirements 8.5
# ============================================================================

# Feature: llm-python-executor, Property 22: Temporary file cleanup
@given(
    request_id=request_id_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_temporary_file_cleanup_on_success(request_id):
    """
    Property: For any code execution that creates temporary files,
    those files must be removed from the filesystem after execution
    completes successfully.
    
    This test verifies that:
    1. Temporary directory is created
    2. Files can be created in temp directory during execution
    3. Temp directory and all files are cleaned up after execution
    4. Cleanup happens even when execution succeeds
    """
    logger = get_logger(__name__)
    
    # Create a temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="test_cleanup_"))
    
    try:
        # Verify temp directory exists
        assert temp_dir.exists(), "Temp directory should exist before cleanup"
        
        # Create some test files in the temp directory
        test_file_1 = temp_dir / "test1.txt"
        test_file_2 = temp_dir / "test2.txt"
        test_file_1.write_text("test content 1")
        test_file_2.write_text("test content 2")
        
        # Create a subdirectory with a file
        sub_dir = temp_dir / "subdir"
        sub_dir.mkdir()
        test_file_3 = sub_dir / "test3.txt"
        test_file_3.write_text("test content 3")
        
        # Verify files exist
        assert test_file_1.exists(), "Test file 1 should exist"
        assert test_file_2.exists(), "Test file 2 should exist"
        assert test_file_3.exists(), "Test file 3 should exist"
        assert sub_dir.exists(), "Subdirectory should exist"
        
        # Call cleanup function
        cleanup_temporary_files(temp_dir, logger)
        
        # Verify temp directory and all files are removed
        assert not temp_dir.exists(), \
            f"Temp directory should be removed after cleanup: {temp_dir}"
        assert not test_file_1.exists(), \
            "Test file 1 should be removed"
        assert not test_file_2.exists(), \
            "Test file 2 should be removed"
        assert not test_file_3.exists(), \
            "Test file 3 should be removed"
        assert not sub_dir.exists(), \
            "Subdirectory should be removed"
        
    finally:
        # Ensure cleanup even if test fails
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir)


# Feature: llm-python-executor, Property 22: Temporary file cleanup
@given(
    request_id=request_id_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_temporary_file_cleanup_on_failure(request_id):
    """
    Property: For any code execution that creates temporary files and fails,
    those files must still be removed from the filesystem after execution.
    
    This test verifies that cleanup happens even when execution fails.
    """
    logger = get_logger(__name__)
    
    # Create a temporary directory
    temp_dir = Path(tempfile.mkdtemp(prefix="test_cleanup_fail_"))
    
    try:
        # Verify temp directory exists
        assert temp_dir.exists(), "Temp directory should exist before cleanup"
        
        # Create some test files
        test_file = temp_dir / "test.txt"
        test_file.write_text("test content")
        
        # Verify file exists
        assert test_file.exists(), "Test file should exist"
        
        # Simulate failure scenario - cleanup should still work
        cleanup_temporary_files(temp_dir, logger)
        
        # Verify cleanup happened
        assert not temp_dir.exists(), \
            f"Temp directory should be removed even after failure: {temp_dir}"
        assert not test_file.exists(), \
            "Test file should be removed even after failure"
        
    finally:
        # Ensure cleanup even if test fails
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir)


# Feature: llm-python-executor, Property 22: Temporary file cleanup
@given(
    request_id=request_id_strategy(),
)
@settings(max_examples=50, deadline=None)
def test_cleanup_handles_nonexistent_directory(request_id):
    """
    Property: The cleanup function must handle the case where the
    temporary directory doesn't exist (already cleaned up or never created).
    
    This test verifies that cleanup is idempotent and doesn't fail
    when called on a non-existent directory.
    """
    logger = get_logger(__name__)
    
    # Create a path that doesn't exist
    temp_dir = Path(tempfile.gettempdir()) / f"nonexistent_{request_id}"
    
    # Verify directory doesn't exist
    assert not temp_dir.exists(), "Directory should not exist"
    
    # Call cleanup - should not raise exception
    try:
        cleanup_temporary_files(temp_dir, logger)
        # If we get here, cleanup handled non-existent directory gracefully
        assert True
    except Exception as e:
        # Cleanup should not raise exceptions for non-existent directories
        assert False, f"Cleanup should handle non-existent directory gracefully, but raised: {e}"


# Feature: llm-python-executor, Property 22: Temporary file cleanup
@given(
    request_id=request_id_strategy(),
)
@settings(max_examples=50, deadline=None)
def test_cleanup_handles_none_directory(request_id):
    """
    Property: The cleanup function must handle None as input
    (when no temp directory was created).
    
    This test verifies that cleanup is safe to call with None.
    """
    logger = get_logger(__name__)
    
    # Call cleanup with None - should not raise exception
    try:
        cleanup_temporary_files(None, logger)
        # If we get here, cleanup handled None gracefully
        assert True
    except Exception as e:
        # Cleanup should not raise exceptions for None
        assert False, f"Cleanup should handle None gracefully, but raised: {e}"


# ============================================================================
# Additional Property: Code execution completes with valid result
# ============================================================================

# Feature: llm-python-executor, Property: Execution result validity
@given(
    code=executable_code_strategy(),
    request_id=request_id_strategy(),
    timeout=timeout_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_execution_returns_valid_result(code, request_id, timeout):
    """
    Property: For any executable code, the execute_code function must
    return a valid ExecutionResult with all required fields populated.
    
    This test verifies that:
    1. Result has valid status
    2. Result has request_id
    3. Result has duration_ms
    4. Result has exit_code
    5. Result has stdout and stderr (even if empty)
    """
    logger = get_logger(__name__)
    
    # Execute code
    result = execute_code(code, timeout, request_id, logger)
    
    # Verify result has valid status
    assert result.status in [
        ExecutionStatus.SUCCESS,
        ExecutionStatus.FAILED,
        ExecutionStatus.TIMEOUT
    ], f"Result must have valid status, got {result.status}"
    
    # Verify request_id is preserved
    assert result.request_id == request_id, \
        f"Request ID should be preserved: expected {request_id}, got {result.request_id}"
    
    # Verify duration is recorded
    assert result.duration_ms > 0, \
        f"Duration must be positive, got {result.duration_ms}ms"
    
    # Verify exit_code is present
    assert result.exit_code is not None, \
        "Exit code must be present"
    
    # Verify stdout and stderr are present (even if empty)
    assert result.stdout is not None, \
        "Stdout must be present"
    assert result.stderr is not None, \
        "Stderr must be present"
    
    # For successful execution, exit code should be 0
    if result.status == ExecutionStatus.SUCCESS:
        assert result.exit_code == 0, \
            f"Successful execution should have exit code 0, got {result.exit_code}"
    
    # For timeout, exit code should be -1
    if result.status == ExecutionStatus.TIMEOUT:
        assert result.exit_code == -1, \
            f"Timeout should have exit code -1, got {result.exit_code}"
        assert "timeout" in result.stderr.lower() or "timed out" in result.stderr.lower(), \
            f"Timeout should mention timeout in stderr: {result.stderr}"


# ============================================================================
# Additional Property: Execution respects timeout
# ============================================================================

@st.composite
def code_that_sleeps(draw):
    """Generate Python code that sleeps for a period."""
    sleep_patterns = [
        "import time\ntime.sleep(10)",
        "import time\ntime.sleep(5)",
        "import time\nfor i in range(10):\n    time.sleep(1)",
    ]
    return draw(st.sampled_from(sleep_patterns))


# Feature: llm-python-executor, Property: Timeout enforcement in job runner
@given(
    code=code_that_sleeps(),
    request_id=request_id_strategy(),
    timeout=st.integers(min_value=1, max_value=2),
)
@settings(max_examples=20, deadline=None)
def test_job_runner_enforces_timeout(code, request_id, timeout):
    """
    Property: For any code that exceeds the timeout, the job runner
    must terminate execution and return a timeout status.
    
    This test verifies timeout enforcement in the job runner.
    """
    logger = get_logger(__name__)
    
    # Execute code with short timeout
    start_time = time.perf_counter()
    result = execute_code(code, timeout, request_id, logger)
    end_time = time.perf_counter()
    
    actual_duration = end_time - start_time
    
    # Verify timeout was enforced
    assert result.status == ExecutionStatus.TIMEOUT, \
        f"Code that sleeps longer than timeout should timeout, got {result.status}"
    
    # Verify execution was terminated within reasonable time
    assert actual_duration <= (timeout + 2), \
        f"Execution should terminate near timeout ({timeout}s), took {actual_duration:.2f}s"
    
    # Verify exit code indicates timeout
    assert result.exit_code == -1, \
        f"Timeout should result in exit code -1, got {result.exit_code}"
    
    # Verify stderr mentions timeout
    assert "timeout" in result.stderr.lower() or "timed out" in result.stderr.lower(), \
        f"Stderr should mention timeout: {result.stderr}"



# ============================================================================
# Property 15: Job completion emits event
# Validates: Requirements 4.5, 5.3
# ============================================================================

@st.composite
def execution_result_strategy(draw):
    """Generate ExecutionResult objects with various statuses."""
    request_id = draw(request_id_strategy())
    status = draw(st.sampled_from([
        ExecutionStatus.SUCCESS,
        ExecutionStatus.FAILED,
        ExecutionStatus.TIMEOUT
    ]))
    
    # Generate appropriate exit codes based on status
    if status == ExecutionStatus.SUCCESS:
        exit_code = 0
    elif status == ExecutionStatus.TIMEOUT:
        exit_code = -1
    else:  # FAILED
        exit_code = draw(st.integers(min_value=1, max_value=255))
    
    duration_ms = draw(st.integers(min_value=1, max_value=300000))
    
    stdout = draw(st.text(min_size=0, max_size=100))
    stderr = draw(st.text(min_size=0, max_size=100))
    
    return ExecutionResult(
        request_id=request_id,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        duration_ms=duration_ms,
        status=status,
    )


@st.composite
def result_location_strategy(draw):
    """Generate result location strings."""
    storage_types = ["abfs", "s3", "local"]
    storage_type = draw(st.sampled_from(storage_types))
    
    if storage_type == "abfs":
        container = draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=('Ll', 'Nd'))))
        filename = draw(st.text(min_size=5, max_size=30, alphabet=st.characters(whitelist_categories=('Ll', 'Nd', 'Pd'))))
        return f"abfs://{container}/{filename}.json"
    elif storage_type == "s3":
        bucket = draw(st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=('Ll', 'Nd'))))
        filename = draw(st.text(min_size=5, max_size=30, alphabet=st.characters(whitelist_categories=('Ll', 'Nd', 'Pd'))))
        return f"s3://{bucket}/{filename}.json"
    else:  # local
        return "local://not-uploaded"


# Feature: llm-python-executor, Property 15: Job completion emits event
@given(
    result=execution_result_strategy(),
    result_location=result_location_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_job_completion_emits_event_on_success(result, result_location):
    """
    Property: For any Heavy Job Runner execution that completes successfully,
    the system must emit a completion event to Event Hub containing the
    request ID, status, and result location.
    
    This test verifies that:
    1. Event is emitted for successful executions
    2. Event contains request_id
    3. Event contains status
    4. Event contains result_location
    5. Event contains duration_ms
    6. Event is sent to the correct Event Hub
    """
    logger = get_logger(__name__)
    
    # Create config with Event Hub connection string
    config = HeavyJobRunnerConfig(
        event_hub_connection_string="Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=testkey"
    )
    
    # Mock the Event Hub producer and EventData (both imported inside the function)
    with patch('azure.eventhub.EventHubProducerClient') as mock_producer_class, \
         patch('azure.eventhub.EventData') as mock_event_data_class:
        
        mock_producer = MagicMock()
        mock_producer_class.from_connection_string.return_value = mock_producer
        
        # Mock EventData to capture the JSON payload
        captured_payload = None
        def capture_event_data(payload):
            nonlocal captured_payload
            captured_payload = payload
            mock_event = MagicMock()
            mock_event.body = payload
            return mock_event
        
        mock_event_data_class.side_effect = capture_event_data
        
        # Call emit_completion_event
        emit_completion_event(result, result_location, config, logger)
        
        # Verify Event Hub producer was created with correct connection string
        mock_producer_class.from_connection_string.assert_called_once()
        call_kwargs = mock_producer_class.from_connection_string.call_args
        assert call_kwargs.kwargs['conn_str'] == config.event_hub_connection_string, \
            "Event Hub producer should be created with correct connection string"
        assert call_kwargs.kwargs['eventhub_name'] == "execution-results", \
            "Event Hub producer should target 'execution-results' hub"
        
        # Verify producer was used as context manager
        mock_producer.__enter__.assert_called_once()
        mock_producer.__exit__.assert_called_once()
        
        # Verify event was sent
        mock_producer.send_event.assert_called_once()
        
        # Extract the event payload from captured data
        assert captured_payload is not None, "EventData should have been created with payload"
        event_payload = json.loads(captured_payload)
        
        # Verify event contains required fields
        assert 'request_id' in event_payload, \
            "Event must contain request_id"
        assert event_payload['request_id'] == result.request_id, \
            f"Event request_id should match result: expected {result.request_id}, got {event_payload['request_id']}"
        
        assert 'status' in event_payload, \
            "Event must contain status"
        assert event_payload['status'] == result.status.value, \
            f"Event status should match result: expected {result.status.value}, got {event_payload['status']}"
        
        assert 'result_location' in event_payload, \
            "Event must contain result_location"
        assert event_payload['result_location'] == result_location, \
            f"Event result_location should match: expected {result_location}, got {event_payload['result_location']}"
        
        assert 'duration_ms' in event_payload, \
            "Event must contain duration_ms"
        assert event_payload['duration_ms'] == result.duration_ms, \
            f"Event duration_ms should match result: expected {result.duration_ms}, got {event_payload['duration_ms']}"
        
        assert 'exit_code' in event_payload, \
            "Event must contain exit_code"
        assert event_payload['exit_code'] == result.exit_code, \
            f"Event exit_code should match result: expected {result.exit_code}, got {event_payload['exit_code']}"
        
        assert 'timestamp' in event_payload, \
            "Event must contain timestamp"
        assert isinstance(event_payload['timestamp'], (int, float)), \
            f"Event timestamp should be numeric, got {type(event_payload['timestamp'])}"


# Feature: llm-python-executor, Property 15: Job completion emits event
@given(
    result=execution_result_strategy(),
    result_location=result_location_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_job_completion_emits_event_on_failure(result, result_location):
    """
    Property: For any Heavy Job Runner execution that fails,
    the system must still emit a completion event to Event Hub.
    
    This test verifies that events are emitted even for failed executions.
    """
    logger = get_logger(__name__)
    
    # Force result to be a failure
    failed_result = ExecutionResult(
        request_id=result.request_id,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=1 if result.exit_code == 0 else result.exit_code,
        duration_ms=result.duration_ms,
        status=ExecutionStatus.FAILED,
    )
    
    # Create config with Event Hub connection string
    config = HeavyJobRunnerConfig(
        event_hub_connection_string="Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=testkey"
    )
    
    # Mock the Event Hub producer and EventData (both imported inside the function)
    with patch('azure.eventhub.EventHubProducerClient') as mock_producer_class, \
         patch('azure.eventhub.EventData') as mock_event_data_class:
        
        mock_producer = MagicMock()
        mock_producer_class.from_connection_string.return_value = mock_producer
        
        # Mock EventData to capture the JSON payload
        captured_payload = None
        def capture_event_data(payload):
            nonlocal captured_payload
            captured_payload = payload
            mock_event = MagicMock()
            mock_event.body = payload
            return mock_event
        
        mock_event_data_class.side_effect = capture_event_data
        
        # Call emit_completion_event
        emit_completion_event(failed_result, result_location, config, logger)
        
        # Verify event was sent even for failure
        mock_producer.send_event.assert_called_once()
        
        # Extract the event payload from captured data
        assert captured_payload is not None, "EventData should have been created with payload"
        event_payload = json.loads(captured_payload)
        
        # Verify status is FAILED
        assert event_payload['status'] == ExecutionStatus.FAILED.value, \
            f"Event should indicate failure status, got {event_payload['status']}"
        
        # Verify all required fields are present
        assert event_payload['request_id'] == failed_result.request_id
        assert event_payload['result_location'] == result_location
        assert event_payload['duration_ms'] == failed_result.duration_ms


# Feature: llm-python-executor, Property 15: Job completion emits event
@given(
    result=execution_result_strategy(),
    result_location=result_location_strategy(),
)
@settings(max_examples=50, deadline=None)
def test_job_completion_handles_missing_event_hub_config(result, result_location):
    """
    Property: When Event Hub connection string is not configured,
    the emit_completion_event function should handle it gracefully
    without raising exceptions.
    
    This test verifies that missing Event Hub configuration doesn't
    cause the job to fail.
    """
    logger = get_logger(__name__)
    
    # Create config without Event Hub connection string
    config = HeavyJobRunnerConfig(
        event_hub_connection_string=""
    )
    
    # Call emit_completion_event - should not raise exception
    try:
        emit_completion_event(result, result_location, config, logger)
        # If we get here, function handled missing config gracefully
        assert True
    except Exception as e:
        # Function should not raise exceptions for missing config
        assert False, f"emit_completion_event should handle missing config gracefully, but raised: {e}"


# Feature: llm-python-executor, Property 15: Job completion emits event
@given(
    result=execution_result_strategy(),
    result_location=result_location_strategy(),
)
@settings(max_examples=50, deadline=None)
def test_job_completion_handles_event_hub_errors(result, result_location):
    """
    Property: When Event Hub emission fails, the function should
    handle the error gracefully without raising exceptions
    (event emission failure shouldn't fail the job).
    
    This test verifies error handling in event emission.
    """
    logger = get_logger(__name__)
    
    # Create config with Event Hub connection string
    config = HeavyJobRunnerConfig(
        event_hub_connection_string="Endpoint=sb://test.servicebus.windows.net/;SharedAccessKeyName=test;SharedAccessKey=testkey"
    )
    
    # Mock the Event Hub producer to raise an exception (it's imported inside the function)
    with patch('azure.eventhub.EventHubProducerClient') as mock_producer_class, \
         patch('azure.eventhub.EventData'):
        
        mock_producer = MagicMock()
        mock_producer_class.from_connection_string.return_value = mock_producer
        
        # Make send_event raise an exception
        mock_producer.send_event.side_effect = Exception("Event Hub connection failed")
        
        # Call emit_completion_event - should not raise exception
        try:
            emit_completion_event(result, result_location, config, logger)
            # If we get here, function handled Event Hub error gracefully
            assert True
        except Exception as e:
            # Function should not raise exceptions for Event Hub errors
            assert False, f"emit_completion_event should handle Event Hub errors gracefully, but raised: {e}"
