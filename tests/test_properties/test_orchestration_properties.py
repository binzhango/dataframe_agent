"""Property-based tests for LLM Orchestration Flow.

This module contains property-based tests that verify the correctness
properties of the LangGraph orchestration workflow.
"""

from hypothesis import given, settings, strategies as st

from llm_executor.llm_service.orchestration import (
    LLMOrchestrationFlow,
    GraphState,
)
from llm_executor.shared.models import CodeComplexity


# ============================================================================
# Custom Strategies for Query Generation
# ============================================================================

@st.composite
def natural_language_queries(draw):
    """Generate natural language queries for code generation."""
    queries = [
        "Calculate the sum of numbers from 1 to 100",
        "Generate a list of even numbers",
        "Find the factorial of 10",
        "Create a dictionary with keys and values",
        "Sort a list of numbers",
        "Calculate the average of a list",
        "Find the maximum value in a list",
        "Count occurrences of items",
        "Filter positive numbers from a list",
        "Reverse a string",
    ]
    return draw(st.sampled_from(queries))


@st.composite
def queries_generating_invalid_code(draw):
    """Generate queries that might produce invalid code."""
    queries = [
        "Read a file from disk",
        "Execute a system command",
        "Make an HTTP request",
        "Open a socket connection",
        "Import the os module",
        "Use subprocess to run a command",
    ]
    return draw(st.sampled_from(queries))


# ============================================================================
# Property 1: Validation precedes execution
# Validates: Requirements 1.2
# ============================================================================

# Feature: llm-python-executor, Property 1: Validation precedes execution
@given(query=natural_language_queries())
@settings(max_examples=100)
def test_validation_precedes_execution(query):
    """
    Property: For any generated Python code, the validation function must be
    invoked and complete before any execution function is called.
    
    This test verifies that the orchestration flow always validates code
    before proceeding to routing/execution.
    """
    flow = LLMOrchestrationFlow()
    
    # Execute the flow
    final_state = flow.execute(query, max_retries=3)
    
    # Verify that validation occurred
    assert "validation_result" in final_state, \
        "Validation result must be present in final state"
    assert final_state["validation_result"] is not None, \
        "Validation must have been performed"
    
    # Verify that if routing occurred, validation was successful
    if final_state.get("classification") is not None:
        assert final_state["validation_result"].is_valid, \
            "Routing should only occur after successful validation"
    
    # Verify status progression
    # If we reached routing, we must have passed validation
    if final_state.get("status") == "routed":
        assert final_state["validation_result"].is_valid, \
            "Cannot reach routed status without valid code"


# ============================================================================
# Property 2: Validation errors trigger correction
# Validates: Requirements 1.3, 2.4
# ============================================================================

# Feature: llm-python-executor, Property 2: Validation errors trigger correction
@given(query=queries_generating_invalid_code())
@settings(max_examples=100)
def test_validation_errors_trigger_correction(query):
    """
    Property: For any code that fails validation, the correction node must be
    invoked with the validation errors as input.
    
    This test verifies that validation failures trigger the correction workflow.
    """
    flow = LLMOrchestrationFlow()
    
    # Execute the flow
    final_state = flow.execute(query, max_retries=3)
    
    # Verify validation occurred
    assert "validation_result" in final_state, \
        "Validation result must be present"
    
    # If validation failed, check that correction was attempted
    if not final_state["validation_result"].is_valid:
        # Correction should have been attempted
        assert final_state.get("validation_attempts", 0) > 0, \
            "Validation failures should trigger correction attempts"
        
        # Verify we didn't exceed max retries
        assert final_state["validation_attempts"] <= final_state["max_retries"], \
            "Should not exceed maximum retry limit"


# ============================================================================
# Property 7: Valid code proceeds to routing
# Validates: Requirements 2.5
# ============================================================================

