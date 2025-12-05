"""Property-based tests for Kubernetes Job Manager.

This module contains property-based tests that verify the correctness
properties of the KubernetesJobManager for heavy job creation.
"""

from hypothesis import given, settings, strategies as st
from unittest.mock import Mock, patch, MagicMock
from kubernetes.client.rest import ApiException

from llm_executor.executor_service.kubernetes_job_manager import KubernetesJobManager
from llm_executor.shared.models import JobCreationRequest, ResourceLimits


# ============================================================================
# Custom Strategies for Job Creation
# ============================================================================

@st.composite
def heavy_code_strategy(draw):
    """Generate Python code that would be classified as heavy."""
    heavy_patterns = [
        # Heavy library imports
        "import pandas as pd\ndf = pd.DataFrame({'a': [1, 2, 3]})\nprint(df)",
        "import polars as pl\ndf = pl.DataFrame({'a': [1, 2, 3]})\nprint(df)",
        "import modin.pandas as pd\ndf = pd.DataFrame({'a': [1, 2, 3]})",
        "import pyarrow as pa\ntable = pa.table({'a': [1, 2, 3]})",
        "import dask.dataframe as dd\ndf = dd.from_dict({'a': [1, 2, 3]}, npartitions=1)",
        # File I/O operations
        "with open('data.csv', 'w') as f:\n    f.write('test')",
        "import pandas as pd\ndf = pd.read_csv('data.csv')",
        # Large data processing
        "import pandas as pd\ndf = pd.DataFrame({'a': range(1000000)})\nresult = df.sum()",
        "import numpy as np\ndata = np.random.rand(1000000)\nresult = data.mean()",
    ]
    return draw(st.sampled_from(heavy_patterns))


@st.composite
def request_id_strategy(draw):
    """Generate valid request IDs."""
    prefix = draw(st.sampled_from(["req", "exec", "test", "job"]))
    number = draw(st.integers(min_value=1, max_value=999999))
    suffix = draw(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=4, max_size=8))
    return f"{prefix}-{number}-{suffix}"


@st.composite
def resource_limits_strategy(draw):
    """Generate valid resource limits."""
    cpu_values = ["1", "2", "4", "8", "16"]
    memory_values = ["2Gi", "4Gi", "8Gi", "16Gi", "32Gi"]
    
    cpu_limit = draw(st.sampled_from(cpu_values))
    memory_limit = draw(st.sampled_from(memory_values))
    
    # Request should be less than or equal to limit
    cpu_request_idx = draw(st.integers(min_value=0, max_value=cpu_values.index(cpu_limit)))
    memory_request_idx = draw(st.integers(min_value=0, max_value=memory_values.index(memory_limit)))
    
    cpu_request = cpu_values[cpu_request_idx]
    memory_request = memory_values[memory_request_idx]
    
    timeout = draw(st.integers(min_value=60, max_value=600))
    
    return ResourceLimits(
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        cpu_request=cpu_request,
        memory_request=memory_request,
        timeout_seconds=timeout,
    )


@st.composite
def job_creation_request_strategy(draw):
    """Generate valid job creation requests."""
    request_id = draw(request_id_strategy())
    code = draw(heavy_code_strategy())
    resource_limits = draw(resource_limits_strategy())
    
    return JobCreationRequest(
        request_id=request_id,
        code=code,
        resource_limits=resource_limits,
    )


# ============================================================================
# Property 14: Heavy code creates Kubernetes Job
# Validates: Requirements 4.3, 8.1
# ============================================================================

