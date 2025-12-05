"""Error handling and retry logic for the Executor Service.

This module implements error handlers that categorize errors as retryable or
non-retryable, calculate exponential backoff, and manage retry policies.
"""

import time
from typing import Optional, Callable, Any
from kubernetes import client, watch
from kubernetes.client.rest import ApiException

from llm_executor.shared.models import ExecutionResult, ExecutionStatus
from llm_executor.shared.exceptions import (
    ExecutionError,
    TimeoutError as ExecutionTimeoutError,
    MemoryError as ExecutionMemoryError,
    NetworkError,
    ResourceExhaustedError,
    JobError,
    PodFailureError,
    ImagePullError,
    DeadlineExceededError,
)
from llm_executor.shared.logging_util import get_logger

logger = get_logger(__name__)


class ExecutionErrorHandler:
    """
    Handles execution errors with retry logic and exponential backoff.
    
    The ExecutionErrorHandler categorizes errors as retryable or non-retryable
    and implements exponential backoff for retryable errors.
    
    Requirements:
    - 9.1: Retry code generation with validation feedback
    - 9.2: Retry execution according to configured retry policies
    - 9.4: Mark timeout errors as non-retryable
    - 9.5: Return failure response when max retries are exhausted
    """
    
    # Errors that should not be retried
    NON_RETRYABLE_ERRORS = {
        ExecutionTimeoutError,
        ExecutionMemoryError,
        NetworkError,
    }
    
    # Errors that can be retried
    RETRYABLE_ERRORS = {
        ResourceExhaustedError,
        RuntimeError,
    }
    
    def __init__(self, max_retries: int = 3):
        """
        Initialize the ExecutionErrorHandler.
        
        Args:
            max_retries: Maximum number of retry attempts
        """
        self.max_retries = max_retries
        logger.info(
            "ExecutionErrorHandler initialized",
            extra={"max_retries": max_retries}
        )
    
    def is_retryable(self, error: Exception) -> bool:
        """
        Determine if an error is retryable.
        
        Args:
            error: Exception to check
        
        Returns:
            True if the error can be retried, False otherwise
        """
        error_type = type(error)
        
        # Check if explicitly non-retryable
        if error_type in self.NON_RETRYABLE_ERRORS:
            return False
        
        # Check if explicitly retryable
        if error_type in self.RETRYABLE_ERRORS:
            return True
        
        # Check if ExecutionError with retryable flag
        if isinstance(error, ExecutionError):
            return error.retryable
        
        # Default to non-retryable for unknown errors
        return False
    
    def calculate_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff delay.
        
        Uses formula: min(2^attempt, 60) seconds
        
        Args:
            attempt: Current attempt number (0-indexed)
        
        Returns:
            Delay in seconds
        """
        delay = min(2 ** attempt, 60)
        return float(delay)
    
    def handle_error(
        self,
        error: Exception,
        request_id: str,
        attempt: int = 0
    ) -> dict:
        """
        Handle an execution error and determine retry strategy.
        
        Args:
            error: Exception that occurred
            request_id: Request identifier
            attempt: Current attempt number (0-indexed)
        
        Returns:
            Dictionary with error information and retry decision
        """
        is_retryable = self.is_retryable(error)
        
        logger.error(
            "Execution error occurred",
            extra={
                "request_id": request_id,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "attempt": attempt,
                "is_retryable": is_retryable,
            },
            exc_info=True,
        )
        
        # Check if max retries exceeded
        if attempt >= self.max_retries:
            logger.warning(
                "Maximum retry attempts exceeded",
                extra={
                    "request_id": request_id,
                    "attempts": attempt + 1,
                    "max_retries": self.max_retries,
                }
            )
            return {
                "status": "failed",
                "error": str(error),
                "error_type": type(error).__name__,
                "retryable": False,
                "attempts": attempt + 1,
                "reason": "Maximum retry attempts exceeded",
            }
        
        # Check if error is retryable
        if not is_retryable:
            logger.info(
                "Error is not retryable",
                extra={
                    "request_id": request_id,
                    "error_type": type(error).__name__,
                }
            )
            return {
                "status": "failed",
                "error": str(error),
                "error_type": type(error).__name__,
                "retryable": False,
                "attempts": attempt + 1,
            }
        
        # Calculate backoff delay
        backoff_delay = self.calculate_backoff(attempt)
        
        logger.info(
            "Error is retryable, will retry after backoff",
            extra={
                "request_id": request_id,
                "attempt": attempt,
                "backoff_delay": backoff_delay,
            }
        )
        
        return {
            "status": "retry",
            "error": str(error),
            "error_type": type(error).__name__,
            "retryable": True,
            "attempts": attempt + 1,
            "backoff_delay": backoff_delay,
        }


class RetryWrapper:
    """
    Wrapper that adds retry logic to SecureExecutor.
    
    Requirements:
    - 9.2: Retry execution according to configured retry policies
    - 9.4: Do not retry timeout errors
    - 9.5: Return detailed failure response when max retries exhausted
    """
    
    def __init__(self, executor, max_retries: int = 3):
        """
        Initialize the RetryWrapper.
        
        Args:
            executor: SecureExecutor instance to wrap
            max_retries: Maximum number of retry attempts
        """
        self.executor = executor
        self.error_handler = ExecutionErrorHandler(max_retries=max_retries)
        logger.info(
            "RetryWrapper initialized",
            extra={"max_retries": max_retries}
        )
    
    def execute_with_retry(
        self,
        code: str,
        request_id: str,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """
        Execute code with automatic retry on retryable errors.
        
        Args:
            code: Python code to execute
            request_id: Request identifier
            timeout: Timeout in seconds
        
        Returns:
            ExecutionResult from successful execution or final failure
        """
        attempt = 0
        last_error = None
        error_history = []
        
        while attempt <= self.error_handler.max_retries:
            try:
                logger.info(
                    "Attempting code execution",
                    extra={
                        "request_id": request_id,
                        "attempt": attempt + 1,
                        "max_retries": self.error_handler.max_retries + 1,
                    }
                )
                
                # Execute the code
                result = self.executor.execute(code, request_id, timeout)
                
                # Check if execution was successful
                if result.status == ExecutionStatus.SUCCESS:
                    if attempt > 0:
                        logger.info(
                            "Execution succeeded after retry",
                            extra={
                                "request_id": request_id,
                                "attempts": attempt + 1,
                            }
                        )
                    return result
                
                # Check if execution timed out (non-retryable)
                if result.status == ExecutionStatus.TIMEOUT:
                    logger.warning(
                        "Execution timed out, not retrying",
                        extra={
                            "request_id": request_id,
                            "timeout": timeout,
                        }
                    )
                    return result
                
                # Execution failed but didn't raise exception
                # Treat as non-retryable
                logger.warning(
                    "Execution failed with non-zero exit code",
                    extra={
                        "request_id": request_id,
                        "exit_code": result.exit_code,
                        "stderr": result.stderr,
                    }
                )
                return result
                
            except Exception as e:
                last_error = e
                error_info = self.error_handler.handle_error(e, request_id, attempt)
                error_history.append(error_info)
                
                # Check if we should retry
                if error_info["status"] != "retry":
                    # Error is not retryable or max retries exceeded
                    logger.error(
                        "Execution failed, not retrying",
                        extra={
                            "request_id": request_id,
                            "error_info": error_info,
                        }
                    )
                    
                    # Return failure result
                    return ExecutionResult(
                        request_id=request_id,
                        stdout="",
                        stderr=self._format_error_history(error_history),
                        exit_code=-1,
                        duration_ms=0,
                        status=ExecutionStatus.FAILED,
                    )
                
                # Wait for backoff delay before retry
                backoff_delay = error_info["backoff_delay"]
                logger.info(
                    "Waiting before retry",
                    extra={
                        "request_id": request_id,
                        "backoff_delay": backoff_delay,
                    }
                )
                time.sleep(backoff_delay)
                
                attempt += 1
        
        # Should not reach here, but handle just in case
        logger.error(
            "Retry loop exhausted without returning",
            extra={"request_id": request_id}
        )
        
        return ExecutionResult(
            request_id=request_id,
            stdout="",
            stderr=self._format_error_history(error_history),
            exit_code=-1,
            duration_ms=0,
            status=ExecutionStatus.FAILED,
        )
    
    def _format_error_history(self, error_history: list) -> str:
        """
        Format error history for stderr output.
        
        Args:
            error_history: List of error information dictionaries
        
        Returns:
            Formatted error message
        """
        lines = ["Execution failed after multiple attempts:"]
        for i, error_info in enumerate(error_history, 1):
            lines.append(f"\nAttempt {i}:")
            lines.append(f"  Error Type: {error_info['error_type']}")
            lines.append(f"  Error: {error_info['error']}")
            if "reason" in error_info:
                lines.append(f"  Reason: {error_info['reason']}")
        
        return "\n".join(lines)


class JobErrorHandler:
    """
    Handles Kubernetes Job errors and monitors job status.
    
    Requirements:
    - 9.3: Retry job creation according to Kubernetes backoff policies
    - 9.5: Emit failure events for jobs that exceed retry limits
    """
    
    def __init__(
        self,
        batch_v1_api: client.BatchV1Api,
        namespace: str = "default",
        max_job_retries: int = 3,
    ):
        """
        Initialize the JobErrorHandler.
        
        Args:
            batch_v1_api: Kubernetes BatchV1Api client
            namespace: Kubernetes namespace
            max_job_retries: Maximum number of job retry attempts
        """
        self.batch_v1 = batch_v1_api
        self.namespace = namespace
        self.max_job_retries = max_job_retries
        
        logger.info(
            "JobErrorHandler initialized",
            extra={
                "namespace": namespace,
                "max_job_retries": max_job_retries,
            }
        )
    
    def monitor_job(self, job_id: str, timeout: int = 300) -> dict:
        """
        Monitor a Kubernetes Job and handle failures.
        
        This method watches the job status and handles various failure scenarios:
        - Pod failures
        - Image pull errors
        - Deadline exceeded
        - Backoff limit exceeded
        
        Args:
            job_id: Job identifier
            timeout: Timeout for monitoring in seconds
        
        Returns:
            Dictionary with job status and outcome
        """
        logger.info(
            "Starting job monitoring",
            extra={
                "job_id": job_id,
                "timeout": timeout,
            }
        )
        
        w = watch.Watch()
        start_time = time.time()
        
        try:
            for event in w.stream(
                self.batch_v1.list_namespaced_job,
                namespace=self.namespace,
                field_selector=f"metadata.name={job_id}",
                timeout_seconds=timeout,
            ):
                job = event["object"]
                event_type = event["type"]
                
                # Check if monitoring timeout exceeded
                if time.time() - start_time > timeout:
                    logger.warning(
                        "Job monitoring timeout exceeded",
                        extra={"job_id": job_id}
                    )
                    w.stop()
                    return {
                        "status": "timeout",
                        "job_id": job_id,
                        "message": "Job monitoring timeout exceeded",
                    }
                
                # Check job status
                if job.status.succeeded:
                    logger.info(
                        "Job completed successfully",
                        extra={"job_id": job_id}
                    )
                    w.stop()
                    return {
                        "status": "success",
                        "job_id": job_id,
                    }
                
                if job.status.failed:
                    failed_count = job.status.failed
                    
                    logger.warning(
                        "Job failed",
                        extra={
                            "job_id": job_id,
                            "failed_count": failed_count,
                        }
                    )
                    
                    # Check if max retries exceeded
                    if failed_count >= self.max_job_retries:
                        logger.error(
                            "Job exceeded maximum retry attempts",
                            extra={
                                "job_id": job_id,
                                "failed_count": failed_count,
                                "max_retries": self.max_job_retries,
                            }
                        )
                        
                        # Get failure reason from conditions
                        failure_reason = self._get_failure_reason(job)
                        
                        w.stop()
                        return {
                            "status": "failed",
                            "job_id": job_id,
                            "failed_count": failed_count,
                            "reason": failure_reason,
                            "message": "Job exceeded maximum retry attempts",
                        }
                
                # Check for specific error conditions
                if job.status.conditions:
                    for condition in job.status.conditions:
                        if condition.type == "Failed":
                            reason = condition.reason
                            message = condition.message
                            
                            logger.error(
                                "Job failure condition detected",
                                extra={
                                    "job_id": job_id,
                                    "reason": reason,
                                    "failure_message": message,
                                }
                            )
                            
                            # Handle specific failure types
                            if reason == "DeadlineExceeded":
                                w.stop()
                                return {
                                    "status": "failed",
                                    "job_id": job_id,
                                    "reason": reason,
                                    "message": message,
                                }
        
        except ApiException as e:
            logger.error(
                "Error monitoring job",
                extra={
                    "job_id": job_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            return {
                "status": "error",
                "job_id": job_id,
                "error": str(e),
            }
        
        finally:
            w.stop()
        
        # If we exit the loop without returning, job is still running
        return {
            "status": "running",
            "job_id": job_id,
        }
    
    def _get_failure_reason(self, job: client.V1Job) -> str:
        """
        Extract failure reason from job status.
        
        Args:
            job: V1Job object
        
        Returns:
            Failure reason string
        """
        if job.status.conditions:
            for condition in job.status.conditions:
                if condition.type == "Failed":
                    return condition.reason or "Unknown"
        
        return "Unknown"
    
    def emit_failure_event(self, job_id: str, reason: str, message: str) -> None:
        """
        Emit a failure event for a job that exceeded retry limits.
        
        This method would typically publish to Event Hub, but for now
        it just logs the failure.
        
        Args:
            job_id: Job identifier
            reason: Failure reason
            message: Failure message
        """
        logger.error(
            "Emitting job failure event",
            extra={
                "job_id": job_id,
                "reason": reason,
                "failure_message": message,
            }
        )
        
        # TODO: Publish to Event Hub when Event Hub integration is available
        # For now, just log the event
    
    def cleanup_job(self, job_id: str) -> bool:
        """
        Clean up a failed job.
        
        Args:
            job_id: Job identifier
        
        Returns:
            True if cleanup was successful, False otherwise
        """
        try:
            self.batch_v1.delete_namespaced_job(
                name=job_id,
                namespace=self.namespace,
                propagation_policy="Background",
            )
            
            logger.info(
                "Job cleaned up successfully",
                extra={"job_id": job_id}
            )
            
            return True
        
        except ApiException as e:
            logger.error(
                "Failed to clean up job",
                extra={
                    "job_id": job_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            return False
