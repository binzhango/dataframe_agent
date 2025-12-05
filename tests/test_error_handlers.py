"""Unit tests for error handlers.

This module contains unit tests for the ExecutionErrorHandler, RetryWrapper,
and JobErrorHandler classes.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from kubernetes import client

from llm_executor.executor_service.error_handlers import (
    ExecutionErrorHandler,
    RetryWrapper,
    JobErrorHandler,
)
from llm_executor.executor_service.secure_executor import SecureExecutor
from llm_executor.shared.models import ExecutionResult, ExecutionStatus
from llm_executor.shared.exceptions import (
    ExecutionError,
    TimeoutError as ExecutionTimeoutError,
    ResourceExhaustedError,
)


class TestExecutionErrorHandler:
    """Tests for ExecutionErrorHandler."""
    
    def test_timeout_error_not_retryable(self):
        """Test that timeout errors are classified as non-retryable."""
        handler = ExecutionErrorHandler(max_retries=3)
        error = ExecutionTimeoutError(30)
        
        assert not handler.is_retryable(error)
    
    def test_resource_exhausted_error_retryable(self):
        """Test that resource exhausted errors are classified as retryable."""
        handler = ExecutionErrorHandler(max_retries=3)
        error = ResourceExhaustedError("CPU")
        
        assert handler.is_retryable(error)
    
    def test_backoff_calculation(self):
        """Test exponential backoff calculation."""
        handler = ExecutionErrorHandler(max_retries=5)
        
        assert handler.calculate_backoff(0) == 1
        assert handler.calculate_backoff(1) == 2
        assert handler.calculate_backoff(2) == 4
        assert handler.calculate_backoff(3) == 8
        assert handler.calculate_backoff(4) == 16
        assert handler.calculate_backoff(5) == 32
        assert handler.calculate_backoff(6) == 60  # Max cap
        assert handler.calculate_backoff(10) == 60  # Max cap
    
    def test_handle_error_max_retries_exceeded(self):
        """Test error handling when max retries are exceeded."""
        handler = ExecutionErrorHandler(max_retries=2)
        error = ResourceExhaustedError("CPU")
        
        result = handler.handle_error(error, "req-123", attempt=2)
        
        assert result["status"] == "failed"
        assert result["retryable"] is False
        assert "Maximum retry attempts exceeded" in result["reason"]
    
    def test_handle_error_retryable(self):
        """Test error handling for retryable errors."""
        handler = ExecutionErrorHandler(max_retries=3)
        error = ResourceExhaustedError("CPU")
        
        result = handler.handle_error(error, "req-123", attempt=1)
        
        assert result["status"] == "retry"
        assert result["retryable"] is True
        assert result["backoff_delay"] == 2  # 2^1


class TestRetryWrapper:
    """Tests for RetryWrapper."""
    
    def test_successful_execution_no_retry(self):
        """Test that successful execution doesn't trigger retries."""
        mock_executor = Mock(spec=SecureExecutor)
        mock_executor.execute.return_value = ExecutionResult(
            request_id="req-123",
            stdout="success",
            stderr="",
            exit_code=0,
            duration_ms=100,
            status=ExecutionStatus.SUCCESS
        )
        
        wrapper = RetryWrapper(mock_executor, max_retries=3)
        
        with patch('time.sleep'):
            result = wrapper.execute_with_retry("code", "req-123", timeout=5)
        
        assert result.status == ExecutionStatus.SUCCESS
        assert mock_executor.execute.call_count == 1
    
    def test_timeout_no_retry(self):
        """Test that timeout results are not retried."""
        mock_executor = Mock(spec=SecureExecutor)
        mock_executor.execute.return_value = ExecutionResult(
            request_id="req-123",
            stdout="",
            stderr="Execution timed out",
            exit_code=-1,
            duration_ms=5000,
            status=ExecutionStatus.TIMEOUT
        )
        
        wrapper = RetryWrapper(mock_executor, max_retries=3)
        
        with patch('time.sleep'):
            result = wrapper.execute_with_retry("code", "req-123", timeout=5)
        
        assert result.status == ExecutionStatus.TIMEOUT
        assert mock_executor.execute.call_count == 1
    
    def test_retryable_exception_triggers_retry(self):
        """Test that retryable exceptions trigger retries."""
        mock_executor = Mock(spec=SecureExecutor)
        mock_executor.execute.side_effect = [
            ResourceExhaustedError("CPU"),
            ExecutionResult(
                request_id="req-123",
                stdout="success",
                stderr="",
                exit_code=0,
                duration_ms=100,
                status=ExecutionStatus.SUCCESS
            )
        ]
        
        wrapper = RetryWrapper(mock_executor, max_retries=3)
        
        with patch('time.sleep'):
            result = wrapper.execute_with_retry("code", "req-123", timeout=5)
        
        assert result.status == ExecutionStatus.SUCCESS
        assert mock_executor.execute.call_count == 2


