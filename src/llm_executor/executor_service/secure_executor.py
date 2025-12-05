"""Secure Python code executor with subprocess isolation.

This module implements the SecureExecutor class that executes Python code
in isolated subprocess environments with strict security constraints.
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

from llm_executor.shared.models import ExecutionResult, ExecutionStatus
from llm_executor.shared.exceptions import (
    TimeoutError as ExecutionTimeoutError,
    ExecutionError,
)
from llm_executor.shared.logging_util import get_logger

logger = get_logger(__name__)


class SecureExecutor:
    """
    Executes Python code in a secure, isolated subprocess environment.
    
    The SecureExecutor provides multiple layers of security:
    - Subprocess isolation with restricted environment variables
    - Timeout enforcement to prevent infinite loops
    - Working directory isolation using temporary directories
    - Output capture for stdout and stderr
    - Execution duration tracking
    
    Requirements:
    - 3.1: Execute code in restricted namespace with timeout enforcement
    - 3.4: Terminate execution when timeout is exceeded
    - 3.5: Capture stdout and stderr output
    - 6.2: Record execution duration
    """
    
    # Restricted environment variables - minimal set for Python execution
    RESTRICTED_ENV = {
        "PYTHONHASHSEED": "0",  # Deterministic hash seed
        "PYTHONDONTWRITEBYTECODE": "1",  # Don't create .pyc files
        "PYTHONUNBUFFERED": "1",  # Unbuffered output
    }
    
    def __init__(self, default_timeout: int = 30):
        """
        Initialize the SecureExecutor.
        
        Args:
            default_timeout: Default timeout in seconds for code execution
        """
        self.default_timeout = default_timeout
        logger.info(
            "SecureExecutor initialized",
            extra={"default_timeout": default_timeout}
        )
    
    def execute(
        self,
        code: str,
        request_id: str,
        timeout: Optional[int] = None
    ) -> ExecutionResult:
        """
        Execute Python code in a secure subprocess environment.
        
        This method:
        1. Creates an isolated temporary directory
        2. Executes code in a subprocess with restricted environment
        3. Enforces timeout limits
        4. Captures stdout and stderr
        5. Records execution duration
        6. Cleans up temporary resources
        
        Args:
            code: Python code to execute
            request_id: Unique identifier for the execution request
            timeout: Timeout in seconds (uses default if not specified)
        
        Returns:
            ExecutionResult containing execution status, output, and metadata
        
        Raises:
            ExecutionError: If execution fails for reasons other than timeout
        """
        timeout_seconds = timeout if timeout is not None else self.default_timeout
        
        logger.info(
            "Starting code execution",
            extra={
                "request_id": request_id,
                "timeout": timeout_seconds,
                "code_length": len(code)
            }
        )
        
        # Create isolated temporary directory
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix=f"exec_{request_id}_")
            logger.debug(
                "Created temporary directory",
                extra={
                    "request_id": request_id,
                    "temp_dir": temp_dir
                }
            )
            
            # Execute code and measure duration
            start_time = time.perf_counter()
            
            try:
                result = subprocess.run(
                    [sys.executable, "-c", code],
                    timeout=timeout_seconds,
                    capture_output=True,
                    text=True,
                    env=self.RESTRICTED_ENV,
                    cwd=temp_dir,
                    check=False  # Don't raise exception on non-zero exit
                )
                
                end_time = time.perf_counter()
                duration_ms = int((end_time - start_time) * 1000)
                
                # Determine execution status
                if result.returncode == 0:
                    status = ExecutionStatus.SUCCESS
                else:
                    status = ExecutionStatus.FAILED
                
                logger.info(
                    "Code execution completed",
                    extra={
                        "request_id": request_id,
                        "status": status.value,
                        "exit_code": result.returncode,
                        "duration_ms": duration_ms
                    }
                )
                
                return ExecutionResult(
                    request_id=request_id,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                    duration_ms=duration_ms,
                    status=status
                )
                
            except subprocess.TimeoutExpired as e:
                end_time = time.perf_counter()
                duration_ms = int((end_time - start_time) * 1000)
                
                logger.warning(
                    "Code execution timed out",
                    extra={
                        "request_id": request_id,
                        "timeout": timeout_seconds,
                        "duration_ms": duration_ms
                    }
                )
                
                # Capture any partial output from the timeout exception
                stdout = e.stdout.decode('utf-8') if e.stdout else ""
                stderr = e.stderr.decode('utf-8') if e.stderr else ""
                
                return ExecutionResult(
                    request_id=request_id,
                    stdout=stdout,
                    stderr=stderr + f"\nExecution timed out after {timeout_seconds} seconds",
                    exit_code=-1,
                    duration_ms=duration_ms,
                    status=ExecutionStatus.TIMEOUT
                )
        
        finally:
            # Clean up temporary directory
            if temp_dir:
                try:
                    import shutil
                    shutil.rmtree(temp_dir)
                    logger.debug(
                        "Cleaned up temporary directory",
                        extra={
                            "request_id": request_id,
                            "temp_dir": temp_dir
                        }
                    )
                except Exception as cleanup_error:
                    logger.error(
                        "Failed to clean up temporary directory",
                        extra={
                            "request_id": request_id,
                            "temp_dir": temp_dir,
                            "error": str(cleanup_error),
                            "component": "secure_executor",
                            "operation": "cleanup_temp_directory"
                        },
                        exc_info=True
                    )
    
    def get_restricted_env(self) -> Dict[str, str]:
        """
        Get the restricted environment variables used for execution.
        
        Returns:
            Dictionary of environment variables
        """
        return self.RESTRICTED_ENV.copy()
