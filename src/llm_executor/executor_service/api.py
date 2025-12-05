"""FastAPI application for Executor Service.

This module implements the REST API for the Executor Service, which executes
lightweight Python code in secure sandbox environments and manages Kubernetes
Jobs for heavy workloads.
"""

import uuid
import time
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from llm_executor.executor_service.secure_executor import SecureExecutor
from llm_executor.executor_service.kubernetes_job_manager import KubernetesJobManager
from llm_executor.shared.config import ExecutorServiceConfig
from llm_executor.shared.models import ExecutionResult, ExecutionStatus, JobCreationRequest, ResourceLimits
from llm_executor.shared.logging_util import get_logger
from llm_executor.shared.database import DatabaseManager
from llm_executor.shared.repository import JobHistoryRepository
from llm_executor.shared.metrics import (
    record_request,
    record_execution,
    record_kubernetes_job,
    set_active_executions,
    set_service_health,
    get_metrics,
    record_error,
)
from llm_executor.shared.tracing import (
    initialize_tracing,
    instrument_fastapi,
    shutdown_tracing,
    trace_execution,
    trace_kubernetes_job,
    add_span_attribute,
    set_span_status,
    record_exception,
)
from opentelemetry.trace import StatusCode

logger = get_logger(__name__)

# Global state for tracking active executions
active_executions: Dict[str, bool] = {}

# Initialize database manager
db_manager = DatabaseManager()
db_manager.create_tables()


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


class JobHistoryResponse(BaseModel):
    """Response model for job history record."""
    id: int = Field(..., description="Database record ID")
    request_id: str = Field(..., description="Request identifier")
    timestamp: str = Field(..., description="Execution timestamp")
    status: str = Field(..., description="Execution status")
    exit_code: int = Field(None, description="Exit code")
    duration_ms: int = Field(..., description="Execution duration in milliseconds")
    resource_usage: Dict = Field(None, description="Resource usage metrics")
    classification: str = Field(None, description="Code classification")
    created_at: str = Field(..., description="Record creation timestamp")
    updated_at: str = Field(..., description="Record update timestamp")


class JobHistoryListResponse(BaseModel):
    """Response model for job history list."""
    total: int = Field(..., description="Total number of records")
    limit: int = Field(..., description="Number of records per page")
    offset: int = Field(..., description="Number of records skipped")
    records: list = Field(..., description="List of job history records")


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
    
    # Initialize tracing
    try:
        initialize_tracing(
            service_name=config.service_name,
            service_version="1.0.0",
        )
        logger.info("OpenTelemetry tracing initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize tracing: {e}")
    
    # Set service health to healthy
    set_service_health(config.service_name, True)
    
    # Initialize active executions gauge
    set_active_executions(config.service_name, "lightweight", 0)
    set_active_executions(config.service_name, "heavy", 0)
    
    yield
    
    # Shutdown
    logger.info("Executor Service shutting down")
    
    # Set service health to unhealthy
    set_service_health(config.service_name, False)
    
    # Shutdown tracing
    try:
        shutdown_tracing()
        logger.info("OpenTelemetry tracing shutdown")
    except Exception as e:
        logger.warning(f"Failed to shutdown tracing: {e}")


