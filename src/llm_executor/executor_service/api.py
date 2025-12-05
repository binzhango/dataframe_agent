"""FastAPI application for Executor Service.

This module implements the REST API for the Executor Service, which executes
lightweight Python code in secure sandbox environments and manages Kubernetes
Jobs for heavy workloads.
"""

import uuid
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from llm_executor.executor_service.secure_executor import SecureExecutor
from llm_executor.executor_service.kubernetes_job_manager import KubernetesJobManager
from llm_executor.shared.config import ExecutorServiceConfig
from llm_executor.shared.models import ExecutionResult, ExecutionStatus, JobCreationRequest, ResourceLimits
from llm_executor.shared.logging_util import get_logger

logger = get_logger(__name__)

# Global state for tracking active executions
active_executions: Dict[str, bool] = {}


class ExecuteSnippetRequest(BaseModel):
    """Request model for code execution endpoint."""
    code: str = Field(..., description="Python code to execute", min_length=1)
    timeout: int = Field(default=30, description="Timeout in seconds", ge=1, le=300)
    request_id: str = Field(default_factory=lambda: f"req-{uuid.uuid4()}", description="Unique request identifier")


class ExecuteSnippetResponse(BaseModel):
    """Response model for code execution endpoint."""
    request_id: str = Field(..., description="Request identifier")
    stdout: str = Field(..., description="Standard output from execution")
    stderr: str = Field(..., description="Standard error from execution")
    exit_code: int = Field(..., description="Exit code from execution")
    duration_ms: int = Field(..., description="Execution duration in milliseconds")
    status: str = Field(..., description="Execution status")


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""
    status: str = Field(..., description="Service health status")
    active_executions: int = Field(..., description="Number of currently active executions")
    service_name: str = Field(..., description="Name of the service")
    version: str = Field(default="1.0.0", description="Service version")


class CreateHeavyJobRequest(BaseModel):
    """Request model for creating a heavy job."""
    code: str = Field(..., description="Python code to execute", min_length=1)
    request_id: str = Field(default_factory=lambda: f"req-{uuid.uuid4()}", description="Unique request identifier")
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits, description="Resource limits for the job")


class CreateHeavyJobResponse(BaseModel):
    """Response model for heavy job creation."""
    job_id: str = Field(..., description="Unique job identifier")
    status: str = Field(..., description="Job status")
    created_at: str = Field(..., description="Job creation timestamp")


# Initialize configuration
config = ExecutorServiceConfig()

# Initialize SecureExecutor
executor = SecureExecutor(default_timeout=config.execution_timeout)

# Initialize KubernetesJobManager (will be None if Kubernetes is not available)
try:
    job_manager = KubernetesJobManager(
        namespace=config.kubernetes_namespace,
        image="heavy-executor:latest",
        ttl_seconds=3600,
    )
except Exception as e:
    logger.warning(
        "Failed to initialize KubernetesJobManager, heavy job creation will not be available",
        extra={"error": str(e)}
    )
    job_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info(
        "Executor Service starting",
        extra={
            "service_name": config.service_name,
            "api_host": config.api_host,
            "api_port": config.api_port,
            "execution_timeout": config.execution_timeout,
        }
    )
    yield
    # Shutdown
    logger.info("Executor Service shutting down")


# Create FastAPI application
app = FastAPI(
    title="Executor Service API",
    description="REST API for secure Python code execution",
    version="1.0.0",
    lifespan=lifespan,
)


