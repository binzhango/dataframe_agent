"""Unit tests for Executor Service REST API.

This module contains unit tests for the FastAPI endpoints in the Executor Service.
"""

import pytest
from fastapi.testclient import TestClient

from llm_executor.executor_service.api import app, active_executions


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_active_executions():
    """Clear active executions before each test."""
    active_executions.clear()
    yield
    active_executions.clear()


class TestHealthEndpoint:
    """Tests for the /api/v1/health endpoint."""
    
    def test_health_endpoint_returns_200(self, client):
        """Test that /api/v1/health returns 200 status code."""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
    
    def test_health_endpoint_returns_service_status(self, client):
        """
        Test that /api/v1/health returns service status and active execution count.
        
        Requirements: 6.5 - Expose health check endpoints that report service status
        """
        response = client.get("/api/v1/health")
        data = response.json()
        
        # Verify response structure
        assert "status" in data
        assert "active_executions" in data
        assert "service_name" in data
        assert "version" in data
        
        # Verify status is healthy
        assert data["status"] == "healthy"
        
        # Verify active_executions is a number
        assert isinstance(data["active_executions"], int)
        assert data["active_executions"] >= 0
        
        # Verify service_name is present
        assert data["service_name"] == "executor-service"
        
        # Verify version is present
        assert data["version"] == "1.0.0"
    
    def test_health_endpoint_tracks_active_executions(self, client):
        """Test that health endpoint correctly reports active execution count."""
        # Initially, no active executions
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["active_executions"] == 0
        
        # Simulate active executions
        active_executions["req-1"] = True
        active_executions["req-2"] = True
        
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["active_executions"] == 2
        
        # Remove one execution
        active_executions.pop("req-1")
        
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["active_executions"] == 1


class TestExecuteSnippetEndpoint:
    """Tests for the /api/v1/execute_snippet endpoint."""
    
    def test_execute_snippet_with_simple_code(self, client):
        """Test executing simple Python code."""
        request_data = {
            "code": "print('hello world')",
            "timeout": 5,
        }
        
        response = client.post("/api/v1/execute_snippet", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "request_id" in data
        assert "stdout" in data
        assert "stderr" in data
        assert "exit_code" in data
        assert "duration_ms" in data
        assert "status" in data
        
        # Verify successful execution
        assert data["status"] == "success"
        assert data["exit_code"] == 0
        assert "hello world" in data["stdout"]
    
    def test_execute_snippet_with_custom_request_id(self, client):
        """Test that custom request_id is preserved."""
        request_data = {
            "code": "result = 1 + 1",
            "timeout": 5,
            "request_id": "custom-req-123",
        }
        
        response = client.post("/api/v1/execute_snippet", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["request_id"] == "custom-req-123"
    
    def test_execute_snippet_with_timeout(self, client):
        """Test that timeout is enforced."""
        request_data = {
            "code": "import time\ntime.sleep(10)",
            "timeout": 1,
        }
        
        response = client.post("/api/v1/execute_snippet", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "timeout"
        assert data["exit_code"] == -1
        assert "timed out" in data["stderr"].lower() or "timeout" in data["stderr"].lower()
    
    def test_execute_snippet_with_error(self, client):
        """Test executing code that raises an error."""
        request_data = {
            "code": "raise ValueError('test error')",
            "timeout": 5,
        }
        
        response = client.post("/api/v1/execute_snippet", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "failed"
        assert data["exit_code"] != 0
        assert len(data["stderr"]) > 0
    
    def test_execute_snippet_validates_request(self, client):
        """Test that request validation works."""
        # Missing code field
        request_data = {
            "timeout": 5,
        }
        
        response = client.post("/api/v1/execute_snippet", json=request_data)
        assert response.status_code == 422  # Validation error
    
    def test_execute_snippet_validates_timeout_range(self, client):
        """Test that timeout validation enforces range."""
        # Timeout too low
        request_data = {
            "code": "result = 1 + 1",
            "timeout": 0,
        }
        
        response = client.post("/api/v1/execute_snippet", json=request_data)
        assert response.status_code == 422  # Validation error
        
        # Timeout too high
        request_data = {
            "code": "result = 1 + 1",
            "timeout": 500,
        }
        
        response = client.post("/api/v1/execute_snippet", json=request_data)
        assert response.status_code == 422  # Validation error
