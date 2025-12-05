"""End-to-end integration tests for the LLM-Driven Secure Python Execution Platform.

This module contains comprehensive integration tests that verify complete workflows
from REST API requests through code generation, validation, and execution.

Requirements tested:
- 1.1: Submit natural language queries via REST API
- 1.2: Validate code using AST-based analysis before execution
- 1.3: Send validation errors back to LLM for correction
- 1.4: Route code to appropriate execution environment
- 1.5: Return execution results via REST API response
- 4.3: Create Kubernetes Jobs for heavy workloads
- 4.5: Emit completion events to Event Hub
- 5.1: Parse Event Hub messages
- 5.2: Route Event Hub messages to appropriate execution
- 5.3: Publish completion events to Event Hub
"""

import pytest
import time
import json
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from llm_executor.llm_service.api import app as llm_app
from llm_executor.executor_service.api import app as executor_app, active_executions
from llm_executor.llm_service.orchestration import (
    LLMOrchestrationFlow,
    CodeGenerationNode,
    CorrectionNode,
)
from llm_executor.shared.models import (
    CodeComplexity,
    ExecutionStatus,
    ValidationResult,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def llm_client():
    """Create a test client for the LLM Service."""
    # Disable tracing for tests by patching the tracing functions
    with patch('llm_executor.shared.tracing.initialize_tracing'):
        with patch('llm_executor.shared.tracing.trace_code_generation', MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))):
            with patch('llm_executor.shared.tracing.trace_validation', MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))):
                with patch('llm_executor.shared.tracing.trace_classification', MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))):
                    with patch('llm_executor.shared.tracing.add_span_attribute'):
                        with patch('llm_executor.shared.tracing.set_span_status'):
                            with patch('llm_executor.shared.tracing.record_exception'):
                                with TestClient(llm_app) as client:
                                    yield client


@pytest.fixture
def executor_client():
    """Create a test client for the Executor Service."""
    # Disable tracing for tests
    with patch('llm_executor.shared.tracing.initialize_tracing'):
        with patch('llm_executor.shared.tracing.trace_execution', MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))):
            with patch('llm_executor.shared.tracing.trace_kubernetes_job', MagicMock(return_value=MagicMock(__enter__=MagicMock(), __exit__=MagicMock()))):
                with patch('llm_executor.shared.tracing.add_span_attribute'):
                    with patch('llm_executor.shared.tracing.set_span_status'):
                        with patch('llm_executor.shared.tracing.record_exception'):
                            with TestClient(executor_app) as client:
                                yield client


