"""Event Hub consumer for asynchronous code execution requests.

This module implements the EventHubConsumer class that subscribes to
Azure Event Hub messages, parses code execution requests, and routes them
to the appropriate execution environment (lightweight or heavy).
"""

import asyncio
import json
from typing import Optional

from azure.eventhub.aio import EventHubConsumerClient
from azure.eventhub import EventData
from azure.eventhub.exceptions import EventHubError

from llm_executor.executor.classifier import CodeClassifier
from llm_executor.executor_service.secure_executor import SecureExecutor
from llm_executor.executor_service.kubernetes_job_manager import KubernetesJobManager
from llm_executor.shared.models import (
    CodeExecutionRequest,
    CodeComplexity,
    JobCreationRequest,
)
from llm_executor.shared.exceptions import (
    MessageParsingError,
    ProcessingError,
)
from llm_executor.shared.logging_util import get_logger, set_request_id, clear_request_id

logger = get_logger(__name__)


class EventHubConsumer:
    """
    Consumes Event Hub messages for asynchronous code execution.
    
    The EventHubConsumer provides:
    - Subscription to code-execution-requests topic
    - Message parsing and validation using CodeExecutionRequest model
    - Routing logic using CodeClassifier
    - Heavy code execution via KubernetesJobManager
    - Lightweight code execution via SecureExecutor
    - Error handling that logs failures without blocking Event Hub retry
    - Structured logging with request_id for all message processing
    
    Requirements:
    - 5.1: Parse Event Hub messages and extract code execution requests
    - 5.2: Route heavy code to Kubernetes Job creation
    - 5.4: Log errors and allow Event Hub retry mechanisms
    - 5.5: Maintain structured logs with request_id for job tracking
    """
    
    def __init__(
        self,
        connection_string: str,
        eventhub_name: str,
        consumer_group: str,
        executor: SecureExecutor,
        job_manager: Optional[KubernetesJobManager] = None,
    ):
        """
        Initialize the EventHubConsumer.
        
        Args:
            connection_string: Azure Event Hub connection string
            eventhub_name: Name of the Event Hub (topic)
            consumer_group: Consumer group name
            executor: SecureExecutor instance for lightweight code
            job_manager: KubernetesJobManager instance for heavy code (optional)
        """
        self.connection_string = connection_string
        self.eventhub_name = eventhub_name
        self.consumer_group = consumer_group
        self.executor = executor
        self.job_manager = job_manager
        self.classifier = CodeClassifier()
        
        # Initialize Event Hub consumer client
        self.client: Optional[EventHubConsumerClient] = None
        
        logger.info(
            "EventHubConsumer initialized",
            extra={
                "eventhub_name": eventhub_name,
                "consumer_group": consumer_group,
                "has_job_manager": job_manager is not None,
            }
        )
    
    async def start(self):
        """
        Start consuming messages from Event Hub.
        
        This method creates the Event Hub consumer client and begins
        processing messages asynchronously.
        """
        logger.info(
            "Starting Event Hub consumer",
            extra={
                "eventhub_name": self.eventhub_name,
                "consumer_group": self.consumer_group,
            }
        )
        
        try:
            self.client = EventHubConsumerClient.from_connection_string(
                conn_str=self.connection_string,
                consumer_group=self.consumer_group,
                eventhub_name=self.eventhub_name,
            )
            
            # Start receiving messages
            async with self.client:
                await self.client.receive(
                    on_event=self._on_event,
                    on_error=self._on_error,
                )
        
        except EventHubError as e:
            logger.error(
                "Event Hub consumer failed to start",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise
    
    async def stop(self):
        """
        Stop consuming messages and close the Event Hub client.
        """
        logger.info("Stopping Event Hub consumer")
        
        if self.client:
            await self.client.close()
            self.client = None
        
        logger.info("Event Hub consumer stopped")
    
    async def _on_event(self, partition_context, event: EventData):
        """
        Handle incoming Event Hub message.
        
        This method:
        1. Parses the message and extracts CodeExecutionRequest
        2. Sets request_id in logging context
        3. Uses CodeClassifier to determine execution path
        4. Routes to KubernetesJobManager for heavy code
        5. Routes to SecureExecutor for lightweight code
        6. Logs errors without blocking Event Hub retry
        
        Args:
            partition_context: Partition context for checkpointing
            event: Event Hub event data
        """
        message_id = event.sequence_number
        
        try:
            # Parse message body
            request = self._parse_message(event)
            
            # Set request_id in logging context
            set_request_id(request.request_id)
            
            logger.info(
                "Received Event Hub message",
                extra={
                    "request_id": request.request_id,
                    "message_id": message_id,
                    "code_length": len(request.code),
                    "timeout": request.timeout,
                }
            )
            
            # Classify code complexity
            complexity = self.classifier.classify(request.code)
            
            logger.info(
                "Code classified",
                extra={
                    "request_id": request.request_id,
                    "complexity": complexity.value,
                }
            )
            
            # Route based on complexity
            if complexity == CodeComplexity.HEAVY:
                await self._handle_heavy_code(request)
            else:
                await self._handle_lightweight_code(request)
            
            # Update checkpoint after successful processing
            await partition_context.update_checkpoint(event)
            
            logger.info(
                "Event Hub message processed successfully",
                extra={
                    "request_id": request.request_id,
                    "message_id": message_id,
                }
            )
        
        except MessageParsingError as e:
            # Log parsing errors but don't update checkpoint (let Event Hub retry)
            logger.error(
                "Failed to parse Event Hub message",
                extra={
                    "message_id": message_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            # Don't update checkpoint - message will be retried
        
        except ProcessingError as e:
            # Log processing errors but don't update checkpoint
            logger.error(
                "Failed to process Event Hub message",
                extra={
                    "message_id": message_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            # Don't update checkpoint - message will be retried
        
        except Exception as e:
            # Log unexpected errors but don't update checkpoint
            logger.error(
                "Unexpected error processing Event Hub message",
                extra={
                    "message_id": message_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            # Don't update checkpoint - message will be retried
        
        finally:
            # Clear request_id from logging context
            clear_request_id()
    
    async def _on_error(self, partition_context, error):
        """
        Handle Event Hub errors.
        
        Args:
            partition_context: Partition context
            error: Error that occurred
        """
        logger.error(
            "Event Hub error occurred",
            extra={
                "partition_id": partition_context.partition_id if partition_context else "unknown",
                "error": str(error),
                "error_type": type(error).__name__,
            },
            exc_info=True,
        )
    
    def _parse_message(self, event: EventData) -> CodeExecutionRequest:
        """
        Parse Event Hub message and extract CodeExecutionRequest.
        
        Args:
            event: Event Hub event data
        
        Returns:
            CodeExecutionRequest object
        
        Raises:
            MessageParsingError: If message format is invalid
        """
        try:
            # Get message body as string
            body = event.body_as_str()
            
            # Parse JSON
            data = json.loads(body)
            
            # Validate and create CodeExecutionRequest
            request = CodeExecutionRequest(**data)
            
            return request
        
        except json.JSONDecodeError as e:
            raise MessageParsingError(
                f"Invalid JSON in message: {str(e)}",
                message_id=str(event.sequence_number)
            )
        
        except Exception as e:
            raise MessageParsingError(
                f"Failed to parse message: {str(e)}",
                message_id=str(event.sequence_number)
            )
    
    async def _handle_heavy_code(self, request: CodeExecutionRequest):
        """
        Handle heavy code execution by creating a Kubernetes Job.
        
        Args:
            request: Code execution request
        
        Raises:
            ProcessingError: If job creation fails
        """
        if self.job_manager is None:
            logger.error(
                "Cannot create Kubernetes Job - job_manager not available",
                extra={"request_id": request.request_id}
            )
            raise ProcessingError(
                "KubernetesJobManager not available for heavy code execution",
                message_id=request.request_id
            )
        
        try:
            logger.info(
                "Creating Kubernetes Job for heavy code",
                extra={
                    "request_id": request.request_id,
                    "code_length": len(request.code),
                }
            )
            
            # Create JobCreationRequest
            job_request = JobCreationRequest(
                request_id=request.request_id,
                code=request.code,
            )
            
            # Create the job
            result = self.job_manager.create_job(job_request)
            
            logger.info(
                "Kubernetes Job created for Event Hub message",
                extra={
                    "request_id": request.request_id,
                    "job_id": result.job_id,
                    "status": result.status,
                }
            )
        
        except Exception as e:
            logger.error(
                "Failed to create Kubernetes Job for Event Hub message",
                extra={
                    "request_id": request.request_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise ProcessingError(
                f"Job creation failed: {str(e)}",
                message_id=request.request_id
            )
    
    async def _handle_lightweight_code(self, request: CodeExecutionRequest):
        """
        Handle lightweight code execution using SecureExecutor.
        
        Args:
            request: Code execution request
        
        Raises:
            ProcessingError: If execution fails
        """
        try:
            logger.info(
                "Executing lightweight code from Event Hub message",
                extra={
                    "request_id": request.request_id,
                    "code_length": len(request.code),
                    "timeout": request.timeout,
                }
            )
            
            # Execute code (run in thread pool to avoid blocking)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.executor.execute,
                request.code,
                request.request_id,
                request.timeout,
            )
            
            logger.info(
                "Lightweight code execution completed for Event Hub message",
                extra={
                    "request_id": request.request_id,
                    "status": result.status.value,
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                }
            )
        
        except Exception as e:
            logger.error(
                "Failed to execute lightweight code from Event Hub message",
                extra={
                    "request_id": request.request_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise ProcessingError(
                f"Code execution failed: {str(e)}",
                message_id=request.request_id
            )
