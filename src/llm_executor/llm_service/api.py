"""FastAPI application for LLM Service.

This module implements the REST API for the LLM Service, providing endpoints
for natural language query processing and health checks.
"""

import uuid
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from llm_executor.llm_service.orchestration import LLMOrchestrationFlow
from llm_executor.shared.config import LLMServiceConfig
from llm_executor.shared.logging_util import get_logger
from llm_executor.shared.models import CodeComplexity


# ============================================================================
# Request/Response Models
# ============================================================================

class QueryRequest(BaseModel):
    """Request model for natural language query."""
    query: str = Field(..., description="Natural language query for code generation")
    timeout: Optional[int] = Field(default=30, description="Execution timeout in seconds")
    max_retries: Optional[int] = Field(default=3, description="Maximum validation retry attempts")


class QueryResponse(BaseModel):
    """Response model for query execution."""
    request_id: str = Field(..., description="Unique identifier for the request")
    generated_code: str = Field(..., description="Generated Python code")
    execution_result: dict = Field(default_factory=dict, description="Execution result details")
    status: str = Field(..., description="Overall status of the request")
    classification: Optional[str] = Field(None, description="Code complexity classification")
    validation_attempts: int = Field(default=0, description="Number of validation attempts")


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str = Field(..., description="Service health status")
    version: str = Field(..., description="Service version")
    service_name: str = Field(..., description="Name of the service")


# ============================================================================
# Application Setup
# ============================================================================

# Load configuration
config = LLMServiceConfig()

# Initialize logger
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info(
        "Starting LLM Service",
        extra={
            "service_name": config.service_name,
            "api_host": config.api_host,
            "api_port": config.api_port,
        }
    )
    
    # Initialize the orchestration flow
    app.state.orchestration_flow = LLMOrchestrationFlow()
    
    yield
    
    # Shutdown
    logger.info("Shutting down LLM Service")


# Create FastAPI application
app = FastAPI(
    title="LLM Service API",
    description="REST API for LLM-Driven Secure Python Execution Platform",
    version="0.1.0",
    lifespan=lifespan,
)


# ============================================================================
# Middleware Configuration
# ============================================================================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add request ID to all requests and propagate through pipeline."""
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    
    # Add request ID to logger context
    logger.info(
        "Incoming request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
        }
    )
    
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.error(
        "Unhandled exception",
        extra={
            "request_id": request_id,
            "error": str(exc),
            "error_type": type(exc).__name__,
        },
        exc_info=True,
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "request_id": request_id,
            "error": "Internal server error",
            "detail": str(exc),
        }
    )


# ============================================================================
# API Endpoints
# ============================================================================

@app.post("/api/v1/query", response_model=QueryResponse)
async def process_query(query_request: QueryRequest, request: Request) -> QueryResponse:
    """Process a natural language query and generate/execute Python code.
    
    This endpoint receives a natural language query, generates Python code using LLM,
    validates the code, and routes it to the appropriate execution environment.
    
    Args:
        query_request: The query request containing the natural language query
        request: FastAPI request object
        
    Returns:
        QueryResponse containing the generated code and execution results
        
    Raises:
        HTTPException: If query processing fails
    """
    request_id = request.state.request_id
    
    logger.info(
        "Processing query",
        extra={
            "request_id": request_id,
            "query": query_request.query,
            "max_retries": query_request.max_retries,
        }
    )
    
    try:
        # Get or create the orchestration flow
        if not hasattr(request.app.state, "orchestration_flow"):
            request.app.state.orchestration_flow = LLMOrchestrationFlow()
        
        orchestration_flow: LLMOrchestrationFlow = request.app.state.orchestration_flow
        final_state = orchestration_flow.execute(
            query=query_request.query,
            max_retries=query_request.max_retries,
        )
        
        # Determine overall status
        status = final_state.get("status", "unknown")
        validation_result = final_state.get("validation_result")
        classification = final_state.get("classification")
        
        # Check if validation failed after max retries
        if validation_result and not validation_result.is_valid:
            if final_state.get("validation_attempts", 0) >= query_request.max_retries:
                status = "validation_failed_max_retries"
                logger.warning(
                    "Validation failed after max retries",
                    extra={
                        "request_id": request_id,
                        "validation_attempts": final_state.get("validation_attempts"),
                        "errors": validation_result.errors,
                    }
                )
        
        # Build execution result
        execution_result = {
            "validation_passed": validation_result.is_valid if validation_result else False,
            "validation_errors": validation_result.errors if validation_result else [],
            "validation_warnings": validation_result.warnings if validation_result else [],
        }
        
        # Add classification if available
        if classification:
            execution_result["classification"] = classification.value
        
        logger.info(
            "Query processed successfully",
            extra={
                "request_id": request_id,
                "status": status,
                "validation_attempts": final_state.get("validation_attempts", 0),
                "classification": classification.value if classification else None,
            }
        )
        
        return QueryResponse(
            request_id=request_id,
            generated_code=final_state.get("generated_code", ""),
            execution_result=execution_result,
            status=status,
            classification=classification.value if classification else None,
            validation_attempts=final_state.get("validation_attempts", 0),
        )
        
    except Exception as e:
        logger.error(
            "Query processing failed",
            extra={
                "request_id": request_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Query processing failed: {str(e)}"
        )


@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint.
    
    Returns the current health status of the LLM Service.
    
    Returns:
        HealthResponse containing service status and version information
    """
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        service_name=config.service_name,
    )


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host=config.api_host,
        port=config.api_port,
        log_level=config.log_level.lower(),
    )