# Feature: llm-python-executor, Property 14: Heavy code creates Kubernetes Job
@given(
    request=job_creation_request_strategy(),
    namespace=st.sampled_from(["default", "production", "staging", "development"]),
    ttl_seconds=st.integers(min_value=600, max_value=7200)
)
@settings(max_examples=100, deadline=None)
def test_heavy_code_creates_kubernetes_job(request, namespace, ttl_seconds):
    """
    Property: For any code classified as heavy, the Executor Service must
    create a Kubernetes Job with CPU and memory limits matching the
    configured resource limits.
    
    This test verifies that:
    1. Job is created with correct resource limits
    2. Job has proper security context
    3. Job has TTL configured for cleanup
    4. Job has PreStop hooks configured
    5. Job name is based on request_id
    6. Job includes environment variables for code execution
    """
    # Mock the Kubernetes API client
    with patch('llm_executor.executor_service.kubernetes_job_manager.config') as mock_config:
        
        # Setup mock configuration
        mock_config.load_incluster_config.side_effect = Exception("Not in cluster")
        mock_config.load_kube_config.return_value = None
        
        # Initialize KubernetesJobManager
        job_manager = KubernetesJobManager(
            namespace=namespace,
            image="heavy-executor:latest",
            ttl_seconds=ttl_seconds,
        )
        
        # Mock the batch API's create method to capture the job spec
        with patch.object(job_manager.batch_v1, 'create_namespaced_job') as mock_create:
            # Create a mock response for job creation
            mock_job_response = MagicMock()
            mock_job_response.metadata.name = f"heavy-executor-{request.request_id}"
            mock_create.return_value = mock_job_response
            
            # Create the job
            result = job_manager.create_job(request)
            
            # Verify job creation was called
            assert mock_create.called, \
                "create_namespaced_job should be called"
            
            # Get the job specification that was passed
            call_args = mock_create.call_args
            assert call_args is not None, "Job creation should have been called"
            
            job_spec = call_args.kwargs['body']
            namespace_arg = call_args.kwargs['namespace']
            
            # Verify namespace
            assert namespace_arg == namespace, \
                f"Job should be created in namespace {namespace}, got {namespace_arg}"
            
            # Verify job metadata
            assert job_spec.metadata.name is not None, \
                "Job must have a name"
            assert "heavy-executor" in job_spec.metadata.name, \
                f"Job name should contain 'heavy-executor', got {job_spec.metadata.name}"
        
            # Verify job has labels
            assert job_spec.metadata.labels is not None, \
                "Job must have labels"
            assert "app" in job_spec.metadata.labels, \
                "Job must have 'app' label"
            assert job_spec.metadata.labels["app"] == "heavy-executor", \
                "Job 'app' label should be 'heavy-executor'"
            
            # Verify TTL configuration
            assert job_spec.spec.ttl_seconds_after_finished == ttl_seconds, \
                f"Job TTL should be {ttl_seconds}, got {job_spec.spec.ttl_seconds_after_finished}"
            
            # Verify pod template
            pod_template = job_spec.spec.template
            assert pod_template is not None, \
                "Job must have pod template"
            
            # Verify pod spec
            pod_spec = pod_template.spec
            assert pod_spec is not None, \
                "Pod template must have spec"
            assert pod_spec.restart_policy == "Never", \
                f"Pod restart policy should be 'Never', got {pod_spec.restart_policy}"
            
            # Verify container configuration
            assert len(pod_spec.containers) > 0, \
                "Pod must have at least one container"
            
            container = pod_spec.containers[0]
            
            # Verify container name and image
            assert container.name == "executor", \
                f"Container name should be 'executor', got {container.name}"
            assert container.image == "heavy-executor:latest", \
                f"Container image should be 'heavy-executor:latest', got {container.image}"
            
            # Verify environment variables
            assert container.env is not None, \
                "Container must have environment variables"
            
            env_dict = {env.name: env.value for env in container.env}
            assert "CODE" in env_dict, \
                "Container must have CODE environment variable"
            assert env_dict["CODE"] == request.code, \
                f"CODE env var should match request code"
            assert "REQUEST_ID" in env_dict, \
                "Container must have REQUEST_ID environment variable"
            assert env_dict["REQUEST_ID"] == request.request_id, \
                f"REQUEST_ID env var should match request ID"
            assert "TIMEOUT" in env_dict, \
                "Container must have TIMEOUT environment variable"
            assert env_dict["TIMEOUT"] == str(request.resource_limits.timeout_seconds), \
                f"TIMEOUT env var should match resource limits"
            
            # Verify resource limits
            assert container.resources is not None, \
                "Container must have resource configuration"
            assert container.resources.limits is not None, \
                "Container must have resource limits"
            assert container.resources.requests is not None, \
                "Container must have resource requests"
            
            # Verify CPU limits
            assert "cpu" in container.resources.limits, \
                "Container must have CPU limit"
            assert container.resources.limits["cpu"] == request.resource_limits.cpu_limit, \
                f"CPU limit should be {request.resource_limits.cpu_limit}, got {container.resources.limits['cpu']}"
            
            # Verify memory limits
            assert "memory" in container.resources.limits, \
                "Container must have memory limit"
            assert container.resources.limits["memory"] == request.resource_limits.memory_limit, \
                f"Memory limit should be {request.resource_limits.memory_limit}, got {container.resources.limits['memory']}"
            
            # Verify CPU requests
            assert "cpu" in container.resources.requests, \
                "Container must have CPU request"
            assert container.resources.requests["cpu"] == request.resource_limits.cpu_request, \
                f"CPU request should be {request.resource_limits.cpu_request}, got {container.resources.requests['cpu']}"
            
            # Verify memory requests
            assert "memory" in container.resources.requests, \
                "Container must have memory request"
            assert container.resources.requests["memory"] == request.resource_limits.memory_request, \
                f"Memory request should be {request.resource_limits.memory_request}, got {container.resources.requests['memory']}"
            
            # Verify security context
            assert container.security_context is not None, \
                "Container must have security context"
            assert container.security_context.run_as_non_root is True, \
                "Container must run as non-root"
            assert container.security_context.read_only_root_filesystem is True, \
                "Container must have read-only root filesystem"
            assert container.security_context.allow_privilege_escalation is False, \
                "Container must not allow privilege escalation"
            assert container.security_context.run_as_user == 1000, \
                f"Container should run as user 1000, got {container.security_context.run_as_user}"
            
            # Verify PreStop lifecycle hook
            assert container.lifecycle is not None, \
                "Container must have lifecycle configuration"
            assert container.lifecycle.pre_stop is not None, \
                "Container must have PreStop hook"
            assert container.lifecycle.pre_stop._exec is not None, \
                "PreStop hook must have exec action"
            assert container.lifecycle.pre_stop._exec.command is not None, \
                "PreStop hook must have command"
            assert len(container.lifecycle.pre_stop._exec.command) > 0, \
                "PreStop hook command must not be empty"
            
            # Verify response
            assert result.job_id is not None, \
                "Response must include job_id"
            assert result.status == "created", \
                f"Response status should be 'created', got {result.status}"
            assert result.created_at is not None, \
                "Response must include created_at timestamp"
            
            # Verify job_id format (should be valid Kubernetes name)
            assert len(result.job_id) <= 63, \
                f"Job ID must be <= 63 characters, got {len(result.job_id)}"
            assert result.job_id[0].isalnum(), \
                f"Job ID must start with alphanumeric character, got {result.job_id[0]}"
            assert all(c.isalnum() or c == '-' for c in result.job_id), \
                f"Job ID must contain only alphanumeric and hyphens, got {result.job_id}"


