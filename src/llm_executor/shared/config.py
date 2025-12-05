"""Configuration management using Pydantic Settings."""

from typing import List, Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    """Base configuration class for all services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Common configuration
    log_level: str = "INFO"
    service_name: str = "unknown"
    
    # Log aggregation configuration for Azure Log Analytics
    azure_log_analytics_workspace_id: str = ""
    azure_log_analytics_shared_key: str = ""
    azure_log_analytics_log_type: str = "LLMExecutorLogs"
    
    # Log retention policies (in days)
    log_retention_info_days: int = 30
    log_retention_error_days: int = 90

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is one of the standard levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()

    @field_validator("log_retention_info_days", "log_retention_error_days")
    @classmethod
    def validate_retention_days(cls, v: int) -> int:
        """Validate retention days are positive."""
        if v <= 0:
            raise ValueError("Retention days must be positive")
        return v

    def validate_on_startup(self) -> None:
        """Validate configuration on service startup. Override in subclasses."""
        pass


class ValidationRulesConfig(BaseSettings):
    """Configuration for code validation rules."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Validation rules configuration
    enable_file_io_check: bool = True
    enable_os_commands_check: bool = True
    enable_network_check: bool = True
    enable_import_validation: bool = True
    
    # Allowed imports (comma-separated in env var)
    allowed_imports: str = "math,random,datetime,json,re,itertools,functools,collections"
    
    # AST parsing timeout in milliseconds
    ast_parsing_timeout_ms: int = 30
    
    @field_validator("ast_parsing_timeout_ms")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate AST parsing timeout is reasonable."""
        if v <= 0 or v > 1000:
            raise ValueError("AST parsing timeout must be between 1 and 1000 ms")
        return v
    
    def get_allowed_imports_list(self) -> List[str]:
        """Parse allowed imports from comma-separated string."""
        return [imp.strip() for imp in self.allowed_imports.split(",") if imp.strip()]


class ResourceLimitsConfig(BaseSettings):
    """Configuration for resource limits."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # CPU limits
    cpu_limit: str = "4"
    cpu_request: str = "2"
    
    # Memory limits
    memory_limit: str = "8Gi"
    memory_request: str = "4Gi"
    
    # Disk limits
    disk_limit: str = "10Gi"
    
    # Timeout for heavy jobs
    heavy_job_timeout_seconds: int = 300
    
    @field_validator("heavy_job_timeout_seconds")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate timeout is reasonable."""
        if v <= 0 or v > 3600:
            raise ValueError("Heavy job timeout must be between 1 and 3600 seconds")
        return v


class LLMServiceConfig(BaseConfig):
    """Configuration for LLM Service."""

    service_name: str = "llm-service"
    
    # LLM endpoint configuration
    llm_endpoint: str = Field(default="http://localhost:8080", description="LLM API endpoint URL")
    llm_api_key: str = Field(default="", description="API key for LLM service")
    llm_model: str = Field(default="gpt-4", description="LLM model to use")
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="LLM temperature")
    llm_max_tokens: int = Field(default=2000, gt=0, description="Maximum tokens for LLM response")
    
    # Validation configuration
    max_validation_retries: int = Field(default=3, ge=1, le=10, description="Maximum validation retry attempts")
    validation_timeout_seconds: int = Field(default=5, gt=0, description="Timeout for validation")
    
    # API configuration
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, gt=0, lt=65536)
    
    # Executor service endpoint
    executor_service_url: str = Field(default="http://executor-service:8001", description="Executor service URL")
    
    @field_validator("llm_endpoint", "executor_service_url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format."""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v
    
    def validate_on_startup(self) -> None:
        """Validate LLM Service configuration on startup."""
        if not self.llm_endpoint:
            raise ValueError("llm_endpoint is required")
        if self.max_validation_retries < 1:
            raise ValueError("max_validation_retries must be at least 1")


