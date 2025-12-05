"""Property-based tests for Event Hub Consumer.

This module contains property-based tests that verify the correctness
properties of the Event Hub message processing workflow.
"""

import json
import uuid
from unittest.mock import Mock, AsyncMock, MagicMock
from hypothesis import given, settings, strategies as st
from azure.eventhub import EventData

from llm_executor.executor_service.event_hub_consumer import EventHubConsumer
from llm_executor.executor_service.secure_executor import SecureExecutor
from llm_executor.executor_service.kubernetes_job_manager import KubernetesJobManager
from llm_executor.shared.models import (
    CodeExecutionRequest,
    CodeComplexity,
    ExecutionResult,
    ExecutionStatus,
)


# ============================================================================
# Custom Strategies for Event Hub Message Generation
# ============================================================================

@st.composite
def valid_code_execution_requests(draw):
    """Generate valid CodeExecutionRequest objects."""
    request_id = f"req-{uuid.uuid4()}"
    
    # Generate different types of code
    code_samples = [
        "result = 1 + 1",
        "result = sum(range(100))",
        "result = [x**2 for x in range(10)]",
        "result = {'key': 'value'}",
        "result = sorted([3, 1, 4, 1, 5, 9])",
    ]
    
    code = draw(st.sampled_from(code_samples))
    timeout = draw(st.integers(min_value=10, max_value=300))
    max_retries = draw(st.integers(min_value=1, max_value=5))
    
    return CodeExecutionRequest(
        request_id=request_id,
        code=code,
        timeout=timeout,
        max_retries=max_retries,
    )


@st.composite
def heavy_code_execution_requests(draw):
    """Generate CodeExecutionRequest objects with heavy code."""
    request_id = f"req-{uuid.uuid4()}"
    
    # Generate code with heavy imports
    heavy_libraries = ["pandas", "polars", "modin", "pyarrow", "dask"]
    library = draw(st.sampled_from(heavy_libraries))
    
    code = f"import {library}\nresult = {library}.__version__"
    timeout = draw(st.integers(min_value=10, max_value=300))
    max_retries = draw(st.integers(min_value=1, max_value=5))
    
    return CodeExecutionRequest(
        request_id=request_id,
        code=code,
        timeout=timeout,
        max_retries=max_retries,
    )


@st.composite
def lightweight_code_execution_requests(draw):
    """Generate CodeExecutionRequest objects with lightweight code."""
    request_id = f"req-{uuid.uuid4()}"
    
    # Generate simple code without heavy imports
    code_samples = [
        "result = 1 + 1",
        "result = sum(range(100))",
        "result = [x**2 for x in range(10)]",
        "result = len('hello world')",
        "result = max([1, 2, 3, 4, 5])",
    ]
    
    code = draw(st.sampled_from(code_samples))
    timeout = draw(st.integers(min_value=10, max_value=300))
    max_retries = draw(st.integers(min_value=1, max_value=5))
    
    return CodeExecutionRequest(
        request_id=request_id,
        code=code,
        timeout=timeout,
        max_retries=max_retries,
    )


@st.composite
def event_hub_messages(draw, request_strategy):
    """Generate Event Hub EventData objects from CodeExecutionRequest."""
    request = draw(request_strategy)
    
    # Convert request to JSON
    body = json.dumps(request.model_dump())
    
    # Create mock EventData
    event = Mock(spec=EventData)
    event.body_as_str.return_value = body
    event.sequence_number = draw(st.integers(min_value=1, max_value=1000000))
    
    return event, request


# ============================================================================
# Property 16: Event Hub message parsing
# Validates: Requirements 5.1
# ============================================================================

