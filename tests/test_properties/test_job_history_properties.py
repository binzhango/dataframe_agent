"""Property-based tests for job history and metadata storage.

This module contains property-based tests that verify job history records
contain all required metadata fields as specified in the design document.

Requirements: 6.3
"""

import json
from datetime import datetime
from hypothesis import given, strategies as st, settings
from hypothesis.strategies import composite

from llm_executor.shared.database import DatabaseManager, JobHistory
from llm_executor.shared.repository import JobHistoryRepository
from llm_executor.shared.models import ExecutionResult, ExecutionStatus


@composite
def execution_results(draw):
    """
    Generate random ExecutionResult instances for testing.
    
    Returns:
        ExecutionResult with random but valid data
    """
    request_id = f"req-{draw(st.uuids())}"
    status = draw(st.sampled_from(list(ExecutionStatus)))
    
    return ExecutionResult(
        request_id=request_id,
        stdout=draw(st.text(max_size=1000)),
        stderr=draw(st.text(max_size=1000)),
        exit_code=draw(st.integers(min_value=-1, max_value=255)),
        duration_ms=draw(st.integers(min_value=0, max_value=300000)),
        status=status
    )


@composite
def code_samples(draw):
    """
    Generate random Python code samples for testing.
    
    Returns:
        String containing Python code
    """
    code_templates = [
        "print('Hello, World!')",
        "result = 1 + 1",
        "x = [i**2 for i in range(10)]",
        "import math\nresult = math.sqrt(16)",
        "def foo():\n    return 42\nresult = foo()",
    ]
    return draw(st.sampled_from(code_templates))


@composite
def resource_usage_dicts(draw):
    """
    Generate random resource usage dictionaries.
    
    Returns:
        Dictionary with resource usage metrics
    """
    return {
        "timeout": draw(st.integers(min_value=1, max_value=300)),
        "cpu_limit": draw(st.sampled_from(["1", "2", "4", "8"])),
        "memory_limit": draw(st.sampled_from(["1Gi", "2Gi", "4Gi", "8Gi"])),
    }


