"""Heavy Job Runner execution script.

This script is the main entry point for Kubernetes Job pods that execute
resource-intensive Python code. It fetches code from environment variables,
executes it with timeout enforcement, captures results, uploads them to
cloud storage, and emits completion events to Event Hub.
"""

import os
import sys
import json
import subprocess
import tempfile
import time
import traceback
from pathlib import Path
from typing import Optional, Dict, Any

from llm_executor.shared.config import HeavyJobRunnerConfig
from llm_executor.shared.models import ExecutionResult, ExecutionStatus
from llm_executor.shared.logging_util import setup_logging, get_logger, set_request_id


def get_env_variable(name: str, default: Optional[str] = None) -> str:
    """
    Get environment variable with optional default.
    
    Args:
        name: Environment variable name
        default: Default value if not set
        
    Returns:
        Environment variable value
        
    Raises:
        ValueError: If variable is not set and no default provided
    """
    value = os.environ.get(name, default)
    if value is None:
        raise ValueError(f"Required environment variable {name} is not set")
    return value


def execute_code(code: str, timeout: int, request_id: str, logger) -> ExecutionResult:
    """
    Execute Python code in a subprocess with timeout enforcement.
    
    Args:
        code: Python code to execute
        timeout: Timeout in seconds
        request_id: Request identifier
        logger: Logger instance
        
    Returns:
        ExecutionResult with execution details
    """
    logger.info("Starting code execution", extra={"timeout": timeout})
    
    start_time = time.perf_counter()
    
    try:
        # Execute code using subprocess
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),  # Use current environment
        )
        
        end_time = time.perf_counter()
        duration_ms = int((end_time - start_time) * 1000)
        
        # Determine status based on exit code
        if result.returncode == 0:
            status = ExecutionStatus.SUCCESS
        else:
            status = ExecutionStatus.FAILED
        
        logger.info(
            "Code execution completed",
            extra={
                "status": status.value,
                "exit_code": result.returncode,
                "duration_ms": duration_ms,
            }
        )
        
        return ExecutionResult(
            request_id=request_id,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            duration_ms=duration_ms,
            status=status,
        )
        
    except subprocess.TimeoutExpired as e:
        end_time = time.perf_counter()
        duration_ms = int((end_time - start_time) * 1000)
        
        logger.warning(
            "Code execution timed out",
            extra={"timeout": timeout, "duration_ms": duration_ms}
        )
        
        # Capture any partial output
        stdout = e.stdout.decode() if e.stdout else ""
        stderr = e.stderr.decode() if e.stderr else ""
        stderr += f"\nExecution timed out after {timeout} seconds"
        
        return ExecutionResult(
            request_id=request_id,
            stdout=stdout,
            stderr=stderr,
            exit_code=-1,
            duration_ms=duration_ms,
            status=ExecutionStatus.TIMEOUT,
        )
        
    except Exception as e:
        end_time = time.perf_counter()
        duration_ms = int((end_time - start_time) * 1000)
        
        logger.error(
            "Code execution failed with exception",
            extra={"error": str(e), "duration_ms": duration_ms},
            exc_info=True
        )
        
        return ExecutionResult(
            request_id=request_id,
            stdout="",
            stderr=f"Execution error: {str(e)}\n{traceback.format_exc()}",
            exit_code=-1,
            duration_ms=duration_ms,
            status=ExecutionStatus.FAILED,
        )


def upload_result_to_azure(
    result: ExecutionResult,
    config: HeavyJobRunnerConfig,
    logger
) -> str:
    """
    Upload execution result to Azure Blob Storage.
    
    Args:
        result: Execution result to upload
        config: Configuration with Azure credentials
        logger: Logger instance
        
    Returns:
        URL/path to uploaded result
        
    Raises:
        Exception: If upload fails
    """
    try:
        import fsspec
        
        # Create result filename
        result_filename = f"{result.request_id}.json"
        
        # Build Azure Blob Storage URL
        # Format: abfs://<container>@<account>.dfs.core.windows.net/<path>
        # For simplicity, we'll use the connection string approach
        storage_options = {
            "connection_string": config.azure_storage_connection_string
        }
        
        result_path = f"abfs://{config.azure_storage_container}/{result_filename}"
        
        logger.info(
            "Uploading result to Azure Blob Storage",
            extra={"path": result_path}
        )
        
        # Serialize result to JSON
        result_json = result.model_dump_json(indent=2)
        
        # Upload using fsspec
        with fsspec.open(result_path, "w", **storage_options) as f:
            f.write(result_json)
        
        logger.info("Result uploaded successfully", extra={"path": result_path})
        
        return result_path
        
    except Exception as e:
        logger.error(
            "Failed to upload result to Azure Blob Storage",
            extra={"error": str(e)},
            exc_info=True
        )
        raise


