"""Unit tests for Event Hub Consumer.

This module contains unit tests for the EventHubConsumer class,
focusing on error handling and edge cases.
"""

import json
import pytest
from unittest.mock import Mock, AsyncMock, patch
from azure.eventhub import EventData

from llm_executor.executor_service.event_hub_consumer import EventHubConsumer
from llm_executor.executor_service.secure_executor import SecureExecutor
from llm_executor.executor_service.kubernetes_job_manager import KubernetesJobManager
from llm_executor.shared.models import (
    CodeExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)
from llm_executor.shared.exceptions import (
    MessageParsingError,
    ProcessingError,
)


class TestEventHubConsumer:
    """Unit tests for EventHubConsumer."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.executor = Mock(spec=SecureExecutor)
        self.job_manager = Mock(spec=KubernetesJobManager)
        
        self.consumer = EventHubConsumer(
            connection_string="mock_connection_string",
            eventhub_name="code-execution-requests",
            consumer_group="$Default",
            executor=self.executor,
            job_manager=self.job_manager,
        )
    
    def test_parse_valid_message(self):
        """Test parsing a valid Event Hub message."""
        # Create valid message
        request = CodeExecutionRequest(
            request_id="req-123",
            code="result = 1 + 1",
            timeout=30,
            max_retries=3,
        )
        
        body = json.dumps(request.model_dump())
        event = Mock(spec=EventData)
        event.body_as_str.return_value = body
        event.sequence_number = 1
        
        # Parse message
        parsed = self.consumer._parse_message(event)
        
        # Verify
        assert isinstance(parsed, CodeExecutionRequest)
        assert parsed.request_id == "req-123"
        assert parsed.code == "result = 1 + 1"
        assert parsed.timeout == 30
        assert parsed.max_retries == 3
    
    def test_parse_invalid_json(self):
        """Test parsing a message with invalid JSON."""
        # Create invalid message
        event = Mock(spec=EventData)
        event.body_as_str.return_value = "not valid json {"
        event.sequence_number = 1
        
        # Verify parsing raises MessageParsingError
        with pytest.raises(MessageParsingError) as exc_info:
            self.consumer._parse_message(event)
        
        assert "Invalid JSON" in str(exc_info.value)
    
    def test_parse_missing_required_fields(self):
        """Test parsing a message with missing required fields."""
        # Create message missing required fields
        body = json.dumps({"code": "result = 1 + 1"})  # Missing request_id
        event = Mock(spec=EventData)
        event.body_as_str.return_value = body
        event.sequence_number = 1
        
        # Verify parsing raises MessageParsingError
        with pytest.raises(MessageParsingError) as exc_info:
            self.consumer._parse_message(event)
        
        assert "Failed to parse message" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_handle_lightweight_code_success(self):
        """Test successful lightweight code execution."""
        request = CodeExecutionRequest(
            request_id="req-123",
            code="result = 1 + 1",
            timeout=30,
            max_retries=3,
        )
        
        # Mock successful execution
        mock_result = ExecutionResult(
            request_id="req-123",
            stdout="2",
            stderr="",
            exit_code=0,
            duration_ms=100,
            status=ExecutionStatus.SUCCESS,
        )
        self.executor.execute.return_value = mock_result
        
        # Handle lightweight code
        await self.consumer._handle_lightweight_code(request)
        
        # Verify executor was called
        self.executor.execute.assert_called_once()
        call_args = self.executor.execute.call_args
        assert call_args[0][0] == request.code
        assert call_args[0][1] == request.request_id
        assert call_args[0][2] == request.timeout
    
    @pytest.mark.asyncio
    async def test_handle_lightweight_code_failure(self):
        """Test lightweight code execution failure."""
        request = CodeExecutionRequest(
            request_id="req-123",
            code="result = 1 / 0",
            timeout=30,
            max_retries=3,
        )
        
        # Mock execution failure
        self.executor.execute.side_effect = Exception("Division by zero")
        
        # Verify handling raises ProcessingError
        with pytest.raises(ProcessingError) as exc_info:
            await self.consumer._handle_lightweight_code(request)
        
        assert "Code execution failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_handle_heavy_code_success(self):
        """Test successful heavy code job creation."""
        request = CodeExecutionRequest(
            request_id="req-123",
            code="import pandas as pd",
            timeout=300,
            max_retries=3,
        )
        
        # Mock successful job creation
        mock_response = Mock()
        mock_response.job_id = "job-req-123"
        mock_response.status = "created"
        mock_response.created_at = "2024-12-05T00:00:00Z"
        self.job_manager.create_job.return_value = mock_response
        
        # Handle heavy code
        await self.consumer._handle_heavy_code(request)
        
        # Verify job manager was called
        self.job_manager.create_job.assert_called_once()
        call_args = self.job_manager.create_job.call_args
        job_request = call_args[0][0]
        assert job_request.request_id == request.request_id
        assert job_request.code == request.code
    
    @pytest.mark.asyncio
    async def test_handle_heavy_code_no_job_manager(self):
        """Test heavy code handling when job manager is not available."""
        # Create consumer without job manager
        consumer = EventHubConsumer(
            connection_string="mock_connection_string",
            eventhub_name="code-execution-requests",
            consumer_group="$Default",
            executor=self.executor,
            job_manager=None,
        )
        
        request = CodeExecutionRequest(
            request_id="req-123",
            code="import pandas as pd",
            timeout=300,
            max_retries=3,
        )
        
        # Verify handling raises ProcessingError
        with pytest.raises(ProcessingError) as exc_info:
            await consumer._handle_heavy_code(request)
        
        assert "KubernetesJobManager not available" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_handle_heavy_code_job_creation_failure(self):
        """Test heavy code handling when job creation fails."""
        request = CodeExecutionRequest(
            request_id="req-123",
            code="import pandas as pd",
            timeout=300,
            max_retries=3,
        )
        
        # Mock job creation failure
        self.job_manager.create_job.side_effect = Exception("Kubernetes API error")
        
        # Verify handling raises ProcessingError
        with pytest.raises(ProcessingError) as exc_info:
            await self.consumer._handle_heavy_code(request)
        
        assert "Job creation failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_on_event_processing_failure_does_not_checkpoint(self):
        """
        Test that processing failures are logged and message is not acknowledged.
        
        Requirements: 5.4 - Log errors and allow Event Hub retry mechanisms
        
        This test verifies that when message processing fails, the checkpoint
        is not updated, allowing Event Hub to retry the message.
        """
        # Create valid message
        request = CodeExecutionRequest(
            request_id="req-123",
            code="result = 1 + 1",
            timeout=30,
            max_retries=3,
        )
        
        body = json.dumps(request.model_dump())
        event = Mock(spec=EventData)
        event.body_as_str.return_value = body
        event.sequence_number = 1
        
        # Mock partition context
        partition_context = AsyncMock()
        
        # Mock execution failure
        self.executor.execute.side_effect = Exception("Execution failed")
        
        # Process event
        await self.consumer._on_event(partition_context, event)
        
        # Verify checkpoint was NOT updated (message not acknowledged)
        partition_context.update_checkpoint.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_on_event_parsing_failure_does_not_checkpoint(self):
        """
        Test that parsing failures are logged and message is not acknowledged.
        
        Requirements: 5.4 - Log errors and allow Event Hub retry mechanisms
        
        This test verifies that when message parsing fails, the checkpoint
        is not updated, allowing Event Hub to retry the message.
        """
        # Create invalid message
        event = Mock(spec=EventData)
        event.body_as_str.return_value = "invalid json {"
        event.sequence_number = 1
        
        # Mock partition context
        partition_context = AsyncMock()
        
        # Process event
        await self.consumer._on_event(partition_context, event)
        
        # Verify checkpoint was NOT updated (message not acknowledged)
        partition_context.update_checkpoint.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_on_event_success_updates_checkpoint(self):
        """
        Test that successful processing updates checkpoint.
        
        This test verifies that when message processing succeeds, the
        checkpoint is updated to acknowledge the message.
        """
        # Create valid message
        request = CodeExecutionRequest(
            request_id="req-123",
            code="result = 1 + 1",
            timeout=30,
            max_retries=3,
        )
        
        body = json.dumps(request.model_dump())
        event = Mock(spec=EventData)
        event.body_as_str.return_value = body
        event.sequence_number = 1
        
        # Mock partition context
        partition_context = AsyncMock()
        
        # Mock successful execution
        mock_result = ExecutionResult(
            request_id="req-123",
            stdout="2",
            stderr="",
            exit_code=0,
            duration_ms=100,
            status=ExecutionStatus.SUCCESS,
        )
        self.executor.execute.return_value = mock_result
        
        # Process event
        await self.consumer._on_event(partition_context, event)
        
        # Verify checkpoint WAS updated (message acknowledged)
        partition_context.update_checkpoint.assert_called_once_with(event)
    
    @pytest.mark.asyncio
    async def test_on_error_logs_error(self):
        """Test that Event Hub errors are logged."""
        # Mock partition context
        partition_context = Mock()
        partition_context.partition_id = "0"
        
        # Create error
        error = Exception("Event Hub connection lost")
        
        # Call error handler (should not raise)
        await self.consumer._on_error(partition_context, error)
        
        # No assertion needed - just verify it doesn't raise
    
    def test_consumer_initialization(self):
        """Test EventHubConsumer initialization."""
        consumer = EventHubConsumer(
            connection_string="test_connection",
            eventhub_name="test-hub",
            consumer_group="test-group",
            executor=self.executor,
            job_manager=self.job_manager,
        )
        
        assert consumer.connection_string == "test_connection"
        assert consumer.eventhub_name == "test-hub"
        assert consumer.consumer_group == "test-group"
        assert consumer.executor == self.executor
        assert consumer.job_manager == self.job_manager
        assert consumer.classifier is not None
        assert consumer.client is None  # Not started yet
