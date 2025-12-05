"""Integration tests for LLM Orchestration Flow.

This module contains integration tests that verify the end-to-end
behavior of the LangGraph orchestration workflow.
"""

import pytest
from llm_executor.llm_service.orchestration import LLMOrchestrationFlow
from llm_executor.shared.models import CodeComplexity


def test_simple_query_flow():
    """Test a simple query that generates valid lightweight code."""
    flow = LLMOrchestrationFlow()
    
    query = "Calculate the sum of numbers from 1 to 10"
    final_state = flow.execute(query, max_retries=3)
    
    # Verify the flow completed successfully
    assert final_state["query"] == query
    assert final_state["generated_code"] != ""
    assert final_state["validation_result"] is not None
    assert final_state["validation_result"].is_valid
    assert final_state["classification"] == CodeComplexity.LIGHTWEIGHT
    assert final_state["status"] == "routed"
    assert final_state["validation_attempts"] == 0  # No retries needed


def test_query_with_validation_failure():
    """Test a query that might generate code requiring correction."""
    flow = LLMOrchestrationFlow()
    
    query = "Read a file from disk"
    final_state = flow.execute(query, max_retries=3)
    
    # Verify validation occurred
    assert final_state["validation_result"] is not None
    
    # The mock implementation will generate safe code, so it should pass
    # In a real implementation with an actual LLM, this might fail validation


def test_max_retries_enforcement():
    """Test that max retries is properly enforced."""
    flow = LLMOrchestrationFlow()
    
    query = "Execute a system command"
    max_retries = 2
    final_state = flow.execute(query, max_retries=max_retries)
    
    # Verify max retries is respected
    assert final_state["validation_attempts"] <= max_retries
    assert final_state["max_retries"] == max_retries


def test_state_preservation():
    """Test that state is properly preserved throughout the flow."""
    flow = LLMOrchestrationFlow()
    
    query = "Generate a list of even numbers"
    max_retries = 5
    final_state = flow.execute(query, max_retries=max_retries)
    
    # Verify all expected state fields are present
    assert "query" in final_state
    assert "generated_code" in final_state
    assert "validation_result" in final_state
    assert "validation_attempts" in final_state
    assert "max_retries" in final_state
    assert "classification" in final_state
    assert "status" in final_state
    
    # Verify values are correct
    assert final_state["query"] == query
    assert final_state["max_retries"] == max_retries


def test_classification_after_validation():
    """Test that classification only occurs after successful validation."""
    flow = LLMOrchestrationFlow()
    
    query = "Sort a list of numbers"
    final_state = flow.execute(query, max_retries=3)
    
    # If classification occurred, validation must have succeeded
    if final_state.get("classification") is not None:
        assert final_state["validation_result"].is_valid, \
            "Classification should only occur after successful validation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
