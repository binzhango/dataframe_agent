"""LangGraph orchestration flow for LLM Service.

This module implements the LangGraph workflow that orchestrates code generation,
validation, correction, and routing for the LLM-Driven Secure Python Execution Platform.
"""

from typing import TypedDict, Annotated, Sequence, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage

from llm_executor.executor.validator import CodeValidator
from llm_executor.executor.classifier import CodeClassifier
from llm_executor.shared.models import (
    ValidationResult,
    CodeComplexity,
)


# ============================================================================
# State Definition
# ============================================================================

class GraphState(TypedDict):
    """State for the LangGraph orchestration flow."""
    query: str
    generated_code: str
    validation_result: ValidationResult
    validation_attempts: int
    max_retries: int
    classification: CodeComplexity
    error: str
    status: str


# ============================================================================
# Node Implementations
# ============================================================================

class InputParserNode:
    """Extracts intent and parameters from natural language queries."""
    
    def __call__(self, state: GraphState) -> GraphState:
        """Parse the input query and prepare for code generation.
        
        Args:
            state: Current graph state
            
        Returns:
            Updated state with parsed query information
        """
        # For now, we pass through the query as-is
        # In a full implementation, this would extract structured parameters
        return {
            **state,
            "status": "parsed",
        }


class CodeGenerationNode:
    """Calls LLM with structured prompts to generate Python code."""
    
    def __init__(self, llm_client=None):
        """Initialize the code generation node.
        
        Args:
            llm_client: Optional LLM client for code generation.
                       If None, uses a mock implementation.
        """
        self.llm_client = llm_client
    
    def __call__(self, state: GraphState) -> GraphState:
        """Generate Python code from the query using LLM.
        
        Args:
            state: Current graph state
            
        Returns:
            Updated state with generated code
        """
        query = state["query"]
        
        if self.llm_client:
            # Use actual LLM client
            generated_code = self._call_llm(query)
        else:
            # Mock implementation for testing
            generated_code = self._mock_generate(query)
        
        return {
            **state,
            "generated_code": generated_code,
            "status": "generated",
        }
    
    def _call_llm(self, query: str) -> str:
        """Call the actual LLM to generate code.
        
        Args:
            query: Natural language query
            
        Returns:
            Generated Python code
        """
        # This would be implemented with actual LLM integration
        prompt = f"""Generate Python code to answer this query: {query}

Requirements:
- Write clean, efficient Python code
- Do not use file I/O operations
- Do not use OS commands or subprocess
- Do not use network operations
- Only use standard library modules from the allowlist

Return only the Python code, no explanations."""
        
        # Placeholder for actual LLM call
        response = self.llm_client.generate(prompt)
        return response
    
    def _mock_generate(self, query: str) -> str:
        """Mock code generation for testing.
        
        Args:
            query: Natural language query
            
        Returns:
            Simple Python code
        """
        # Simple mock that generates basic code
        return "result = 1 + 1"


class CodeValidatorNode:
    """Invokes the CodeValidator and returns validation results."""
    
    def __init__(self):
        """Initialize the code validator node."""
        self.validator = CodeValidator()
    
    def __call__(self, state: GraphState) -> GraphState:
        """Validate the generated code.
        
        Args:
            state: Current graph state
            
        Returns:
            Updated state with validation results
        """
        code = state["generated_code"]
        
        # Perform validation
        validation_result = self.validator.validate(code)
        
        return {
            **state,
            "validation_result": validation_result,
            "status": "validated" if validation_result.is_valid else "validation_failed",
        }


class CorrectionNode:
    """Sends validation errors back to LLM for code correction."""
    
    def __init__(self, llm_client=None):
        """Initialize the correction node.
        
        Args:
            llm_client: Optional LLM client for code correction.
                       If None, uses a mock implementation.
        """
        self.llm_client = llm_client
    
    def __call__(self, state: GraphState) -> GraphState:
        """Request corrected code from LLM based on validation errors.
        
        Args:
            state: Current graph state
            
        Returns:
            Updated state with corrected code and incremented attempt counter
        """
        query = state["query"]
        failed_code = state["generated_code"]
        validation_result = state["validation_result"]
        attempts = state.get("validation_attempts", 0)
        
        # Increment validation attempts
        new_attempts = attempts + 1
        
        if self.llm_client:
            # Use actual LLM client
            corrected_code = self._call_llm_for_correction(
                query, failed_code, validation_result
            )
        else:
            # Mock implementation for testing
            corrected_code = self._mock_correct(failed_code, validation_result)
        
        return {
            **state,
            "generated_code": corrected_code,
            "validation_attempts": new_attempts,
            "status": "corrected",
        }
    
    def _call_llm_for_correction(
        self, query: str, failed_code: str, validation_result: ValidationResult
    ) -> str:
        """Call the LLM to correct the code based on validation errors.
        
        Args:
            query: Original natural language query
            failed_code: Code that failed validation
            validation_result: Validation errors and warnings
            
        Returns:
            Corrected Python code
        """
        errors_text = "\n".join(validation_result.errors)
        
        prompt = f"""The following code failed validation:

```python
{failed_code}
```

Validation errors:
{errors_text}

Original query: {query}

Please generate corrected Python code that:
1. Addresses all validation errors
2. Still fulfills the original query
3. Follows all security constraints

Return only the corrected Python code, no explanations."""
        
        # Placeholder for actual LLM call
        response = self.llm_client.generate(prompt)
        return response
    
    def _mock_correct(self, failed_code: str, validation_result: ValidationResult) -> str:
        """Mock code correction for testing.
        
        Args:
            failed_code: Code that failed validation
            validation_result: Validation errors
            
        Returns:
            Simple corrected code
        """
        # Simple mock that returns safe code
        return "result = sum(range(10))"