# ============================================================================
# Additional Property: Job creation handles API errors gracefully
# ============================================================================

# Feature: llm-python-executor, Property: Job creation error handling
@given(
    request=job_creation_request_strategy(),
)
@settings(max_examples=50, deadline=None)
def test_job_creation_handles_api_errors(request):
    """
    Property: For any job creation request that fails due to Kubernetes API errors,
    the system must raise an appropriate exception and log the error.
    
    This test verifies that API errors are handled correctly.
    """
    # Mock the Kubernetes API client to raise an error
    with patch('llm_executor.executor_service.kubernetes_job_manager.config') as mock_config, \
         patch('llm_executor.executor_service.kubernetes_job_manager.client') as mock_client:
        
        # Setup mock configuration
        mock_config.load_incluster_config.side_effect = Exception("Not in cluster")
        mock_config.load_kube_config.return_value = None
        
        # Setup mock BatchV1Api that raises an error
        mock_batch_api = MagicMock()
        mock_client.BatchV1Api.return_value = mock_batch_api
        
        # Simulate API error
        mock_batch_api.create_namespaced_job.side_effect = ApiException(
            status=500,
            reason="Internal Server Error"
        )
        
        # Initialize KubernetesJobManager
        job_manager = KubernetesJobManager(
            namespace="default",
            image="heavy-executor:latest",
            ttl_seconds=3600,
        )
        
        # Attempt to create job should raise ApiException
        try:
            result = job_manager.create_job(request)
            assert False, "Job creation should raise ApiException"
        except ApiException as e:
            # Verify exception details
            assert e.status == 500, \
                f"Exception status should be 500, got {e.status}"
            assert "Internal Server Error" in str(e), \
                f"Exception should mention error reason"


# ============================================================================
# Property: Job ID generation is valid for Kubernetes
# ============================================================================