@app.post(
    "/api/v1/execute_snippet",
    response_model=ExecuteSnippetResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute Python code snippet",
    description="Executes lightweight Python code in a secure sandbox environment with timeout enforcement",
)
async def execute_snippet(request: ExecuteSnippetRequest) -> ExecuteSnippetResponse:
    """
    Execute Python code in a secure subprocess environment.
    
    This endpoint:
    - Validates the request using Pydantic models
    - Executes code using SecureExecutor with timeout enforcement
    - Tracks active executions
    - Returns execution results with stdout, stderr, and metadata
    - Handles execution failures with appropriate HTTP status codes
    
    Requirements:
    - 3.1: Execute code in restricted namespace with timeout enforcement
    - 6.5: Provide API endpoints for service interaction
    
    Args:
        request: Code execution request containing code, timeout, and request_id
    
    Returns:
        ExecuteSnippetResponse with execution results
    
    Raises:
        HTTPException: If execution fails or encounters errors
    """
    request_id = request.request_id
    
    logger.info(
        "Received code execution request",
        extra={
            "request_id": request_id,
            "code_length": len(request.code),
            "timeout": request.timeout,
        }
    )
    
    # Track active execution
    active_executions[request_id] = True
    
    try:
        # Execute code using SecureExecutor
        result: ExecutionResult = executor.execute(
            code=request.code,
            request_id=request_id,
            timeout=request.timeout,
        )
        
        logger.info(
            "Code execution completed",
            extra={
                "request_id": request_id,
                "status": result.status.value,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            }
        )
        
        # Return successful response
        return ExecuteSnippetResponse(
            request_id=result.request_id,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            status=result.status.value,
        )
    
    except Exception as e:
        logger.error(
            "Code execution failed with exception",
            extra={
                "request_id": request_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        
        # Return error response with appropriate status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Execution failed",
                "message": str(e),
                "request_id": request_id,
            }
        )
    
    finally:
        # Remove from active executions
        active_executions.pop(request_id, None)


@app.post(
    "/api/v1/create_heavy_job",
    response_model=CreateHeavyJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Kubernetes Job for heavy code execution",
    description="Creates a Kubernetes Job for resource-intensive Python code with specialized libraries",
)
async def create_heavy_job(request: CreateHeavyJobRequest) -> CreateHeavyJobResponse:
    """
    Create a Kubernetes Job for heavy code execution.
    
    This endpoint:
    - Validates the request using Pydantic models
    - Creates a Kubernetes Job with resource limits
    - Configures security context and TTL cleanup
    - Returns job_id, status, and created_at timestamp
    
    Requirements:
    - 4.3: Create Kubernetes Jobs for heavy workloads with CPU and memory limits
    
    Args:
        request: Heavy job creation request containing code and resource limits
    
    Returns:
        CreateHeavyJobResponse with job details
    
    Raises:
        HTTPException: If job creation fails or Kubernetes is not available
    """
    if job_manager is None:
        logger.error(
            "Kubernetes Job creation requested but KubernetesJobManager is not available",
            extra={"request_id": request.request_id}
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "Kubernetes Job creation not available",
                "message": "KubernetesJobManager is not initialized",
                "request_id": request.request_id,
            }
        )
    
    logger.info(
        "Received heavy job creation request",
        extra={
            "request_id": request.request_id,
            "code_length": len(request.code),
            "cpu_limit": request.resource_limits.cpu_limit,
            "memory_limit": request.resource_limits.memory_limit,
        }
    )
    
    try:
        # Create JobCreationRequest from the API request
        job_request = JobCreationRequest(
            request_id=request.request_id,
            code=request.code,
            resource_limits=request.resource_limits,
        )
        
        # Create the Kubernetes Job
        result = job_manager.create_job(job_request)
        
        logger.info(
            "Heavy job created successfully",
            extra={
                "request_id": request.request_id,
                "job_id": result.job_id,
                "status": result.status,
            }
        )
        
        return CreateHeavyJobResponse(
            job_id=result.job_id,
            status=result.status,
            created_at=result.created_at,
        )
    
    except Exception as e:
        logger.error(
            "Heavy job creation failed with exception",
            extra={
                "request_id": request.request_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Job creation failed",
                "message": str(e),
                "request_id": request.request_id,
            }
        )


@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
    description="Returns service health status and active execution count",
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint for service monitoring.
    
    This endpoint:
    - Returns service health status
    - Reports number of active executions
    - Provides service metadata
    
    Requirements:
    - 6.5: Expose health check endpoints that report service status
    
    Returns:
        HealthResponse with service status and metrics
    """
    active_count = len(active_executions)
    
    logger.debug(
        "Health check requested",
        extra={
            "active_executions": active_count,
        }
    )
    
    return HealthResponse(
        status="healthy",
        active_executions=active_count,
        service_name=config.service_name,
        version="1.0.0",
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors."""
    logger.error(
        "Unhandled exception in API",
        extra={
            "error": str(exc),
            "error_type": type(exc).__name__,
            "path": request.url.path,
        },
        exc_info=True,
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "message": str(exc),
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=config.api_host,
        port=config.api_port,
        log_level=config.log_level.lower(),
    )
