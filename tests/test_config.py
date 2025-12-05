"""Unit tests for configuration loading."""

import os
import pytest
from pydantic import ValidationError

from llm_executor.shared.config import (
    BaseConfig,
    LLMServiceConfig,
    ExecutorServiceConfig,
    HeavyJobRunnerConfig,
    ValidationRulesConfig,
    ResourceLimitsConfig,
)


class TestBaseConfig:
    """Test base configuration class."""

    def test_base_config_defaults(self):
        """Test that base config loads with default values."""
        config = BaseConfig()
        assert config.log_level == "INFO"
        assert config.service_name == "unknown"
        assert config.log_retention_info_days == 30
        assert config.log_retention_error_days == 90

    def test_base_config_from_env(self, monkeypatch):
        """Test that base config loads from environment variables."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("SERVICE_NAME", "test-service")
        monkeypatch.setenv("LOG_RETENTION_INFO_DAYS", "60")
        
        config = BaseConfig()
        assert config.log_level == "DEBUG"
        assert config.service_name == "test-service"
        assert config.log_retention_info_days == 60

    def test_log_level_validation(self):
        """Test that invalid log levels are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            BaseConfig(log_level="INVALID")
        assert "log_level must be one of" in str(exc_info.value)

    def test_retention_days_validation(self):
        """Test that negative retention days are rejected."""
        with pytest.raises(ValidationError):
            BaseConfig(log_retention_info_days=-1)
        
        with pytest.raises(ValidationError):
            BaseConfig(log_retention_error_days=0)


class TestValidationRulesConfig:
    """Test validation rules configuration."""

    def test_validation_rules_defaults(self):
        """Test validation rules config with defaults."""
        config = ValidationRulesConfig()
        assert config.enable_file_io_check is True
        assert config.enable_os_commands_check is True
        assert config.enable_network_check is True
        assert config.enable_import_validation is True
        assert config.ast_parsing_timeout_ms == 30

    def test_allowed_imports_parsing(self):
        """Test parsing of allowed imports list."""
        config = ValidationRulesConfig(allowed_imports="math,json,pandas")
        imports = config.get_allowed_imports_list()
        assert imports == ["math", "json", "pandas"]

    def test_ast_timeout_validation(self):
        """Test AST parsing timeout validation."""
        with pytest.raises(ValidationError):
            ValidationRulesConfig(ast_parsing_timeout_ms=0)
        
        with pytest.raises(ValidationError):
            ValidationRulesConfig(ast_parsing_timeout_ms=2000)


class TestResourceLimitsConfig:
    """Test resource limits configuration."""

    def test_resource_limits_defaults(self):
        """Test resource limits config with defaults."""
        config = ResourceLimitsConfig()
        assert config.cpu_limit == "4"
        assert config.cpu_request == "2"
        assert config.memory_limit == "8Gi"
        assert config.memory_request == "4Gi"
        assert config.heavy_job_timeout_seconds == 300

    def test_timeout_validation(self):
        """Test heavy job timeout validation."""
        with pytest.raises(ValidationError):
            ResourceLimitsConfig(heavy_job_timeout_seconds=0)
        
        with pytest.raises(ValidationError):
            ResourceLimitsConfig(heavy_job_timeout_seconds=5000)