class ExecutionRouterNode:
    """Uses CodeClassifier to determine execution environment."""
    
    def __init__(self):
        """Initialize the execution router node."""
        self.classifier = CodeClassifier()
    
    def __call__(self, state: GraphState) -> GraphState:
        """Classify code and determine routing.
        
        Args:
            state: Current graph state
            
        Returns:
            Updated state with classification result
        """
        code = state["generated_code"]
        
        # Classify the code
        classification = self.classifier.classify(code)
        
        return {
            **state,
            "classification": classification,
            "status": "routed",
        }


# ============================================================================
# Conditional Edge Functions
# ============================================================================

def should_retry_validation(state: GraphState) -> Literal["correction", "max_retries_exceeded"]:
    """Determine if validation should be retried or if max retries exceeded.
    
    Args:
        state: Current graph state
        
    Returns:
        "correction" if should retry, "max_retries_exceeded" if limit reached
    """
    attempts = state.get("validation_attempts", 0)
    max_retries = state.get("max_retries", 3)
    
    if attempts >= max_retries:
        return "max_retries_exceeded"
    return "correction"


def check_validation_result(state: GraphState) -> Literal["valid", "invalid"]:
    """Check if validation passed or failed.
    
    Args:
        state: Current graph state
        
    Returns:
        "valid" if validation passed, "invalid" if failed
    """
    validation_result = state.get("validation_result")
    
    if validation_result and validation_result.is_valid:
        return "valid"
    return "invalid"


# ============================================================================
# Graph Construction
# ============================================================================

class LLMOrchestrationFlow:
    """LangGraph orchestration flow for the LLM Service."""
    
    def __init__(self, llm_client=None):
        """Initialize the orchestration flow.
        
        Args:
            llm_client: Optional LLM client for code generation and correction.
                       If None, uses mock implementations for testing.
        """
        self.llm_client = llm_client
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow.
        
        Returns:
            Compiled StateGraph ready for execution
        """
        # Create the graph
        workflow = StateGraph(GraphState)
        
        # Add nodes
        workflow.add_node("input_parser", InputParserNode())
        workflow.add_node("code_generation", CodeGenerationNode(self.llm_client))
        workflow.add_node("code_validator", CodeValidatorNode())
        workflow.add_node("correction", CorrectionNode(self.llm_client))
        workflow.add_node("execution_router", ExecutionRouterNode())
        
        # Set entry point
        workflow.set_entry_point("input_parser")
        
        # Add edges
        workflow.add_edge("input_parser", "code_generation")
        workflow.add_edge("code_generation", "code_validator")
        
        # Conditional edge after validation
        workflow.add_conditional_edges(
            "code_validator",
            check_validation_result,
            {
                "valid": "execution_router",
                "invalid": "check_retry_limit",
            }
        )
        
        # Add a node to check retry limit
        workflow.add_node("check_retry_limit", lambda state: state)
        
        # Conditional edge for retry logic
        workflow.add_conditional_edges(
            "check_retry_limit",
            should_retry_validation,
            {
                "correction": "correction",
                "max_retries_exceeded": END,
            }
        )
        
        # After correction, go back to validation
        workflow.add_edge("correction", "code_validator")
        
        # After routing, we're done
        workflow.add_edge("execution_router", END)
        
        # Compile the graph
        return workflow.compile()
    
    def execute(self, query: str, max_retries: int = 3) -> GraphState:
        """Execute the orchestration flow for a given query.
        
        Args:
            query: Natural language query
            max_retries: Maximum number of validation retry attempts
            
        Returns:
            Final state after execution
        """
        initial_state: GraphState = {
            "query": query,
            "generated_code": "",
            "validation_result": None,
            "validation_attempts": 0,
            "max_retries": max_retries,
            "classification": None,
            "error": "",
            "status": "initialized",
        }
        
        # Execute the graph
        final_state = self.graph.invoke(initial_state)
        
        return final_state