class ExecutorServiceConfig(BaseConfig):
    """Configuration for Executor Service."""

    service_name: str = "executor-service"
    
    # Execution configuration
    execution_timeout: int = Field(default=30, gt=0, le=300, description="Timeout for lightweight execution in seconds")
    max_execution_retries: int = Field(default=3, ge=0, le=10, description="Maximum execution retry attempts")
    
    # Event Hub configuration
    event_hub_connection_string: str = Field(default="", description="Azure Event Hub connection string")
    event_hub_consumer_group: str = Field(default="$Default", description="Event Hub consumer group")
    event_hub_requests_topic: str = Field(default="code-execution-requests", description="Event Hub requests topic")
    event_hub_results_topic: str = Field(default="execution-results", description="Event Hub results topic")
    
    # Kubernetes configuration
    kubernetes_namespace: str = Field(default="default", description="Kubernetes namespace for jobs")
    kubernetes_job_ttl_seconds: int = Field(default=3600, gt=0, description="TTL for completed Kubernetes jobs")
    kubernetes_job_image: str = Field(default="heavy-executor:latest", description="Docker image for heavy jobs")
    
    # API configuration
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8001, gt=0, lt=65536)
    
    # Resource limits for heavy jobs
    heavy_job_cpu_limit: str = "4"
    heavy_job_cpu_request: str = "2"
    heavy_job_memory_limit: str = "8Gi"
    heavy_job_memory_request: str = "4Gi"
    
    @field_validator("event_hub_connection_string")
    @classmethod
    def validate_event_hub_connection(cls, v: str) -> str:
        """Validate Event Hub connection string format."""
        if v and not v.startswith("Endpoint="):
            raise ValueError("Event Hub connection string must start with 'Endpoint='")
        return v
    
    def validate_on_startup(self) -> None:
        """Validate Executor Service configuration on startup."""
        if self.execution_timeout <= 0:
            raise ValueError("execution_timeout must be positive")
        if self.kubernetes_job_ttl_seconds <= 0:
            raise ValueError("kubernetes_job_ttl_seconds must be positive")


class HeavyJobRunnerConfig(BaseConfig):
    """Configuration for Heavy Job Runner."""

    service_name: str = "heavy-job-runner"
    
    # Storage configuration - Azure
    azure_storage_connection_string: str = Field(default="", description="Azure Storage connection string")
    azure_storage_container: str = Field(default="execution-results", description="Azure Storage container name")
    
    # Storage configuration - S3
    s3_endpoint: str = Field(default="", description="S3 endpoint URL")
    s3_access_key: str = Field(default="", description="S3 access key")
    s3_secret_key: str = Field(default="", description="S3 secret key")
    s3_bucket: str = Field(default="execution-results", description="S3 bucket name")
    s3_region: str = Field(default="us-east-1", description="S3 region")
    
    # Event Hub configuration
    event_hub_connection_string: str = Field(default="", description="Azure Event Hub connection string")
    event_hub_results_topic: str = Field(default="execution-results", description="Event Hub results topic")
    
    # Execution configuration
    execution_timeout: int = Field(default=300, gt=0, le=3600, description="Timeout for heavy execution in seconds")
    
    # Job configuration from environment (set by Kubernetes)
    code: str = Field(default="", description="Code to execute (from env var)")
    request_id: str = Field(default="", description="Request ID (from env var)")
    
    @field_validator("event_hub_connection_string")
    @classmethod
    def validate_event_hub_connection(cls, v: str) -> str:
        """Validate Event Hub connection string format."""
        if v and not v.startswith("Endpoint="):
            raise ValueError("Event Hub connection string must start with 'Endpoint='")
        return v
    
    @model_validator(mode="after")
    def validate_storage_config(self) -> "HeavyJobRunnerConfig":
        """Validate that at least one storage backend is configured."""
        has_azure = bool(self.azure_storage_connection_string)
        has_s3 = bool(self.s3_endpoint and self.s3_access_key and self.s3_secret_key)
        
        if not has_azure and not has_s3:
            # Allow empty config for testing, but warn
            pass
        
        return self
    
    def validate_on_startup(self) -> None:
        """Validate Heavy Job Runner configuration on startup."""
        if self.execution_timeout <= 0:
            raise ValueError("execution_timeout must be positive")
        
        # Check that at least one storage backend is configured
        has_azure = bool(self.azure_storage_connection_string)
        has_s3 = bool(self.s3_endpoint and self.s3_access_key and self.s3_secret_key)
        
        if not has_azure and not has_s3:
            raise ValueError("At least one storage backend (Azure or S3) must be configured")
        
        # Check Event Hub is configured
        if not self.event_hub_connection_string:
            raise ValueError("event_hub_connection_string is required")