class TestJobErrorHandler:
    """Tests for JobErrorHandler."""
    
    def test_monitor_job_success(self):
        """Test monitoring a successful job."""
        mock_batch_api = Mock(spec=client.BatchV1Api)
        handler = JobErrorHandler(mock_batch_api, namespace="default", max_job_retries=3)
        
        # Create mock job with success status
        mock_job = Mock()
        mock_job.status.succeeded = 1
        mock_job.status.failed = None
        mock_job.status.conditions = None
        
        # Mock the watch stream
        with patch('llm_executor.executor_service.error_handlers.watch.Watch') as mock_watch:
            mock_watch_instance = Mock()
            mock_watch.return_value = mock_watch_instance
            mock_watch_instance.stream.return_value = [
                {"type": "MODIFIED", "object": mock_job}
            ]
            
            result = handler.monitor_job("test-job-123", timeout=10)
        
        assert result["status"] == "success"
        assert result["job_id"] == "test-job-123"
    
    def test_monitor_job_failure_max_retries(self):
        """Test monitoring a job that exceeds max retries.
        
        Requirements: 9.3 - Test that failed jobs trigger retry according to backoff policy
        """
        mock_batch_api = Mock(spec=client.BatchV1Api)
        handler = JobErrorHandler(mock_batch_api, namespace="default", max_job_retries=3)
        
        # Create mock job with failure status exceeding max retries
        mock_job = Mock()
        mock_job.status.succeeded = None
        mock_job.status.failed = 3  # Equals max_job_retries
        mock_job.status.conditions = [
            Mock(type="Failed", reason="BackoffLimitExceeded", message="Job has reached the specified backoff limit")
        ]
        
        # Mock the watch stream
        with patch('llm_executor.executor_service.error_handlers.watch.Watch') as mock_watch:
            mock_watch_instance = Mock()
            mock_watch.return_value = mock_watch_instance
            mock_watch_instance.stream.return_value = [
                {"type": "MODIFIED", "object": mock_job}
            ]
            
            result = handler.monitor_job("test-job-123", timeout=10)
        
        assert result["status"] == "failed"
        assert result["job_id"] == "test-job-123"
        assert result["failed_count"] == 3
        assert "Maximum retry attempts" in result["message"] or "BackoffLimitExceeded" in result["reason"]
    
    def test_emit_failure_event(self):
        """Test emitting failure events for jobs that exceed retry limits."""
        mock_batch_api = Mock(spec=client.BatchV1Api)
        handler = JobErrorHandler(mock_batch_api, namespace="default", max_job_retries=3)
        
        # This should log the failure event
        handler.emit_failure_event(
            job_id="test-job-123",
            reason="BackoffLimitExceeded",
            message="Job exceeded retry limit"
        )
        
        # No assertion needed - just verify it doesn't raise an exception
    
    def test_cleanup_job(self):
        """Test cleaning up a failed job."""
        mock_batch_api = Mock(spec=client.BatchV1Api)
        handler = JobErrorHandler(mock_batch_api, namespace="default", max_job_retries=3)
        
        result = handler.cleanup_job("test-job-123")
        
        assert result is True
        mock_batch_api.delete_namespaced_job.assert_called_once_with(
            name="test-job-123",
            namespace="default",
            propagation_policy="Background"
        )
    
    def test_monitor_job_deadline_exceeded(self):
        """Test monitoring a job that exceeds deadline."""
        mock_batch_api = Mock(spec=client.BatchV1Api)
        handler = JobErrorHandler(mock_batch_api, namespace="default", max_job_retries=3)
        
        # Create mock job with deadline exceeded condition
        mock_job = Mock()
        mock_job.status.succeeded = None
        mock_job.status.failed = 1
        mock_job.status.conditions = [
            Mock(type="Failed", reason="DeadlineExceeded", message="Job was active longer than specified deadline")
        ]
        
        # Mock the watch stream
        with patch('llm_executor.executor_service.error_handlers.watch.Watch') as mock_watch:
            mock_watch_instance = Mock()
            mock_watch.return_value = mock_watch_instance
            mock_watch_instance.stream.return_value = [
                {"type": "MODIFIED", "object": mock_job}
            ]
            
            result = handler.monitor_job("test-job-123", timeout=10)
        
        assert result["status"] == "failed"
        assert result["reason"] == "DeadlineExceeded"
