"""Example usage of the LLM Orchestration Flow.

This script demonstrates how to use the LangGraph orchestration flow
to process natural language queries and generate validated Python code.
"""

from llm_executor.llm_service.orchestration import LLMOrchestrationFlow
from llm_executor.shared.models import CodeComplexity


def main():
    """Run example queries through the orchestration flow."""
    
    # Create the orchestration flow
    flow = LLMOrchestrationFlow()
    
    # Example queries
    queries = [
        "Calculate the sum of numbers from 1 to 100",
        "Generate a list of even numbers from 0 to 20",
        "Find the factorial of 10",
        "Create a dictionary with keys and values",
    ]
    
    print("=" * 80)
    print("LLM Orchestration Flow Examples")
    print("=" * 80)
    print()
    
    for i, query in enumerate(queries, 1):
        print(f"Query {i}: {query}")
        print("-" * 80)
        
        # Execute the flow
        result = flow.execute(query, max_retries=3)
        
        # Display results
        print(f"Status: {result['status']}")
        print(f"Generated Code:\n{result['generated_code']}")
        print(f"Validation: {'✓ Valid' if result['validation_result'].is_valid else '✗ Invalid'}")
        
        if result['validation_result'].is_valid:
            print(f"Classification: {result['classification'].value}")
        else:
            print(f"Validation Errors: {result['validation_result'].errors}")
            print(f"Validation Attempts: {result['validation_attempts']}")
        
        print()
    
    print("=" * 80)
    print("Flow Execution Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()