# Feature: llm-python-executor, Property 7: Valid code proceeds to routing
@given(query=natural_language_queries())
@settings(max_examples=100)
def test_valid_code_proceeds_to_routing(query):
    """
    Property: For any code that passes validation, the system must invoke
    the routing logic to determine execution environment.
    
    This test verifies that valid code always proceeds to classification
    and routing.
    """
    flow = LLMOrchestrationFlow()
    
    # Execute the flow
    final_state = flow.execute(query, max_retries=3)
    
    # If validation succeeded, routing must have occurred
    if final_state.get("validation_result") and final_state["validation_result"].is_valid:
        assert "classification" in final_state, \
            "Classification must be present for valid code"
        assert final_state["classification"] is not None, \
            "Valid code must be classified"
        assert final_state["classification"] in [CodeComplexity.LIGHTWEIGHT, CodeComplexity.HEAVY], \
            f"Classification must be LIGHTWEIGHT or HEAVY, got: {final_state['classification']}"
        
        # Verify status reached routing
        assert final_state.get("status") == "routed", \
            "Valid code should reach routed status"


# ============================================================================
# Property 23: Validation retry limit
# Validates: Requirements 9.1
# ============================================================================

# Feature: llm-python-executor, Property 23: Validation retry limit
@given(
    query=queries_generating_invalid_code(),
    max_retries=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=100)
def test_validation_retry_limit(query, max_retries):
    """
    Property: For any code that repeatedly fails validation, the LLM Service
    must stop retrying after the maximum retry count is reached and return
    a failure response.
    
    This test verifies that the retry limit is enforced correctly.
    """
    flow = LLMOrchestrationFlow()
    
    # Execute the flow with specified max_retries
    final_state = flow.execute(query, max_retries=max_retries)
    
    # Verify max_retries is respected
    assert final_state["validation_attempts"] <= max_retries, \
        f"Validation attempts ({final_state['validation_attempts']}) should not exceed max_retries ({max_retries})"
    
    # If validation failed and we hit the limit, verify we stopped
    if not final_state.get("validation_result", {}).is_valid:
        if final_state["validation_attempts"] >= max_retries:
            # Should not have proceeded to routing
            assert final_state.get("classification") is None, \
                "Should not route after exceeding retry limit"
            
            # Status should not be "routed"
            assert final_state.get("status") != "routed", \
                "Should not reach routed status after exceeding retry limit"


# ============================================================================
# Additional Integration Property Tests
# ============================================================================

# Feature: llm-python-executor, Property: State consistency
@given(query=natural_language_queries())
@settings(max_examples=50)
def test_state_consistency_throughout_flow(query):
    """
    Property: For any query, the state must remain consistent throughout
    the flow execution.
    
    This test verifies that state fields are properly maintained and
    updated as the flow progresses.
    """
    flow = LLMOrchestrationFlow()
    
    # Execute the flow
    final_state = flow.execute(query, max_retries=3)
    
    # Verify required fields are present
    assert "query" in final_state, "Query must be preserved in state"
    assert final_state["query"] == query, "Query must match input"
    
    assert "generated_code" in final_state, "Generated code must be in state"
    assert isinstance(final_state["generated_code"], str), "Generated code must be a string"
    
    assert "validation_attempts" in final_state, "Validation attempts must be tracked"
    assert final_state["validation_attempts"] >= 0, "Validation attempts must be non-negative"
    
    assert "max_retries" in final_state, "Max retries must be in state"
    assert final_state["max_retries"] == 3, "Max retries must match input"
    
    assert "status" in final_state, "Status must be present"
    assert isinstance(final_state["status"], str), "Status must be a string"


# Feature: llm-python-executor, Property: Code generation always produces output
@given(query=natural_language_queries())
@settings(max_examples=50)
def test_code_generation_produces_output(query):
    """
    Property: For any query, the code generation node must produce
    non-empty code output.
    
    This test verifies that code generation always produces some output.
    """
    flow = LLMOrchestrationFlow()
    
    # Execute the flow
    final_state = flow.execute(query, max_retries=3)
    
    # Verify code was generated
    assert "generated_code" in final_state, "Generated code must be present"
    assert len(final_state["generated_code"]) > 0, \
        "Generated code must not be empty"