# Feature: llm-python-executor, Property: Job ID validation
@given(
    request_id=request_id_strategy(),
)
@settings(max_examples=100, deadline=None)
def test_job_id_generation_is_valid(request_id):
    """
    Property: For any request_id, the generated job_id must be a valid
    Kubernetes resource name.
    
    Kubernetes names must:
    - Be lowercase
    - Contain only alphanumeric characters and hyphens
    - Start with an alphanumeric character
    - Be no more than 63 characters
    """
    # Mock the Kubernetes API client
    with patch('llm_executor.executor_service.kubernetes_job_manager.config') as mock_config, \
         patch('llm_executor.executor_service.kubernetes_job_manager.client') as mock_client:
        
        # Setup mock configuration
        mock_config.load_incluster_config.side_effect = Exception("Not in cluster")
        mock_config.load_kube_config.return_value = None
        
        # Setup mock BatchV1Api
        mock_batch_api = MagicMock()
        mock_client.BatchV1Api.return_value = mock_batch_api
        
        # Initialize KubernetesJobManager
        job_manager = KubernetesJobManager(
            namespace="default",
            image="heavy-executor:latest",
            ttl_seconds=3600,
        )
        
        # Generate job ID
        job_id = job_manager._generate_job_id(request_id)
        
        # Verify job ID is valid
        assert len(job_id) <= 63, \
            f"Job ID must be <= 63 characters, got {len(job_id)}: {job_id}"
        
        assert job_id[0].isalnum(), \
            f"Job ID must start with alphanumeric character, got '{job_id[0]}' in {job_id}"
        
        assert all(c.isalnum() or c == '-' for c in job_id), \
            f"Job ID must contain only alphanumeric and hyphens, got {job_id}"
        
        assert job_id == job_id.lower(), \
            f"Job ID must be lowercase, got {job_id}"
        
        # Verify it contains the prefix
        assert job_id.startswith("heavy-executor-"), \
            f"Job ID should start with 'heavy-executor-', got {job_id}"



# ============================================================================
# Unit Tests for Job Configuration
# ============================================================================

def test_job_security_configuration():
    """
    Unit test: Verify that created jobs have correct security context and resource limits.
    
    Requirements: 8.2 - Enforce pod-level security policies
    
    This test verifies that:
    1. Security context is properly configured
    2. runAsNonRoot is set to True
    3. readOnlyRootFilesystem is set to True
    4. allowPrivilegeEscalation is set to False
    5. runAsUser is set to 1000
    6. Resource limits match the request
    """
    # Mock the Kubernetes API client
    with patch('llm_executor.executor_service.kubernetes_job_manager.config') as mock_config:
        
        # Setup mock configuration
        mock_config.load_incluster_config.side_effect = Exception("Not in cluster")
        mock_config.load_kube_config.return_value = None
        
        # Initialize KubernetesJobManager
        job_manager = KubernetesJobManager(
            namespace="default",
            image="heavy-executor:latest",
            ttl_seconds=3600,
        )
        
        # Create a test request
        request = JobCreationRequest(
            request_id="test-security-123",
            code="import pandas as pd\nprint('test')",
            resource_limits=ResourceLimits(
                cpu_limit="4",
                memory_limit="8Gi",
                cpu_request="2",
                memory_request="4Gi",
                timeout_seconds=300,
            ),
        )
        
        # Mock the batch API's create method
        with patch.object(job_manager.batch_v1, 'create_namespaced_job') as mock_create:
            mock_job_response = MagicMock()
            mock_job_response.metadata.name = "heavy-executor-test-security-123"
            mock_create.return_value = mock_job_response
            
            # Create the job
            result = job_manager.create_job(request)
            
            # Get the job specification
            call_args = mock_create.call_args
            job_spec = call_args.kwargs['body']
            
            # Extract container from job spec
            container = job_spec.spec.template.spec.containers[0]
            
            # Verify security context
            assert container.security_context is not None, \
                "Container must have security context"
            
            assert container.security_context.run_as_non_root is True, \
                "Security context must set runAsNonRoot to True"
            
            assert container.security_context.read_only_root_filesystem is True, \
                "Security context must set readOnlyRootFilesystem to True"
            
            assert container.security_context.allow_privilege_escalation is False, \
                "Security context must set allowPrivilegeEscalation to False"
            
            assert container.security_context.run_as_user == 1000, \
                "Security context must set runAsUser to 1000"
            
            # Verify resource limits
            assert container.resources.limits["cpu"] == "4", \
                "CPU limit must match request"
            assert container.resources.limits["memory"] == "8Gi", \
                "Memory limit must match request"
            
            # Verify resource requests
            assert container.resources.requests["cpu"] == "2", \
                "CPU request must match request"
            assert container.resources.requests["memory"] == "4Gi", \
                "Memory request must match request"


