"""Pydantic models for the LLM-Driven Secure Python Execution Platform."""

from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Status of code execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class CodeComplexity(str, Enum):
    """Classification of code complexity for routing."""
    LIGHTWEIGHT = "lightweight"
    HEAVY = "heavy"


class ResourceLimits(BaseModel):
    """Resource limits for code execution."""
    cpu_limit: str = Field(default="4", description="CPU limit (e.g., '4' for 4 cores)")
    memory_limit: str = Field(default="8Gi", description="Memory limit (e.g., '8Gi')")
    cpu_request: str = Field(default="2", description="CPU request")
    memory_request: str = Field(default="4Gi", description="Memory request")
    timeout_seconds: int = Field(default=300, description="Execution timeout in seconds")
    disk_limit: str = Field(default="10Gi", description="Disk space limit")


class CodeExecutionRequest(BaseModel):
    """Request for code execution."""
    request_id: str = Field(..., description="Unique identifier for the request")
    code: str = Field(..., description="Python code to execute")
    timeout: int = Field(default=30, description="Timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum number of retry attempts")


class ValidationResult(BaseModel):
    """Result of code validation."""
    is_valid: bool = Field(..., description="Whether the code passed validation")
    errors: List[str] = Field(default_factory=list, description="List of validation errors")
    warnings: List[str] = Field(default_factory=list, description="List of validation warnings")


class ExecutionResult(BaseModel):
    """Result of code execution."""
    request_id: str = Field(..., description="Request identifier")
    stdout: str = Field(default="", description="Standard output from execution")
    stderr: str = Field(default="", description="Standard error from execution")
    exit_code: int = Field(..., description="Exit code from execution")
    duration_ms: int = Field(..., description="Execution duration in milliseconds")
    status: ExecutionStatus = Field(..., description="Execution status")


class JobCreationRequest(BaseModel):
    """Request for creating a Kubernetes Job."""
    request_id: str = Field(..., description="Request identifier")
    code: str = Field(..., description="Python code to execute")
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits, description="Resource limits for the job")
