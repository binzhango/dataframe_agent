"""Configuration management using Pydantic Settings."""

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


class LLMServiceConfig(BaseConfig):
    """Configuration for LLM Service."""

    service_name: str = "llm-service"
    llm_endpoint: str = "http://localhost:8080"
    llm_api_key: str = ""
    max_validation_retries: int = 3
    api_host: str = "0.0.0.0"
    api_port: int = 8000


class ExecutorServiceConfig(BaseConfig):
    """Configuration for Executor Service."""

    service_name: str = "executor-service"
    execution_timeout: int = 30
    max_execution_retries: int = 3
    event_hub_connection_string: str = ""
    event_hub_consumer_group: str = "$Default"
    kubernetes_namespace: str = "default"
    api_host: str = "0.0.0.0"
    api_port: int = 8001


class HeavyJobRunnerConfig(BaseConfig):
    """Configuration for Heavy Job Runner."""

    service_name: str = "heavy-job-runner"
    azure_storage_connection_string: str = ""
    azure_storage_container: str = "execution-results"
    s3_endpoint: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "execution-results"
    event_hub_connection_string: str = ""
    execution_timeout: int = 300