# Feature: llm-python-executor, Property 16: Event Hub message parsing
@given(event_data=event_hub_messages(valid_code_execution_requests()))
@settings(max_examples=100)
def test_event_hub_message_parsing(event_data):
    """
    Property: For any valid Event Hub message in the code-execution-requests
    format, the Executor Service must successfully parse the message and
    extract a valid CodeExecutionRequest object.
    
    This test verifies that message parsing correctly extracts and validates
    CodeExecutionRequest objects from Event Hub messages.
    """
    event, expected_request = event_data
    
    # Create mock executor and consumer
    executor = Mock(spec=SecureExecutor)
    consumer = EventHubConsumer(
        connection_string="mock_connection_string",
        eventhub_name="code-execution-requests",
        consumer_group="$Default",
        executor=executor,
        job_manager=None,
    )
    
    # Parse the message
    parsed_request = consumer._parse_message(event)
    
    # Verify parsing succeeded
    assert isinstance(parsed_request, CodeExecutionRequest), \
        "Parsed message must be a CodeExecutionRequest"
    
    # Verify all fields match
    assert parsed_request.request_id == expected_request.request_id, \
        "Request ID must match"
    assert parsed_request.code == expected_request.code, \
        "Code must match"
    assert parsed_request.timeout == expected_request.timeout, \
        "Timeout must match"
    assert parsed_request.max_retries == expected_request.max_retries, \
        "Max retries must match"


# ============================================================================
# Property 17: Event Hub heavy code routing
# Validates: Requirements 5.2
# ============================================================================

# Feature: llm-python-executor, Property 17: Event Hub heavy code routing
@given(event_data=event_hub_messages(heavy_code_execution_requests()))
@settings(max_examples=100)
def test_event_hub_heavy_code_routing(event_data):
    """
    Property: For any Event Hub message containing code classified as heavy,
    the Executor Service must create a Kubernetes Job rather than executing
    locally.
    
    This test verifies that heavy code from Event Hub messages is correctly
    routed to Kubernetes Job creation.
    """
    event, expected_request = event_data
    
    # Create mock executor and job manager
    executor = Mock(spec=SecureExecutor)
    job_manager = Mock(spec=KubernetesJobManager)
    
    # Mock job creation response
    mock_response = Mock()
    mock_response.job_id = f"job-{expected_request.request_id}"
    mock_response.status = "created"
    mock_response.created_at = "2024-12-05T00:00:00Z"
    job_manager.create_job.return_value = mock_response
    
    consumer = EventHubConsumer(
        connection_string="mock_connection_string",
        eventhub_name="code-execution-requests",
        consumer_group="$Default",
        executor=executor,
        job_manager=job_manager,
    )
    
    # Parse the message
    parsed_request = consumer._parse_message(event)
    
    # Classify the code
    complexity = consumer.classifier.classify(parsed_request.code)
    
    # Verify it's classified as heavy
    assert complexity == CodeComplexity.HEAVY, \
        f"Code with heavy imports must be classified as HEAVY, got {complexity}"
    
    # Simulate handling the message (synchronous version for testing)
    import asyncio
    try:
        asyncio.run(consumer._handle_heavy_code(parsed_request))
    except RuntimeError:
        # If event loop is already running, use sync approach
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(consumer._handle_heavy_code(parsed_request))
        finally:
            loop.close()
    
    # Verify job manager was called
    job_manager.create_job.assert_called_once()
    
    # Verify executor was NOT called (heavy code should not execute locally)
    executor.execute.assert_not_called()
    
    # Verify the job creation request
    call_args = job_manager.create_job.call_args
    job_request = call_args[0][0]
    assert job_request.request_id == parsed_request.request_id, \
        "Job request must have correct request_id"
    assert job_request.code == parsed_request.code, \
        "Job request must have correct code"


# ============================================================================
# Additional Property Tests
# ============================================================================

