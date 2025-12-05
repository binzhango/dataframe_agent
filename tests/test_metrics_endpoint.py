"""Unit tests for Prometheus metrics endpoints.

This module tests that the metrics endpoints expose required metrics
in Prometheus format for both LLM Service and Executor Service.

Requirements:
- 6.2: Record execution duration statistics
"""

import pytest
from fastapi.testclient import TestClient

from llm_executor.llm_service.api import app as llm_app
from llm_executor.executor_service.api import app as executor_app
from llm_executor.shared.metrics import (
    record_request,
    record_validation,
    record_execution,
    record_classification,
    record_kubernetes_job,
    set_service_health,
)


class TestLLMServiceMetricsEndpoint:
    """Test metrics endpoint for LLM Service."""
    
    def test_metrics_endpoint_exists(self):
        """Test that /metrics endpoint exists and returns 200."""
        client = TestClient(llm_app)
        response = client.get("/metrics")
        
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
    
    def test_metrics_endpoint_exposes_prometheus_format(self):
        """Test that metrics endpoint returns Prometheus text format."""
        client = TestClient(llm_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check for Prometheus format indicators
        assert "# HELP" in content or "# TYPE" in content or "_total" in content
    
    def test_metrics_endpoint_exposes_request_metrics(self):
        """Test that request metrics are exposed."""
        # Record some request metrics
        record_request("llm_service", "/api/v1/query", "POST")
        
        client = TestClient(llm_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check for request counter metric
        assert "llm_executor_requests_total" in content
    
    def test_metrics_endpoint_exposes_validation_metrics(self):
        """Test that validation metrics are exposed."""
        # Record some validation metrics
        record_validation("llm_service", success=True, duration_seconds=0.025)
        record_validation("llm_service", success=False, duration_seconds=0.030)
        
        client = TestClient(llm_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check for validation metrics
        assert "llm_executor_validations_total" in content
        assert "llm_executor_validation_duration_seconds" in content
    
    def test_metrics_endpoint_exposes_classification_metrics(self):
        """Test that classification metrics are exposed."""
        # Record some classification metrics
        record_classification("llm_service", "lightweight")
        record_classification("llm_service", "heavy")
        
        client = TestClient(llm_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check for classification metrics
        assert "llm_executor_classifications_total" in content
    
    def test_metrics_endpoint_exposes_health_metrics(self):
        """Test that health metrics are exposed."""
        # Set service health
        set_service_health("llm_service", True)
        
        client = TestClient(llm_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check for health metrics
        assert "llm_executor_service_health" in content


class TestExecutorServiceMetricsEndpoint:
    """Test metrics endpoint for Executor Service."""
    
    def test_metrics_endpoint_exists(self):
        """Test that /metrics endpoint exists and returns 200."""
        client = TestClient(executor_app)
        response = client.get("/metrics")
        
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
    
    def test_metrics_endpoint_exposes_prometheus_format(self):
        """Test that metrics endpoint returns Prometheus text format."""
        client = TestClient(executor_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check for Prometheus format indicators
        assert "# HELP" in content or "# TYPE" in content or "_total" in content
    
    def test_metrics_endpoint_exposes_execution_metrics(self):
        """Test that execution metrics are exposed."""
        # Record some execution metrics
        record_execution(
            service="executor_service",
            classification="lightweight",
            status="success",
            duration_seconds=1.5,
        )
        
        client = TestClient(executor_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check for execution metrics
        assert "llm_executor_executions_total" in content
        assert "llm_executor_execution_duration_seconds" in content
    
    def test_metrics_endpoint_exposes_kubernetes_job_metrics(self):
        """Test that Kubernetes Job metrics are exposed."""
        # Record some Kubernetes Job metrics
        record_kubernetes_job("executor_service", "created", duration_seconds=120.0)
        
        client = TestClient(executor_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check for Kubernetes Job metrics
        assert "llm_executor_kubernetes_jobs_total" in content
        assert "llm_executor_kubernetes_job_duration_seconds" in content
    
    def test_metrics_endpoint_exposes_active_executions(self):
        """Test that active executions gauge is exposed."""
        client = TestClient(executor_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check for active executions gauge
        assert "llm_executor_active_executions" in content
    
    def test_metrics_endpoint_exposes_error_metrics(self):
        """Test that error metrics are exposed."""
        from llm_executor.shared.metrics import record_error
        
        # Record some error metrics
        record_error("executor_service", "TimeoutError", "code_execution")
        
        client = TestClient(executor_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check for error metrics
        assert "llm_executor_errors_total" in content


class TestMetricsLabels:
    """Test that metrics include proper labels."""
    
    def test_request_metrics_include_labels(self):
        """Test that request metrics include service, endpoint, and method labels."""
        # Record request with specific labels
        record_request("test_service", "/api/v1/test", "GET")
        
        client = TestClient(llm_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check that labels are present in the metric
        assert 'service="test_service"' in content or "test_service" in content
    
    def test_execution_metrics_include_classification_label(self):
        """Test that execution metrics include classification label."""
        # Record execution with classification
        record_execution(
            service="test_service",
            classification="lightweight",
            status="success",
            duration_seconds=0.5,
        )
        
        client = TestClient(executor_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check that classification label is present
        assert 'classification="lightweight"' in content or "lightweight" in content
    
    def test_validation_metrics_include_result_label(self):
        """Test that validation metrics include result label."""
        # Record validation with result
        record_validation("test_service", success=True, duration_seconds=0.01)
        
        client = TestClient(llm_app)
        response = client.get("/metrics")
        
        content = response.text
        
        # Check that result label is present
        assert 'result="success"' in content or "success" in content


class TestHealthCheckEndpoints:
    """Test health check and readiness endpoints."""
    
    def test_llm_service_health_endpoint(self):
        """Test LLM Service health endpoint."""
        client = TestClient(llm_app)
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service_name" in data
    
    def test_llm_service_readiness_endpoint(self):
        """Test LLM Service readiness endpoint."""
        client = TestClient(llm_app)
        response = client.get("/api/v1/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
        assert "service_name" in data
    
    def test_executor_service_health_endpoint(self):
        """Test Executor Service health endpoint."""
        client = TestClient(executor_app)
        response = client.get("/api/v1/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "active_executions" in data
    
    def test_executor_service_readiness_endpoint(self):
        """Test Executor Service readiness endpoint."""
        client = TestClient(executor_app)
        response = client.get("/api/v1/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
        assert "service_name" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