def test_job_ttl_cleanup():
    """
    Unit test: Verify that completed jobs are configured with TTL for automatic cleanup.
    
    Requirements: 8.3 - Configure TTL for automatic cleanup
    
    This test verifies that:
    1. TTL is set on the job spec
    2. TTL value matches the configured value
    3. TTL is applied to all jobs
    """
    # Mock the Kubernetes API client
    with patch('llm_executor.executor_service.kubernetes_job_manager.config') as mock_config:
        
        # Setup mock configuration
        mock_config.load_incluster_config.side_effect = Exception("Not in cluster")
        mock_config.load_kube_config.return_value = None
        
        # Test with different TTL values
        ttl_values = [600, 1800, 3600, 7200]
        
        for ttl_seconds in ttl_values:
            # Initialize KubernetesJobManager with specific TTL
            job_manager = KubernetesJobManager(
                namespace="default",
                image="heavy-executor:latest",
                ttl_seconds=ttl_seconds,
            )
            
            # Create a test request
            request = JobCreationRequest(
                request_id=f"test-ttl-{ttl_seconds}",
                code="print('test')",
                resource_limits=ResourceLimits(),
            )
            
            # Mock the batch API's create method
            with patch.object(job_manager.batch_v1, 'create_namespaced_job') as mock_create:
                mock_job_response = MagicMock()
                mock_job_response.metadata.name = f"heavy-executor-test-ttl-{ttl_seconds}"
                mock_create.return_value = mock_job_response
                
                # Create the job
                result = job_manager.create_job(request)
                
                # Get the job specification
                call_args = mock_create.call_args
                job_spec = call_args.kwargs['body']
                
                # Verify TTL is set
                assert job_spec.spec.ttl_seconds_after_finished is not None, \
                    "Job must have TTL configured"
                
                assert job_spec.spec.ttl_seconds_after_finished == ttl_seconds, \
                    f"TTL must be {ttl_seconds}, got {job_spec.spec.ttl_seconds_after_finished}"


def test_job_prestop_hooks():
    """
    Unit test: Verify that job pods have PreStop hooks configured.
    
    Requirements: 8.4 - Add PreStop hooks for graceful shutdown
    
    This test verifies that:
    1. PreStop hook is configured on the container
    2. PreStop hook has an exec action
    3. PreStop hook has a command
    """
    # Mock the Kubernetes API client
    with patch('llm_executor.executor_service.kubernetes_job_manager.config') as mock_config:
        
        # Setup mock configuration
        mock_config.load_incluster_config.side_effect = Exception("Not in cluster")
        mock_config.load_kube_config.return_value = None
        
        # Initialize KubernetesJobManager
        job_manager = KubernetesJobManager(
            namespace="default",
            image="heavy-executor:latest",
            ttl_seconds=3600,
        )
        
        # Create a test request
        request = JobCreationRequest(
            request_id="test-prestop-123",
            code="print('test')",
            resource_limits=ResourceLimits(),
        )
        
        # Mock the batch API's create method
        with patch.object(job_manager.batch_v1, 'create_namespaced_job') as mock_create:
            mock_job_response = MagicMock()
            mock_job_response.metadata.name = "heavy-executor-test-prestop-123"
            mock_create.return_value = mock_job_response
            
            # Create the job
            result = job_manager.create_job(request)
            
            # Get the job specification
            call_args = mock_create.call_args
            job_spec = call_args.kwargs['body']
            
            # Extract container from job spec
            container = job_spec.spec.template.spec.containers[0]
            
            # Verify lifecycle configuration exists
            assert container.lifecycle is not None, \
                "Container must have lifecycle configuration"
            
            # Verify PreStop hook exists
            assert container.lifecycle.pre_stop is not None, \
                "Container must have PreStop hook configured"
            
            # Verify PreStop hook has exec action
            assert container.lifecycle.pre_stop._exec is not None, \
                "PreStop hook must have exec action"
            
            # Verify PreStop hook has command
            assert container.lifecycle.pre_stop._exec.command is not None, \
                "PreStop hook must have command"
            
            assert len(container.lifecycle.pre_stop._exec.command) > 0, \
                "PreStop hook command must not be empty"
            
            # Verify command is a list
            assert isinstance(container.lifecycle.pre_stop._exec.command, list), \
                "PreStop hook command must be a list"