def upload_result_to_s3(
    result: ExecutionResult,
    config: HeavyJobRunnerConfig,
    logger
) -> str:
    """
    Upload execution result to S3.
    
    Args:
        result: Execution result to upload
        config: Configuration with S3 credentials
        logger: Logger instance
        
    Returns:
        URL/path to uploaded result
        
    Raises:
        Exception: If upload fails
    """
    try:
        import fsspec
        
        # Create result filename
        result_filename = f"{result.request_id}.json"
        
        # Build S3 URL
        result_path = f"s3://{config.s3_bucket}/{result_filename}"
        
        # S3 storage options
        storage_options = {
            "key": config.s3_access_key,
            "secret": config.s3_secret_key,
        }
        
        if config.s3_endpoint:
            storage_options["client_kwargs"] = {"endpoint_url": config.s3_endpoint}
        
        logger.info(
            "Uploading result to S3",
            extra={"path": result_path}
        )
        
        # Serialize result to JSON
        result_json = result.model_dump_json(indent=2)
        
        # Upload using fsspec
        with fsspec.open(result_path, "w", **storage_options) as f:
            f.write(result_json)
        
        logger.info("Result uploaded successfully", extra={"path": result_path})
        
        return result_path
        
    except Exception as e:
        logger.error(
            "Failed to upload result to S3",
            extra={"error": str(e)},
            exc_info=True
        )
        raise


def emit_completion_event(
    result: ExecutionResult,
    result_location: str,
    config: HeavyJobRunnerConfig,
    logger
) -> None:
    """
    Emit completion event to Azure Event Hub.
    
    Args:
        result: Execution result
        result_location: Location where result was uploaded
        config: Configuration with Event Hub credentials
        logger: Logger instance
    """
    try:
        from azure.eventhub import EventHubProducerClient, EventData
        
        if not config.event_hub_connection_string:
            logger.warning("Event Hub connection string not configured, skipping event emission")
            return
        
        logger.info("Emitting completion event to Event Hub")
        
        # Create event payload
        event_payload = {
            "request_id": result.request_id,
            "status": result.status.value,
            "result_location": result_location,
            "duration_ms": result.duration_ms,
            "exit_code": result.exit_code,
            "timestamp": time.time(),
        }
        
        # Create Event Hub producer
        producer = EventHubProducerClient.from_connection_string(
            conn_str=config.event_hub_connection_string,
            eventhub_name="execution-results"
        )
        
        # Send event
        with producer:
            event_data = EventData(json.dumps(event_payload))
            producer.send_event(event_data)
        
        logger.info("Completion event emitted successfully")
        
    except Exception as e:
        logger.error(
            "Failed to emit completion event",
            extra={"error": str(e)},
            exc_info=True
        )
        # Don't raise - event emission failure shouldn't fail the job


def cleanup_temporary_files(temp_dir: Optional[Path], logger) -> None:
    """
    Clean up temporary files created during execution.
    
    Args:
        temp_dir: Temporary directory to clean up
        logger: Logger instance
    """
    if temp_dir is None:
        return
    
    try:
        if temp_dir.exists():
            logger.info("Cleaning up temporary files", extra={"temp_dir": str(temp_dir)})
            
            import shutil
            
            # Remove directory and all its contents recursively
            shutil.rmtree(temp_dir)
            logger.info("Temporary files cleaned up successfully")
            
    except Exception as e:
        logger.error(
            "Failed to clean up temporary files",
            extra={"error": str(e), "temp_dir": str(temp_dir)},
            exc_info=True
        )


def main() -> int:
    """
    Main entry point for Heavy Job Runner.
    
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    # Load configuration
    config = HeavyJobRunnerConfig()
    
    # Set up logging
    setup_logging(config.service_name, config.log_level)
    logger = get_logger(__name__)
    
    temp_dir: Optional[Path] = None
    
    try:
        # Fetch required environment variables
        code = get_env_variable("CODE")
        request_id = get_env_variable("REQUEST_ID")
        timeout_str = get_env_variable("TIMEOUT", str(config.execution_timeout))
        timeout = int(timeout_str)
        
        # Set request_id in logging context
        set_request_id(request_id)
        
        logger.info(
            "Heavy Job Runner started",
            extra={
                "request_id": request_id,
                "timeout": timeout,
                "code_length": len(code),
            }
        )
        
        # Create temporary directory for execution
        temp_dir = Path(tempfile.mkdtemp(prefix="heavy_job_"))
        logger.debug("Created temporary directory", extra={"temp_dir": str(temp_dir)})
        
        # Execute code
        result = execute_code(code, timeout, request_id, logger)
        
        # Determine storage backend and upload result
        result_location = ""
        
        if config.azure_storage_connection_string:
            try:
                result_location = upload_result_to_azure(result, config, logger)
            except Exception as e:
                logger.error("Azure upload failed, trying S3 fallback", extra={"error": str(e)})
                if config.s3_access_key and config.s3_secret_key:
                    result_location = upload_result_to_s3(result, config, logger)
                else:
                    raise
        elif config.s3_access_key and config.s3_secret_key:
            result_location = upload_result_to_s3(result, config, logger)
        else:
            logger.warning("No storage backend configured, result will not be uploaded")
            result_location = "local://not-uploaded"
        
        # Emit completion event to Event Hub
        emit_completion_event(result, result_location, config, logger)
        
        # Clean up temporary files
        cleanup_temporary_files(temp_dir, logger)
        
        logger.info(
            "Heavy Job Runner completed successfully",
            extra={
                "status": result.status.value,
                "result_location": result_location,
            }
        )
        
        # Return exit code based on execution status
        if result.status == ExecutionStatus.SUCCESS:
            return 0
        else:
            return 1
        
    except Exception as e:
        logger.error(
            "Heavy Job Runner failed",
            extra={"error": str(e)},
            exc_info=True
        )
        
        # Clean up temporary files even on failure
        if temp_dir:
            cleanup_temporary_files(temp_dir, logger)
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