class TestLLMServiceConfig:
    """Test LLM Service configuration."""

    def test_llm_service_defaults(self):
        """Test that LLM Service config loads with default values."""
        config = LLMServiceConfig()
        assert config.service_name == "llm-service"
        assert config.llm_endpoint == "http://localhost:8080"
        assert config.max_validation_retries == 3
        assert config.api_port == 8000
        assert config.llm_temperature == 0.7
        assert config.llm_max_tokens == 2000

    def test_llm_service_from_env(self, monkeypatch):
        """Test that LLM Service config loads independently from environment."""
        monkeypatch.setenv("SERVICE_NAME", "custom-llm-service")
        monkeypatch.setenv("LLM_ENDPOINT", "https://api.openai.com")
        monkeypatch.setenv("LLM_API_KEY", "test-key-123")
        monkeypatch.setenv("MAX_VALIDATION_RETRIES", "5")
        monkeypatch.setenv("API_PORT", "9000")
        monkeypatch.setenv("LLM_TEMPERATURE", "0.5")
        
        config = LLMServiceConfig()
        assert config.service_name == "custom-llm-service"
        assert config.llm_endpoint == "https://api.openai.com"
        assert config.llm_api_key == "test-key-123"
        assert config.max_validation_retries == 5
        assert config.api_port == 9000
        assert config.llm_temperature == 0.5

    def test_llm_endpoint_validation(self):
        """Test that invalid LLM endpoints are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LLMServiceConfig(llm_endpoint="invalid-url")
        assert "URL must start with http://" in str(exc_info.value)

    def test_validation_retries_bounds(self):
        """Test validation retry bounds."""
        with pytest.raises(ValidationError):
            LLMServiceConfig(max_validation_retries=0)
        
        with pytest.raises(ValidationError):
            LLMServiceConfig(max_validation_retries=20)

    def test_temperature_bounds(self):
        """Test LLM temperature bounds."""
        with pytest.raises(ValidationError):
            LLMServiceConfig(llm_temperature=-0.1)
        
        with pytest.raises(ValidationError):
            LLMServiceConfig(llm_temperature=2.5)

    def test_port_validation(self):
        """Test API port validation."""
        with pytest.raises(ValidationError):
            LLMServiceConfig(api_port=0)
        
        with pytest.raises(ValidationError):
            LLMServiceConfig(api_port=70000)

    def test_startup_validation(self, monkeypatch):
        """Test startup validation for LLM Service."""
        config = LLMServiceConfig(llm_endpoint="http://localhost:8080")
        config.validate_on_startup()  # Should not raise
        
        # Create config with empty endpoint by clearing the default
        monkeypatch.setenv("LLM_ENDPOINT", "http://temp.com")
        config_invalid = LLMServiceConfig()
        config_invalid.llm_endpoint = ""  # Manually set to empty after creation
        with pytest.raises(ValueError) as exc_info:
            config_invalid.validate_on_startup()
        assert "llm_endpoint is required" in str(exc_info.value)


class TestExecutorServiceConfig:
    """Test Executor Service configuration."""

    def test_executor_service_defaults(self):
        """Test that Executor Service config loads with default values."""
        config = ExecutorServiceConfig()
        assert config.service_name == "executor-service"
        assert config.execution_timeout == 30
        assert config.max_execution_retries == 3
        assert config.api_port == 8001
        assert config.kubernetes_namespace == "default"
        assert config.kubernetes_job_ttl_seconds == 3600

    def test_executor_service_from_env(self, monkeypatch):
        """Test that Executor Service config loads independently from environment."""
        monkeypatch.setenv("SERVICE_NAME", "custom-executor")
        monkeypatch.setenv("EXECUTION_TIMEOUT", "60")
        monkeypatch.setenv("MAX_EXECUTION_RETRIES", "5")
        monkeypatch.setenv("EVENT_HUB_CONNECTION_STRING", "Endpoint=sb://test.servicebus.windows.net/")
        monkeypatch.setenv("KUBERNETES_NAMESPACE", "production")
        monkeypatch.setenv("API_PORT", "9001")
        
        config = ExecutorServiceConfig()
        assert config.service_name == "custom-executor"
        assert config.execution_timeout == 60
        assert config.max_execution_retries == 5
        assert config.event_hub_connection_string == "Endpoint=sb://test.servicebus.windows.net/"
        assert config.kubernetes_namespace == "production"
        assert config.api_port == 9001

    def test_execution_timeout_bounds(self):
        """Test execution timeout bounds."""
        with pytest.raises(ValidationError):
            ExecutorServiceConfig(execution_timeout=0)
        
        with pytest.raises(ValidationError):
            ExecutorServiceConfig(execution_timeout=500)

    def test_event_hub_connection_validation(self):
        """Test Event Hub connection string validation."""
        with pytest.raises(ValidationError) as exc_info:
            ExecutorServiceConfig(event_hub_connection_string="invalid-connection")
        assert "must start with 'Endpoint='" in str(exc_info.value)

    def test_startup_validation(self):
        """Test startup validation for Executor Service."""
        config = ExecutorServiceConfig()
        config.validate_on_startup()  # Should not raise


class TestHeavyJobRunnerConfig:
    """Test Heavy Job Runner configuration."""

    def test_heavy_job_runner_defaults(self):
        """Test that Heavy Job Runner config loads with default values."""
        config = HeavyJobRunnerConfig()
        assert config.service_name == "heavy-job-runner"
        assert config.execution_timeout == 300
        assert config.azure_storage_container == "execution-results"
        assert config.s3_bucket == "execution-results"
        assert config.s3_region == "us-east-1"

    def test_heavy_job_runner_from_env(self, monkeypatch):
        """Test that Heavy Job Runner config loads independently from environment."""
        monkeypatch.setenv("SERVICE_NAME", "custom-runner")
        monkeypatch.setenv("EXECUTION_TIMEOUT", "600")
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "DefaultEndpointsProtocol=https;AccountName=test")
        monkeypatch.setenv("EVENT_HUB_CONNECTION_STRING", "Endpoint=sb://test.servicebus.windows.net/")
        monkeypatch.setenv("S3_ENDPOINT", "https://s3.amazonaws.com")
        monkeypatch.setenv("S3_BUCKET", "my-results")
        monkeypatch.setenv("CODE", "print('hello')")
        monkeypatch.setenv("REQUEST_ID", "req-123")
        
        config = HeavyJobRunnerConfig()
        assert config.service_name == "custom-runner"
        assert config.execution_timeout == 600
        assert config.azure_storage_connection_string == "DefaultEndpointsProtocol=https;AccountName=test"
        assert config.event_hub_connection_string == "Endpoint=sb://test.servicebus.windows.net/"
        assert config.s3_endpoint == "https://s3.amazonaws.com"
        assert config.s3_bucket == "my-results"
        assert config.code == "print('hello')"
        assert config.request_id == "req-123"

    def test_execution_timeout_bounds(self):
        """Test execution timeout bounds."""
        with pytest.raises(ValidationError):
            HeavyJobRunnerConfig(execution_timeout=0)
        
        with pytest.raises(ValidationError):
            HeavyJobRunnerConfig(execution_timeout=5000)

    def test_event_hub_connection_validation(self):
        """Test Event Hub connection string validation."""
        with pytest.raises(ValidationError) as exc_info:
            HeavyJobRunnerConfig(event_hub_connection_string="invalid-connection")
        assert "must start with 'Endpoint='" in str(exc_info.value)

    def test_startup_validation_requires_storage(self):
        """Test that startup validation requires at least one storage backend."""
        config = HeavyJobRunnerConfig()
        with pytest.raises(ValueError) as exc_info:
            config.validate_on_startup()
        assert "At least one storage backend" in str(exc_info.value)

    def test_startup_validation_requires_event_hub(self):
        """Test that startup validation requires Event Hub configuration."""
        config = HeavyJobRunnerConfig(
            azure_storage_connection_string="DefaultEndpointsProtocol=https;AccountName=test"
        )
        with pytest.raises(ValueError) as exc_info:
            config.validate_on_startup()
        assert "event_hub_connection_string is required" in str(exc_info.value)

    def test_startup_validation_success_with_azure(self):
        """Test successful startup validation with Azure storage."""
        config = HeavyJobRunnerConfig(
            azure_storage_connection_string="DefaultEndpointsProtocol=https;AccountName=test",
            event_hub_connection_string="Endpoint=sb://test.servicebus.windows.net/"
        )
        config.validate_on_startup()  # Should not raise

    def test_startup_validation_success_with_s3(self):
        """Test successful startup validation with S3 storage."""
        config = HeavyJobRunnerConfig(
            s3_endpoint="https://s3.amazonaws.com",
            s3_access_key="test-key",
            s3_secret_key="test-secret",
            event_hub_connection_string="Endpoint=sb://test.servicebus.windows.net/"
        )
        config.validate_on_startup()  # Should not raise


class TestConfigurationIndependence:
    """Test that each component loads configuration independently."""

    def test_llm_service_config_independent(self, monkeypatch):
        """Test LLM Service config loads independently without affecting others."""
        # Clear SERVICE_NAME to ensure each config uses its own default
        monkeypatch.delenv("SERVICE_NAME", raising=False)
        monkeypatch.setenv("LLM_ENDPOINT", "https://llm.example.com")
        monkeypatch.setenv("API_PORT", "8000")
        
        llm_config = LLMServiceConfig()
        assert llm_config.service_name == "llm-service"
        assert llm_config.api_port == 8000
        
        # Executor config should have different defaults even with same env vars
        executor_config = ExecutorServiceConfig()
        assert executor_config.service_name == "executor-service"
        # API_PORT is shared, so executor will also see 8000 from env
        # But it has its own default of 8001 which would be used if API_PORT wasn't set

    def test_executor_service_config_independent(self, monkeypatch):
        """Test Executor Service config loads independently without affecting others."""
        # Clear SERVICE_NAME to ensure each config uses its own default
        monkeypatch.delenv("SERVICE_NAME", raising=False)
        monkeypatch.setenv("EXECUTION_TIMEOUT", "45")
        monkeypatch.setenv("API_PORT", "8001")
        
        executor_config = ExecutorServiceConfig()
        assert executor_config.service_name == "executor-service"
        assert executor_config.execution_timeout == 45
        assert executor_config.api_port == 8001
        
        # LLM config should have different defaults even with same env vars
        llm_config = LLMServiceConfig()
        assert llm_config.service_name == "llm-service"
        # API_PORT is shared, so llm will also see 8001 from env
        # But it has its own default of 8000 which would be used if API_PORT wasn't set

    def test_heavy_job_runner_config_independent(self, monkeypatch):
        """Test Heavy Job Runner config loads independently without affecting others."""
        # Clear SERVICE_NAME to ensure each config uses its own default
        monkeypatch.delenv("SERVICE_NAME", raising=False)
        monkeypatch.setenv("EXECUTION_TIMEOUT", "300")
        monkeypatch.setenv("CODE", "print('test')")
        
        runner_config = HeavyJobRunnerConfig()
        assert runner_config.service_name == "heavy-job-runner"
        assert runner_config.execution_timeout == 300
        assert runner_config.code == "print('test')"
        
        # Executor config should have different defaults even with same env vars
        executor_config = ExecutorServiceConfig()
        assert executor_config.service_name == "executor-service"
        # EXECUTION_TIMEOUT is shared, so executor will also see 300 from env
        # But it has its own default of 30 which would be used if EXECUTION_TIMEOUT wasn't set

    def test_all_configs_can_coexist(self, monkeypatch):
        """Test that all configs can be loaded simultaneously with different values."""
        # Set environment variables that would be used by different services
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LLM_ENDPOINT", "https://llm.example.com")
        monkeypatch.setenv("EXECUTION_TIMEOUT", "60")
        monkeypatch.setenv("AZURE_STORAGE_CONNECTION_STRING", "DefaultEndpointsProtocol=https")
        
        # Load all configs
        llm_config = LLMServiceConfig()
        executor_config = ExecutorServiceConfig()
        runner_config = HeavyJobRunnerConfig()
        
        # Verify they all loaded correctly with their own defaults
        assert llm_config.service_name == "llm-service"
        assert executor_config.service_name == "executor-service"
        assert runner_config.service_name == "heavy-job-runner"
        
        # Verify shared config is consistent
        assert llm_config.log_level == "DEBUG"
        assert executor_config.log_level == "DEBUG"
        assert runner_config.log_level == "DEBUG"
        
        # Verify service-specific config is independent
        assert llm_config.llm_endpoint == "https://llm.example.com"
        assert executor_config.execution_timeout == 60
        assert runner_config.azure_storage_connection_string == "DefaultEndpointsProtocol=https"