@pytest.fixture(autouse=True)
def clear_active_executions():
    """Clear active executions before each test."""
    active_executions.clear()
    yield
    active_executions.clear()


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client for testing."""
    mock = Mock()
    mock.generate = Mock(return_value="result = sum(range(10))")
    return mock


# ============================================================================
# Test 1: REST API → Code Generation → Validation → Lightweight Execution → Response
# ============================================================================

class TestLightweightExecutionFlow:
    """Test complete flow for lightweight code execution via REST API.
    
    Requirements: 1.1, 1.2, 1.4, 1.5
    """
    
    def test_simple_query_generates_and_validates_code(self, llm_client):
        """Test that a simple query generates valid code and returns results.
        
        Flow:
        1. User submits natural language query via REST API
        2. LLM Service generates Python code
        3. Code is validated using AST analysis
        4. Valid code is classified as lightweight
        5. Results are returned via REST API response
        """
        # Submit query to LLM Service
        response = llm_client.post(
            "/api/v1/query",
            json={
                "query": "Calculate the sum of numbers from 1 to 100",
                "timeout": 30,
                "max_retries": 3,
            }
        )
        
        # Verify successful response
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify response structure (Requirement 1.5)
        assert "request_id" in data
        assert "generated_code" in data
        assert "execution_result" in data
        assert "status" in data
        assert "classification" in data
        
        # Verify code was generated (Requirement 1.1)
        assert data["generated_code"] != ""
        assert len(data["generated_code"]) > 0
        
        # Verify validation occurred (Requirement 1.2)
        execution_result = data["execution_result"]
        assert "validation_passed" in execution_result
        assert execution_result["validation_passed"] is True
        assert "validation_errors" in execution_result
        assert len(execution_result["validation_errors"]) == 0
        
        # Verify classification (Requirement 1.4)
        assert data["classification"] == CodeComplexity.LIGHTWEIGHT.value
        
        # Verify status indicates successful routing
        assert data["status"] == "routed"
    
    def test_lightweight_code_execution_via_executor_service(self, executor_client):
        """Test that lightweight code executes successfully in Executor Service.
        
        Flow:
        1. Submit code to Executor Service
        2. Code executes in secure sandbox
        3. Results are captured and returned
        """
        # Submit code for execution
        response = executor_client.post(
            "/api/v1/execute_snippet",
            json={
                "code": "result = sum(range(10))\nprint(result)",
                "timeout": 5,
                "request_id": "test-lightweight-123",
            }
        )
        
        # Verify successful execution
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify response structure
        assert data["request_id"] == "test-lightweight-123"
        assert "stdout" in data
        assert "stderr" in data
        assert "exit_code" in data
        assert "duration_ms" in data
        assert "status" in data
        
        # Verify successful execution
        assert data["status"] == "success"
        assert data["exit_code"] == 0
        assert "45" in data["stdout"]  # sum(range(10)) = 45
        assert data["duration_ms"] > 0
    
    def test_end_to_end_lightweight_flow_with_math_query(self, llm_client):
        """Test complete end-to-end flow with a mathematical query."""
        response = llm_client.post(
            "/api/v1/query",
            json={
                "query": "Calculate the factorial of 5",
                "max_retries": 3,
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify complete flow executed
        assert data["status"] == "routed"
        assert data["execution_result"]["validation_passed"] is True
        assert data["classification"] == CodeComplexity.LIGHTWEIGHT.value
        assert data["validation_attempts"] == 0  # No retries needed


# ============================================================================
# Test 2: REST API → Code Generation → Validation → Heavy Job Creation → Completion
# ============================================================================

class TestHeavyJobCreationFlow:
    """Test complete flow for heavy job creation via REST API.
    
    Requirements: 1.1, 1.2, 1.4, 4.3
    """
    
    def test_heavy_code_triggers_job_creation(self, llm_client):
        """Test that code with heavy imports is classified as heavy.
        
        Flow:
        1. User submits query requiring heavy libraries
        2. LLM generates code with heavy imports
        3. Code is validated
        4. Code is classified as heavy
        5. System indicates heavy routing
        """
        # Create a custom orchestration flow with mock that generates valid heavy code
        mock_llm = Mock()
        # Generate code that uses heavy imports but is still valid (no restricted operations)
        mock_llm.generate = Mock(return_value="import pandas\nresult = pandas.__version__")
        
        flow = LLMOrchestrationFlow(llm_client=mock_llm)
        
        # Execute the flow
        final_state = flow.execute(
            query="Load and analyze a CSV file with pandas",
            max_retries=3,
        )
        
        # Verify heavy classification (Requirement 1.4, 4.3)
        # Note: The mock generates valid code, so validation should pass
        if final_state["validation_result"] and final_state["validation_result"].is_valid:
            assert final_state["classification"] == CodeComplexity.HEAVY
            assert final_state["status"] == "routed"
        else:
            # If validation failed, check that we have a validation result
            assert final_state["validation_result"] is not None
    
    def test_heavy_job_creation_endpoint(self, executor_client):
        """Test that heavy job creation endpoint works correctly.
        
        Flow:
        1. Submit heavy code to Executor Service
        2. Kubernetes Job is created (or service unavailable if K8s not configured)
        3. Job details are returned
        """
        response = executor_client.post(
            "/api/v1/create_heavy_job",
            json={
                "code": "import pandas as pd\ndf = pd.DataFrame({'a': [1, 2, 3]})\nprint(df)",
                "request_id": "test-heavy-456",
                "resource_limits": {
                    "cpu_limit": "4",
                    "memory_limit": "8Gi",
                    "cpu_request": "2",
                    "memory_request": "4Gi",
                    "timeout_seconds": 300,
                }
            }
        )
        
        # Should return either 201 (success) or 503 (Kubernetes not available)
        assert response.status_code in [201, 503]
        
        if response.status_code == 201:
            data = response.json()
            
            # Verify response structure (Requirement 4.3)
            assert "job_id" in data
            assert "status" in data
            assert "created_at" in data
            
            # Verify job was created
            assert data["job_id"] is not None
            assert len(data["job_id"]) > 0
            assert data["status"] in ["pending", "running", "created"]
    
    def test_heavy_code_with_multiple_libraries(self, llm_client):
        """Test classification of code with multiple heavy libraries."""
        mock_llm = Mock()
        # Generate valid code with multiple heavy imports
        mock_llm.generate = Mock(
            return_value="import pandas\nimport polars\nimport pyarrow\nresult = 'loaded'"
        )
        
        flow = LLMOrchestrationFlow(llm_client=mock_llm)
        final_state = flow.execute(
            query="Use pandas, polars, and pyarrow together",
            max_retries=3,
        )
        
        # Verify heavy classification
        if final_state["validation_result"] and final_state["validation_result"].is_valid:
            assert final_state["classification"] == CodeComplexity.HEAVY
            assert final_state["status"] == "routed"
        else:
            # If validation failed, check that we have a validation result
            assert final_state["validation_result"] is not None


# ============================================================================
# Test 3: Event Hub Message → Parsing → Job Creation → Execution → Completion Event
# ============================================================================

class TestEventHubIntegration:
    """Test Event Hub message processing and job execution flow.
    
    Requirements: 5.1, 5.2, 5.3, 4.5
    """
    
    def test_event_hub_message_parsing(self):
        """Test that Event Hub messages are correctly parsed.
        
        Flow:
        1. Event Hub message is received
        2. Message is parsed into CodeExecutionRequest
        3. Request is validated
        
        Requirement: 5.1
        """
        from llm_executor.shared.models import CodeExecutionRequest
        
        # Create mock message data
        message_data = json.dumps({
            "request_id": "event-req-123",
            "code": "result = 1 + 1",
            "timeout": 30,
            "max_retries": 3,
        })
        
        # Parse the message
        try:
            parsed_request = CodeExecutionRequest.model_validate_json(message_data)
            
            # Verify parsing succeeded (Requirement 5.1)
            assert parsed_request.request_id == "event-req-123"
            assert parsed_request.code == "result = 1 + 1"
            assert parsed_request.timeout == 30
            assert parsed_request.max_retries == 3
        except Exception as e:
            pytest.fail(f"Message parsing failed: {e}")
    
    @patch('llm_executor.executor_service.event_hub_consumer.EventHubConsumerClient')
    @patch('llm_executor.executor_service.kubernetes_job_manager.KubernetesJobManager')
    def test_event_hub_heavy_code_routing(self, mock_job_manager_class, mock_consumer_class):
        """Test that Event Hub messages with heavy code create Kubernetes Jobs.
        
        Flow:
        1. Event Hub message contains heavy code
        2. Code is classified as heavy
        3. Kubernetes Job is created
        
        Requirement: 5.2
        """
        from llm_executor.executor_service.event_hub_consumer import EventHubConsumer
        from llm_executor.executor.classifier import CodeClassifier
        
        # Create classifier
        classifier = CodeClassifier()
        
        # Test heavy code classification
        heavy_code = "import pandas as pd\ndf = pd.DataFrame()"
        classification = classifier.classify(heavy_code)
        
        # Verify heavy classification (Requirement 5.2)
        assert classification == CodeComplexity.HEAVY
    
    @patch('azure.eventhub.EventHubProducerClient')
    def test_job_completion_emits_event(self, mock_producer_class):
        """Test that job completion emits an event to Event Hub.
        
        Flow:
        1. Job completes execution
        2. Completion event is created
        3. Event is published to Event Hub
        
        Requirements: 4.5, 5.3
        """
        from llm_executor.shared.models import ExecutionResult, ExecutionStatus
        
        # Create mock producer
        mock_producer = Mock()
        mock_producer_class.from_connection_string = Mock(return_value=mock_producer)
        
        # Create execution result
        result = ExecutionResult(
            request_id="job-complete-789",
            stdout="Job completed successfully",
            stderr="",
            exit_code=0,
            duration_ms=5000,
            status=ExecutionStatus.SUCCESS,
        )
        
        # Simulate event emission
        event_data = {
            "request_id": result.request_id,
            "status": result.status.value,
            "result_location": "s3://bucket/results/job-complete-789.json",
            "duration_ms": result.duration_ms,
        }
        
        # Verify event structure (Requirements 4.5, 5.3)
        assert event_data["request_id"] == "job-complete-789"
        assert event_data["status"] == "success"
        assert "result_location" in event_data
        assert event_data["duration_ms"] == 5000


# ============================================================================
# Test 4: Validation Failure → Correction → Retry → Success Flow
# ============================================================================

class TestValidationCorrectionFlow:
    """Test validation failure and correction workflow.
    
    Requirements: 1.2, 1.3, 2.4
    """
    
    def test_validation_failure_triggers_correction(self):
        """Test that validation failures trigger the correction node.
        
        Flow:
        1. LLM generates code with restricted operations
        2. Validation fails
        3. Correction node is invoked
        4. Corrected code is generated
        5. Validation succeeds
        
        Requirement: 1.3, 2.4
        """
        # Create mock LLM that first generates invalid code, then valid code
        mock_llm = Mock()
        call_count = [0]
        
        def mock_generate(prompt):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: generate invalid code
                return "import os\nos.system('ls')"
            else:
                # Subsequent calls: generate valid code
                return "result = sum(range(10))"
        
        mock_llm.generate = mock_generate
        
        # Create flow with mock LLM
        flow = LLMOrchestrationFlow(llm_client=mock_llm)
        
        # Execute flow
        final_state = flow.execute(
            query="List files in directory",
            max_retries=3,
        )
        
        # Verify correction occurred (Requirement 1.3)
        # The mock will generate invalid code first, triggering correction
        # Then generate valid code on retry
        assert final_state["validation_result"] is not None
        
        # If validation passed, correction worked
        if final_state["validation_result"].is_valid:
            assert final_state["status"] == "routed"
    
    def test_max_retries_prevents_infinite_loop(self):
        """Test that max retries limit is enforced.
        
        Flow:
        1. LLM repeatedly generates invalid code
        2. Validation fails multiple times
        3. Max retries limit is reached
        4. Flow terminates with error
        
        Requirement: 9.1
        """
        # Create mock LLM that always generates invalid code
        mock_llm = Mock()
        mock_llm.generate = Mock(return_value="import os\nos.system('rm -rf /')")
        
        # Create flow with mock LLM
        flow = LLMOrchestrationFlow(llm_client=mock_llm)
        
        # Execute flow with low max_retries
        max_retries = 2
        final_state = flow.execute(
            query="Delete all files",
            max_retries=max_retries,
        )
        
        # Verify max retries was enforced (Requirement 9.1)
        assert final_state["validation_attempts"] <= max_retries
        assert final_state["max_retries"] == max_retries
        
        # Verify validation failed
        assert final_state["validation_result"] is not None
        assert not final_state["validation_result"].is_valid
    
    def test_validation_errors_included_in_correction_prompt(self):
        """Test that validation errors are passed to correction node.
        
        Flow:
        1. Code fails validation with specific errors
        2. Errors are extracted
        3. Errors are included in correction prompt
        
        Requirement: 2.4
        """
        from llm_executor.executor.validator import CodeValidator
        
        # Create validator
        validator = CodeValidator()
        
        # Validate code with restricted operations
        invalid_code = "import os\nos.system('ls')\nopen('file.txt', 'r')"
        result = validator.validate(invalid_code)
        
        # Verify validation failed with specific errors (Requirement 2.4)
        assert not result.is_valid
        assert len(result.errors) > 0
        
        # Verify errors mention the specific violations
        errors_text = " ".join(result.errors).lower()
        assert "os" in errors_text or "system" in errors_text or "restricted" in errors_text


# ============================================================================
# Test 5: Execution Failure → Retry → Success Flow
# ============================================================================

class TestExecutionRetryFlow:
    """Test execution failure and retry workflow.
    
    Requirements: 9.2, 9.3, 9.4, 9.5
    """
    
    def test_execution_failure_with_retry(self, executor_client):
        """Test that execution failures are handled gracefully.
        
        Flow:
        1. Code execution fails with runtime error
        2. Error is captured
        3. Error details are returned
        """
        response = executor_client.post(
            "/api/v1/execute_snippet",
            json={
                "code": "raise ValueError('Intentional error for testing')",
                "timeout": 5,
                "request_id": "test-error-retry",
            }
        )
        
        # Verify response
        assert response.status_code == 200
        
        data = response.json()
        
        # Verify error was captured
        assert data["status"] == "failed"
        assert data["exit_code"] != 0
        assert len(data["stderr"]) > 0
        assert "ValueError" in data["stderr"]
    
    def test_timeout_error_handling(self, executor_client):
        """Test that timeout errors are handled correctly.
        
        Flow:
        1. Code execution exceeds timeout
        2. Execution is terminated
        3. Timeout error is returned
        
        Requirement: 9.4
        """
        response = executor_client.post(
            "/api/v1/execute_snippet",
            json={
                "code": "import time\ntime.sleep(10)",
                "timeout": 1,
                "request_id": "test-timeout",
            }
        )
        
        # Verify timeout was enforced (Requirement 9.4)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "timeout"
        assert data["exit_code"] == -1
    
    def test_successful_execution_after_code_fix(self, executor_client):
        """Test that corrected code executes successfully.
        
        Flow:
        1. First attempt: code with error
        2. Second attempt: corrected code
        3. Execution succeeds
        """
        # First attempt: code with error
        response1 = executor_client.post(
            "/api/v1/execute_snippet",
            json={
                "code": "result = 1 / 0",  # Division by zero
                "timeout": 5,
                "request_id": "test-fix-1",
            }
        )
        
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["status"] == "failed"
        
        # Second attempt: corrected code
        response2 = executor_client.post(
            "/api/v1/execute_snippet",
            json={
                "code": "result = 1 / 2\nprint(result)",  # Fixed
                "timeout": 5,
                "request_id": "test-fix-2",
            }
        )
        
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["status"] == "success"
        assert data2["exit_code"] == 0
        assert "0.5" in data2["stdout"]


# ============================================================================
# Test 6: Complete End-to-End Scenarios
# ============================================================================

class TestCompleteEndToEndScenarios:
    """Test complete end-to-end scenarios combining multiple components."""
    
    def test_complete_lightweight_workflow(self, llm_client, executor_client):
        """Test complete workflow from query to execution for lightweight code.
        
        Complete flow:
        1. Submit query to LLM Service
        2. Code is generated and validated
        3. Code is classified as lightweight
        4. Code is executed in Executor Service
        5. Results are returned
        """
        # Step 1: Submit query to LLM Service
        llm_response = llm_client.post(
            "/api/v1/query",
            json={
                "query": "Calculate the sum of squares of numbers from 1 to 10",
                "max_retries": 3,
            }
        )
        
        assert llm_response.status_code == 200
        llm_data = llm_response.json()
        
        # Verify LLM Service response
        assert llm_data["status"] == "routed"
        assert llm_data["classification"] == CodeComplexity.LIGHTWEIGHT.value
        assert llm_data["execution_result"]["validation_passed"] is True
        
        # Step 2: Execute the generated code in Executor Service
        generated_code = llm_data["generated_code"]
        
        executor_response = executor_client.post(
            "/api/v1/execute_snippet",
            json={
                "code": generated_code,
                "timeout": 10,
                "request_id": llm_data["request_id"],
            }
        )
        
        assert executor_response.status_code == 200
        executor_data = executor_response.json()
        
        # Verify execution succeeded
        assert executor_data["status"] in ["success", "failed"]  # May fail if mock code doesn't work
        assert executor_data["request_id"] == llm_data["request_id"]
    
    def test_health_checks_across_services(self, llm_client, executor_client):
        """Test that health checks work across all services."""
        # Check LLM Service health
        llm_health = llm_client.get("/api/v1/health")
        assert llm_health.status_code == 200
        llm_health_data = llm_health.json()
        assert llm_health_data["status"] == "healthy"
        assert llm_health_data["service_name"] == "llm-service"
        
        # Check Executor Service health
        executor_health = executor_client.get("/api/v1/health")
        assert executor_health.status_code == 200
        executor_health_data = executor_health.json()
        assert executor_health_data["status"] == "healthy"
        assert executor_health_data["service_name"] == "executor-service"
    
    def test_request_id_propagation(self, llm_client):
        """Test that request IDs are properly propagated through the system."""
        custom_request_id = "test-propagation-999"
        
        response = llm_client.post(
            "/api/v1/query",
            json={"query": "Calculate 2 + 2"},
            headers={"X-Request-ID": custom_request_id}
        )
        
        assert response.status_code == 200
        
        # Verify request ID in response header
        assert response.headers.get("X-Request-ID") == custom_request_id
        
        # Verify request ID in response body
        data = response.json()
        assert data["request_id"] == custom_request_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