# Feature: llm-python-executor, Property: Lightweight code uses executor
@given(event_data=event_hub_messages(lightweight_code_execution_requests()))
@settings(max_examples=100)
def test_lightweight_code_uses_executor(event_data):
    """
    Property: For any Event Hub message containing code classified as
    lightweight, the Executor Service must execute it using SecureExecutor
    rather than creating a Kubernetes Job.
    
    This test verifies that lightweight code is correctly routed to
    local execution.
    """
    event, expected_request = event_data
    
    # Create mock executor and job manager
    executor = Mock(spec=SecureExecutor)
    
    # Mock execution result
    mock_result = ExecutionResult(
        request_id=expected_request.request_id,
        stdout="2",
        stderr="",
        exit_code=0,
        duration_ms=100,
        status=ExecutionStatus.SUCCESS,
    )
    executor.execute.return_value = mock_result
    
    job_manager = Mock(spec=KubernetesJobManager)
    
    consumer = EventHubConsumer(
        connection_string="mock_connection_string",
        eventhub_name="code-execution-requests",
        consumer_group="$Default",
        executor=executor,
        job_manager=job_manager,
    )
    
    # Parse the message
    parsed_request = consumer._parse_message(event)
    
    # Classify the code
    complexity = consumer.classifier.classify(parsed_request.code)
    
    # Verify it's classified as lightweight
    assert complexity == CodeComplexity.LIGHTWEIGHT, \
        f"Simple code must be classified as LIGHTWEIGHT, got {complexity}"
    
    # Simulate handling the message (synchronous version for testing)
    import asyncio
    try:
        asyncio.run(consumer._handle_lightweight_code(parsed_request))
    except RuntimeError:
        # If event loop is already running, use sync approach
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(consumer._handle_lightweight_code(parsed_request))
        finally:
            loop.close()
    
    # Verify executor was called
    executor.execute.assert_called_once()
    
    # Verify job manager was NOT called (lightweight code should not create jobs)
    job_manager.create_job.assert_not_called()
    
    # Verify the execution parameters
    call_args = executor.execute.call_args
    assert call_args[0][0] == parsed_request.code, \
        "Executor must receive correct code"
    assert call_args[0][1] == parsed_request.request_id, \
        "Executor must receive correct request_id"
    assert call_args[0][2] == parsed_request.timeout, \
        "Executor must receive correct timeout"


# Feature: llm-python-executor, Property: Request ID is preserved
@given(event_data=event_hub_messages(valid_code_execution_requests()))
@settings(max_examples=100)
def test_request_id_preserved_through_processing(event_data):
    """
    Property: For any Event Hub message, the request_id must be preserved
    throughout the processing pipeline.
    
    This test verifies that request_id is correctly maintained from message
    parsing through execution/job creation.
    """
    event, expected_request = event_data
    
    # Create mock executor
    executor = Mock(spec=SecureExecutor)
    mock_result = ExecutionResult(
        request_id=expected_request.request_id,
        stdout="",
        stderr="",
        exit_code=0,
        duration_ms=100,
        status=ExecutionStatus.SUCCESS,
    )
    executor.execute.return_value = mock_result
    
    consumer = EventHubConsumer(
        connection_string="mock_connection_string",
        eventhub_name="code-execution-requests",
        consumer_group="$Default",
        executor=executor,
        job_manager=None,
    )
    
    # Parse the message
    parsed_request = consumer._parse_message(event)
    
    # Verify request_id is preserved in parsing
    assert parsed_request.request_id == expected_request.request_id, \
        "Request ID must be preserved during parsing"
    
    # Simulate lightweight execution
    import asyncio
    try:
        asyncio.run(consumer._handle_lightweight_code(parsed_request))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(consumer._handle_lightweight_code(parsed_request))
        finally:
            loop.close()
    
    # Verify request_id was passed to executor
    call_args = executor.execute.call_args
    assert call_args[0][1] == expected_request.request_id, \
        "Request ID must be passed to executor"


# Feature: llm-python-executor, Property: Classification is deterministic
@given(request=valid_code_execution_requests())
@settings(max_examples=100)
def test_classification_is_deterministic(request):
    """
    Property: For any code, the classification result must be deterministic
    (same code always produces same classification).
    
    This test verifies that code classification is consistent.
    """
    executor = Mock(spec=SecureExecutor)
    consumer = EventHubConsumer(
        connection_string="mock_connection_string",
        eventhub_name="code-execution-requests",
        consumer_group="$Default",
        executor=executor,
        job_manager=None,
    )
    
    # Classify the same code multiple times
    classification1 = consumer.classifier.classify(request.code)
    classification2 = consumer.classifier.classify(request.code)
    classification3 = consumer.classifier.classify(request.code)
    
    # Verify all classifications are identical
    assert classification1 == classification2, \
        "Classification must be deterministic"
    assert classification2 == classification3, \
        "Classification must be deterministic"
    assert classification1 in [CodeComplexity.LIGHTWEIGHT, CodeComplexity.HEAVY], \
        "Classification must be either LIGHTWEIGHT or HEAVY"