class TestJobHistoryProperties:
    """Property-based tests for job history metadata storage."""
    
    def setup_method(self):
        """Set up test database for each test."""
        # Use in-memory SQLite database for testing
        self.db_manager = DatabaseManager(database_url="sqlite:///:memory:")
        self.db_manager.create_tables()
    
    def teardown_method(self):
        """Clean up database after each test."""
        self.db_manager.close()
    
    # Feature: llm-python-executor, Property 20: Job history contains metadata
    @given(
        execution_result=execution_results(),
        code=code_samples(),
        classification=st.sampled_from(["lightweight", "heavy"]),
        resource_usage=resource_usage_dicts()
    )
    @settings(max_examples=100)
    def test_job_history_contains_required_metadata(
        self,
        execution_result,
        code,
        classification,
        resource_usage
    ):
        """
        Property 20: Job history contains metadata
        
        For any job execution stored in history, the record must contain
        timestamp, status, and resource_usage fields.
        
        This test verifies that:
        1. All saved job history records contain timestamp field
        2. All saved job history records contain status field
        3. All saved job history records contain resource_usage field
        4. The metadata fields are properly populated with valid data
        
        Validates: Requirements 6.3
        """
        # Arrange
        session = self.db_manager.get_session()
        repository = JobHistoryRepository(session)
        
        # Act - Save execution result to job history
        saved_record = repository.save_execution(
            execution_result=execution_result,
            code=code,
            classification=classification,
            resource_usage=resource_usage
        )
        
        # Assert - Verify record contains required metadata fields
        assert saved_record is not None, "Saved record should not be None"
        
        # Verify timestamp field exists and is valid
        assert hasattr(saved_record, 'timestamp'), "Record must have timestamp field"
        assert saved_record.timestamp is not None, "Timestamp must not be None"
        assert isinstance(saved_record.timestamp, datetime), "Timestamp must be a datetime object"
        
        # Verify status field exists and is valid
        assert hasattr(saved_record, 'status'), "Record must have status field"
        assert saved_record.status is not None, "Status must not be None"
        assert saved_record.status == execution_result.status.value, \
            f"Status should match execution result: expected {execution_result.status.value}, got {saved_record.status}"
        
        # Verify resource_usage field exists and is valid
        assert hasattr(saved_record, 'resource_usage'), "Record must have resource_usage field"
        assert saved_record.resource_usage is not None, "Resource usage must not be None"
        
        # Verify resource_usage can be parsed as JSON
        parsed_resource_usage = json.loads(saved_record.resource_usage)
        assert isinstance(parsed_resource_usage, dict), "Resource usage must be a dictionary"
        assert parsed_resource_usage == resource_usage, \
            f"Resource usage should match input: expected {resource_usage}, got {parsed_resource_usage}"
        
        # Verify additional required fields
        assert hasattr(saved_record, 'request_id'), "Record must have request_id field"
        assert saved_record.request_id == execution_result.request_id, \
            "Request ID should match execution result"
        
        assert hasattr(saved_record, 'duration_ms'), "Record must have duration_ms field"
        assert saved_record.duration_ms == execution_result.duration_ms, \
            "Duration should match execution result"
        
        # Clean up
        session.close()
    
    # Feature: llm-python-executor, Property 20: Job history contains metadata
    @given(
        execution_result=execution_results(),
        code=code_samples()
    )
    @settings(max_examples=100)
    def test_job_history_retrieval_preserves_metadata(
        self,
        execution_result,
        code
    ):
        """
        Property 20: Job history contains metadata (retrieval)
        
        For any job execution stored in history, retrieving the record
        must preserve all metadata fields.
        
        This test verifies that:
        1. Saved records can be retrieved by request_id
        2. Retrieved records contain all metadata fields
        3. Metadata values are preserved during storage and retrieval
        
        Validates: Requirements 6.3
        """
        # Arrange
        session = self.db_manager.get_session()
        repository = JobHistoryRepository(session)
        
        resource_usage = {"timeout": 30, "cpu_limit": "2"}
        
        # Act - Save and retrieve
        saved_record = repository.save_execution(
            execution_result=execution_result,
            code=code,
            classification="lightweight",
            resource_usage=resource_usage
        )
        
        retrieved_record = repository.get_by_request_id(execution_result.request_id)
        
        # Assert - Verify retrieved record matches saved record
        assert retrieved_record is not None, "Retrieved record should not be None"
        assert retrieved_record.request_id == saved_record.request_id, \
            "Request ID should be preserved"
        assert retrieved_record.timestamp == saved_record.timestamp, \
            "Timestamp should be preserved"
        assert retrieved_record.status == saved_record.status, \
            "Status should be preserved"
        assert retrieved_record.resource_usage == saved_record.resource_usage, \
            "Resource usage should be preserved"
        assert retrieved_record.duration_ms == saved_record.duration_ms, \
            "Duration should be preserved"
        
        # Clean up
        session.close()
    
    # Feature: llm-python-executor, Property 20: Job history contains metadata
    @given(
        execution_results_list=st.lists(execution_results(), min_size=1, max_size=20),
        code=code_samples()
    )
    @settings(max_examples=50)
    def test_job_history_list_all_contain_metadata(
        self,
        execution_results_list,
        code
    ):
        """
        Property 20: Job history contains metadata (list query)
        
        For any list of job executions stored in history, all records
        must contain the required metadata fields.
        
        This test verifies that:
        1. Multiple records can be stored
        2. Querying all records returns all saved records
        3. All returned records contain required metadata fields
        
        Validates: Requirements 6.3
        """
        # Arrange - Create a fresh database for this test
        db_manager = DatabaseManager(database_url="sqlite:///:memory:")
        db_manager.create_tables()
        session = db_manager.get_session()
        repository = JobHistoryRepository(session)
        
        # Act - Save multiple execution results
        for execution_result in execution_results_list:
            repository.save_execution(
                execution_result=execution_result,
                code=code,
                classification="lightweight",
                resource_usage={"timeout": 30}
            )
        
        # Retrieve all records
        all_records = repository.get_all(limit=100, offset=0)
        
        # Assert - Verify all records contain required metadata
        assert len(all_records) == len(execution_results_list), \
            f"Should retrieve all saved records: expected {len(execution_results_list)}, got {len(all_records)}"
        
        for record in all_records:
            # Verify required metadata fields
            assert record.timestamp is not None, "Each record must have timestamp"
            assert record.status is not None, "Each record must have status"
            assert record.resource_usage is not None, "Each record must have resource_usage"
            assert record.request_id is not None, "Each record must have request_id"
            assert record.duration_ms is not None, "Each record must have duration_ms"
            
            # Verify timestamp is a datetime object
            assert isinstance(record.timestamp, datetime), \
                "Timestamp must be a datetime object"
            
            # Verify resource_usage is valid JSON
            parsed_resource_usage = json.loads(record.resource_usage)
            assert isinstance(parsed_resource_usage, dict), \
                "Resource usage must be a dictionary"
        
        # Clean up
        session.close()
        db_manager.close()
