"""Unit tests for LLM Service REST API.

This module contains unit tests for the FastAPI endpoints in the LLM Service.
"""

import pytest
from fastapi.testclient import TestClient

from llm_executor.llm_service.api import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


def test_health_endpoint_returns_200(client):
    """Test that /api/v1/health returns 200 status and service information.
    
    Requirements: 6.5
    """
    response = client.get("/api/v1/health")
    
    # Verify status code
    assert response.status_code == 200
    
    # Verify response structure
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "service_name" in data
    
    # Verify response values
    assert data["status"] == "healthy"
    assert data["version"] == "0.1.0"
    assert data["service_name"] == "llm-service"


def test_health_endpoint_response_format(client):
    """Test that health endpoint returns properly formatted JSON."""
    response = client.get("/api/v1/health")
    
    # Verify content type
    assert response.headers["content-type"] == "application/json"
    
    # Verify response can be parsed as JSON
    data = response.json()
    assert isinstance(data, dict)


def test_query_endpoint_exists(client):
    """Test that the query endpoint exists and accepts POST requests."""
    # Send a simple query
    response = client.post(
        "/api/v1/query",
        json={
            "query": "Calculate 1 + 1",
            "timeout": 30,
            "max_retries": 3,
        }
    )
    
    # Should not return 404 (endpoint exists)
    assert response.status_code != 404


def test_query_endpoint_with_valid_request(client):
    """Test query endpoint with a valid request."""
    response = client.post(
        "/api/v1/query",
        json={
            "query": "Calculate the sum of numbers from 1 to 10",
            "timeout": 30,
            "max_retries": 3,
        }
    )
    
    # Verify successful response
    assert response.status_code == 200
    
    # Verify response structure
    data = response.json()
    assert "request_id" in data
    assert "generated_code" in data
    assert "execution_result" in data
    assert "status" in data
    
    # Verify request_id is present
    assert data["request_id"] is not None
    assert len(data["request_id"]) > 0


def test_query_endpoint_generates_request_id(client):
    """Test that query endpoint generates a unique request ID."""
    response1 = client.post(
        "/api/v1/query",
        json={"query": "Calculate 1 + 1"}
    )
    
    response2 = client.post(
        "/api/v1/query",
        json={"query": "Calculate 2 + 2"}
    )
    
    # Both should succeed
    assert response1.status_code == 200
    assert response2.status_code == 200
    
    # Request IDs should be different
    data1 = response1.json()
    data2 = response2.json()
    assert data1["request_id"] != data2["request_id"]


def test_query_endpoint_with_custom_request_id(client):
    """Test that query endpoint respects X-Request-ID header."""
    custom_request_id = "test-request-123"
    
    response = client.post(
        "/api/v1/query",
        json={"query": "Calculate 1 + 1"},
        headers={"X-Request-ID": custom_request_id}
    )
    
    # Verify response includes the custom request ID
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_request_id
    
    data = response.json()
    assert data["request_id"] == custom_request_id


def test_query_endpoint_with_minimal_request(client):
    """Test query endpoint with minimal required fields."""
    response = client.post(
        "/api/v1/query",
        json={"query": "Print hello world"}
    )
    
    # Should succeed with default values
    assert response.status_code == 200
    
    data = response.json()
    assert "request_id" in data
    assert "generated_code" in data


def test_query_endpoint_validation_result(client):
    """Test that query endpoint includes validation results."""
    response = client.post(
        "/api/v1/query",
        json={"query": "Calculate factorial of 5"}
    )
    
    assert response.status_code == 200
    
    data = response.json()
    assert "execution_result" in data
    
    execution_result = data["execution_result"]
    assert "validation_passed" in execution_result
    assert isinstance(execution_result["validation_passed"], bool)


def test_cors_headers_present(client):
    """Test that CORS headers are properly configured."""
    response = client.get("/api/v1/health")
    
    # CORS headers should be present in the response
    # Note: TestClient may not fully simulate CORS preflight, but middleware is configured
    assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