# Create FastAPI application
app = FastAPI(
    title="Executor Service API",
    description="REST API for secure Python code execution",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument FastAPI with OpenTelemetry
try:
    instrument_fastapi(app)
except Exception as e:
    logger.warning(f"Failed to instrument FastAPI with OpenTelemetry: {e}")


# Request metrics middleware
@app.middleware("http")
async def add_metrics_middleware(request: Request, call_next):
    """Record request metrics."""
    # Record request start time
    start_time = time.time()
    
    # Record request metric
    record_request(
        service=config.service_name,
        endpoint=request.url.path,
        method=request.method,
    )
    
    response = await call_next(request)
    
    # Record request duration (excluding /metrics endpoint)
    if request.url.path != "/metrics":
        duration = time.time() - start_time
        from llm_executor.shared.metrics import request_duration
        request_duration.labels(
            service=config.service_name,
            endpoint=request.url.path,
            method=request.method,
        ).observe(duration)
    
    return response


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
    set_active_executions(config.service_name, "lightweight", len(active_executions))
    
    try:
        # Execute code using SecureExecutor with tracing
        with trace_execution(request.code, request_id, "lightweight"):
            result: ExecutionResult = executor.execute(
                code=request.code,
                request_id=request_id,
                timeout=request.timeout,
            )
            
            # Add execution details to span
            add_span_attribute("execution.exit_code", result.exit_code)
            add_span_attribute("execution.duration_ms", result.duration_ms)
            add_span_attribute("execution.status", result.status.value)
        
        # Record execution metrics
        execution_status = "success" if result.exit_code == 0 else "failure"
        if result.status == ExecutionStatus.TIMEOUT:
            execution_status = "timeout"
        
        record_execution(
            service=config.service_name,
            classification="lightweight",
            status=execution_status,
            duration_seconds=result.duration_ms / 1000.0,
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
        
        # Set span status
        if result.exit_code == 0:
            set_span_status(StatusCode.OK)
        else:
            set_span_status(StatusCode.ERROR, f"Execution failed with exit code {result.exit_code}")
        
        # Save execution result to job history
        try:
            session = db_manager.get_session()
            repository = JobHistoryRepository(session)
            repository.save_execution(
                execution_result=result,
                code=request.code,
                classification="lightweight",
                resource_usage={"timeout": request.timeout}
            )
            session.close()
            logger.debug(
                "Execution result saved to job history",
                extra={"request_id": request_id}
            )
        except Exception as db_error:
            # Log but don't fail the request if database save fails
            logger.error(
                "Failed to save execution result to job history",
                extra={
                    "request_id": request_id,
                    "error": str(db_error),
                },
                exc_info=True,
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
        
        # Record exception in span
        record_exception(e)
        
        # Record error metric
        record_error(
            service=config.service_name,
            error_type=type(e).__name__,
            component="code_execution",
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
        set_active_executions(config.service_name, "lightweight", len(active_executions))


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
        
        # Create the Kubernetes Job with tracing
        with trace_kubernetes_job(f"heavy-executor-{request.request_id}", request.request_id):
            result = job_manager.create_job(job_request)
            
            # Add job details to span
            add_span_attribute("job.id", result.job_id)
            add_span_attribute("job.status", result.status)
            add_span_attribute("job.cpu_limit", request.resource_limits.cpu_limit)
            add_span_attribute("job.memory_limit", request.resource_limits.memory_limit)
        
        # Record Kubernetes job metric
        record_kubernetes_job(
            service=config.service_name,
            status="created",
        )
        
        logger.info(
            "Heavy job created successfully",
            extra={
                "request_id": request.request_id,
                "job_id": result.job_id,
                "status": result.status,
            }
        )
        
        # Set span status to OK
        set_span_status(StatusCode.OK)
        
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
        
        # Record exception in span
        record_exception(e)
        
        # Record error metric
        record_error(
            service=config.service_name,
            error_type=type(e).__name__,
            component="kubernetes_job_creation",
        )
        
        # Record failed job metric
        record_kubernetes_job(
            service=config.service_name,
            status="failed",
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
    summary="Health check endpoint (liveness probe)",
    description="Returns service health status and active execution count",
)
async def health_check() -> HealthResponse:
    """
    Health check endpoint for service monitoring (liveness probe).
    
    This endpoint:
    - Returns service health status
    - Reports number of active executions
    - Provides service metadata
    - Used by Kubernetes liveness probes
    
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


@app.get(
    "/api/v1/ready",
    status_code=status.HTTP_200_OK,
    summary="Readiness check endpoint (readiness probe)",
    description="Returns whether the service is ready to accept requests",
)
async def readiness_check() -> dict:
    """
    Readiness check endpoint (readiness probe).
    
    Returns whether the service is ready to accept requests.
    This endpoint is used by Kubernetes readiness probes.
    
    Returns:
        Dictionary with readiness status
    """
    # Check if database is accessible
    ready = True
    try:
        session = db_manager.get_session()
        session.close()
    except Exception as e:
        logger.warning(f"Database not accessible: {e}")
        ready = False
    
    return {
        "ready": ready,
        "service_name": config.service_name,
        "active_executions": len(active_executions),
    }


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint.
    
    Exposes metrics in Prometheus text format for scraping.
    
    Returns:
        Response with Prometheus metrics
    """
    metrics_data, content_type = get_metrics()
    return Response(content=metrics_data, media_type=content_type)


@app.get(
    "/api/v1/job_history",
    response_model=JobHistoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get job execution history",
    description="Retrieves job execution history with pagination and filtering",
)
async def get_job_history(
    limit: int = 100,
    offset: int = 0,
    status_filter: str = None,
    order_by: str = "timestamp",
    order_direction: str = "desc"
) -> JobHistoryListResponse:
    """
    Retrieve job execution history with pagination.
    
    This endpoint:
    - Returns paginated job history records
    - Supports filtering by status
    - Supports ordering by different fields
    - Provides total count for pagination
    
    Requirements:
    - 6.3: Store and query execution metadata including timestamps, status, and resource usage
    
    Args:
        limit: Maximum number of records to return (default: 100)
        offset: Number of records to skip (default: 0)
        status_filter: Filter by execution status (optional)
        order_by: Field to order by (default: timestamp)
        order_direction: Order direction - asc or desc (default: desc)
    
    Returns:
        JobHistoryListResponse with paginated records
    """
    logger.info(
        "Job history query requested",
        extra={
            "limit": limit,
            "offset": offset,
            "status_filter": status_filter,
            "order_by": order_by,
            "order_direction": order_direction,
        }
    )
    
    try:
        session = db_manager.get_session()
        repository = JobHistoryRepository(session)
        
        # Get records based on filter
        if status_filter:
            records = repository.get_by_status(status_filter, limit, offset)
        else:
            records = repository.get_all(limit, offset, order_by, order_direction)
        
        # Get total count
        if status_filter:
            total = repository.count_by_status(status_filter)
        else:
            total = repository.get_total_count()
        
        # Convert to dictionaries
        records_dict = [repository.to_dict(record) for record in records]
        
        session.close()
        
        logger.info(
            "Job history query completed",
            extra={
                "total": total,
                "returned": len(records_dict),
            }
        )
        
        return JobHistoryListResponse(
            total=total,
            limit=limit,
            offset=offset,
            records=records_dict,
        )
    
    except Exception as e:
        logger.error(
            "Job history query failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to retrieve job history",
                "message": str(e),
            }
        )


@app.get(
    "/api/v1/job_history/{request_id}",
    response_model=JobHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get job history by request ID",
    description="Retrieves a specific job execution record by request ID",
)
async def get_job_by_request_id(request_id: str) -> JobHistoryResponse:
    """
    Retrieve job history by request ID.
    
    This endpoint:
    - Returns a specific job history record
    - Includes all metadata fields
    
    Requirements:
    - 6.3: Store and query execution metadata including timestamps, status, and resource usage
    
    Args:
        request_id: Request identifier
    
    Returns:
        JobHistoryResponse with job details
    
    Raises:
        HTTPException: If job not found
    """
    logger.info(
        "Job history lookup by request_id",
        extra={"request_id": request_id}
    )
    
    try:
        session = db_manager.get_session()
        repository = JobHistoryRepository(session)
        
        record = repository.get_by_request_id(request_id)
        
        if not record:
            session.close()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "Job not found",
                    "message": f"No job history found for request_id: {request_id}",
                }
            )
        
        record_dict = repository.to_dict(record)
        session.close()
        
        logger.info(
            "Job history lookup completed",
            extra={"request_id": request_id, "status": record.status}
        )
        
        return JobHistoryResponse(**record_dict)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Job history lookup failed",
            extra={
                "request_id": request_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to retrieve job history",
                "message": str(e),
            }
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
