"""Property-based tests for Secure Executor.

This module contains property-based tests that verify the correctness
properties of the SecureExecutor for code execution.
"""

import time
from hypothesis import given, settings, strategies as st

from llm_executor.executor_service.secure_executor import SecureExecutor
from llm_executor.shared.models import ExecutionStatus


# ============================================================================
# Custom Strategies for Code Generation
# ============================================================================

@st.composite
def code_that_times_out(draw):
    """Generate Python code that will exceed timeout."""
    timeout_patterns = [
        # Infinite loops
        "while True:\n    pass",
        "while True:\n    x = 1 + 1",
        "for i in range(10**9):\n    pass",
        # Long-running operations
        "import time\ntime.sleep(100)",
        "import time\nfor i in range(1000):\n    time.sleep(0.1)",
        # CPU-intensive infinite loop
        "x = 0\nwhile True:\n    x = x + 1",
        # Long computation
        "result = sum(range(10**9))",
    ]
    return draw(st.sampled_from(timeout_patterns))


@st.composite
def code_with_output(draw):
    """Generate Python code that produces stdout output."""
    output_patterns = [
        "print('hello world')",
        "print('line1')\nprint('line2')\nprint('line3')",
        "for i in range(5):\n    print(f'Number: {i}')",
        "import sys\nsys.stdout.write('output\\n')",
        "result = 1 + 1\nprint(f'Result: {result}')",
        "print('test' * 10)",
        "x = [1, 2, 3, 4, 5]\nfor item in x:\n    print(item)",
        "print('Start')\nprint('Middle')\nprint('End')",
    ]
    return draw(st.sampled_from(output_patterns))


@st.composite
def code_with_stderr(draw):
    """Generate Python code that produces stderr output."""
    stderr_patterns = [
        "import sys\nsys.stderr.write('error message\\n')",
        "import sys\nprint('error', file=sys.stderr)",
        "import warnings\nwarnings.warn('warning message')",
        # Code that raises exceptions
        "raise ValueError('test error')",
        "x = 1 / 0",
        "undefined_variable",
        "import sys\nsys.stderr.write('line1\\n')\nsys.stderr.write('line2\\n')",
    ]
    return draw(st.sampled_from(stderr_patterns))


@st.composite
def code_with_both_outputs(draw):
    """Generate Python code that produces both stdout and stderr."""
    both_patterns = [
        "print('stdout')\nimport sys\nsys.stderr.write('stderr\\n')",
        "print('normal')\nraise ValueError('error')",
        "import sys\nprint('out')\nprint('err', file=sys.stderr)",
        "for i in range(3):\n    print(f'stdout {i}')\nimport sys\nsys.stderr.write('stderr\\n')",
    ]
    return draw(st.sampled_from(both_patterns))


@st.composite
def fast_executable_code(draw):
    """Generate Python code that executes quickly."""
    fast_patterns = [
        "result = 1 + 1",
        "result = sum(range(100))",
        "x = [i**2 for i in range(10)]",
        "import math\nresult = math.sqrt(16)",
        "result = 'hello' * 5",
        "x = {'a': 1, 'b': 2}\nresult = x['a']",
        "def func():\n    return 42\nresult = func()",
    ]
    return draw(st.sampled_from(fast_patterns))


@st.composite
def request_id_strategy(draw):
    """Generate valid request IDs."""
    prefix = draw(st.sampled_from(["req", "exec", "test"]))
    number = draw(st.integers(min_value=1, max_value=999999))
    return f"{prefix}-{number}"


# ============================================================================
# Property 10: Timeout terminates execution
# Validates: Requirements 3.4
# ============================================================================

# Feature: llm-python-executor, Property 10: Timeout terminates execution
@given(
    code=code_that_times_out(),
    request_id=request_id_strategy(),
    timeout=st.integers(min_value=1, max_value=2)
)
@settings(max_examples=20, deadline=None)
def test_timeout_terminates_execution(code, request_id, timeout):
    """
    Property: For any code execution that exceeds the configured timeout,
    the Executor Service must terminate the process and return a timeout error.
    
    This test verifies that:
    1. Execution is terminated when timeout is exceeded
    2. Status is set to TIMEOUT
    3. Execution completes within reasonable time after timeout
    4. Partial output (if any) is captured
    """
    executor = SecureExecutor(default_timeout=timeout)
    
    # Measure actual execution time
    start_time = time.perf_counter()
    result = executor.execute(code, request_id, timeout=timeout)
    end_time = time.perf_counter()
    
    actual_duration_seconds = end_time - start_time
    
    # Verify timeout was enforced
    assert result.status == ExecutionStatus.TIMEOUT, \
        f"Code that times out must have TIMEOUT status, got {result.status}"
    
    # Verify execution was terminated within reasonable time
    # Allow 2 seconds grace period for subprocess cleanup
    assert actual_duration_seconds <= (timeout + 2), \
        f"Execution should terminate near timeout ({timeout}s), took {actual_duration_seconds:.2f}s"
    
    # Verify exit code indicates failure
    assert result.exit_code == -1, \
        f"Timeout should result in exit code -1, got {result.exit_code}"
    
    # Verify stderr contains timeout message
    assert "timed out" in result.stderr.lower() or "timeout" in result.stderr.lower(), \
        f"Stderr should mention timeout: {result.stderr}"
    
    # Verify request_id is preserved
    assert result.request_id == request_id, \
        f"Request ID should be preserved: expected {request_id}, got {result.request_id}"
    
    # Verify duration is recorded (should be close to timeout * 1000 ms)
    assert result.duration_ms > 0, \
        "Duration must be recorded"
    assert result.duration_ms >= (timeout * 1000 - 100), \
        f"Duration should be at least {timeout * 1000}ms, got {result.duration_ms}ms"


# ============================================================================
# Property 11: Output capture completeness
# Validates: Requirements 3.5
# ============================================================================

# Feature: llm-python-executor, Property 11: Output capture completeness
@given(
    code=code_with_output(),
    request_id=request_id_strategy()
)
@settings(max_examples=100, deadline=None)
def test_stdout_capture_completeness(code, request_id):
    """
    Property: For any code that writes to stdout, the execution result
    must contain the complete output in the stdout field.
    
    This test verifies that all stdout output is captured correctly.
    """
    executor = SecureExecutor(default_timeout=5)
    result = executor.execute(code, request_id, timeout=5)
    
    # Verify stdout is captured
    assert result.stdout is not None, \
        "Stdout field must be present"
    
    # For successful executions with print statements, stdout should not be empty
    if result.status == ExecutionStatus.SUCCESS and "print" in code:
        assert len(result.stdout) > 0, \
            f"Code with print statements should produce stdout output: {code}"
    
    # Verify request_id is preserved
    assert result.request_id == request_id, \
        f"Request ID should be preserved"


# Feature: llm-python-executor, Property 11: Output capture completeness
@given(
    code=code_with_stderr(),
    request_id=request_id_strategy()
)
@settings(max_examples=100, deadline=None)
def test_stderr_capture_completeness(code, request_id):
    """
    Property: For any code that writes to stderr or raises exceptions,
    the execution result must contain the complete error output in the
    stderr field.
    
    This test verifies that all stderr output is captured correctly.
    """
    executor = SecureExecutor(default_timeout=5)
    result = executor.execute(code, request_id, timeout=5)
    
    # Verify stderr is captured
    assert result.stderr is not None, \
        "Stderr field must be present"
    
    # Code that writes to stderr or raises exceptions should have stderr output
    assert len(result.stderr) > 0, \
        f"Code with stderr output should produce stderr: {code}"
    
    # Verify request_id is preserved
    assert result.request_id == request_id, \
        f"Request ID should be preserved"


# Feature: llm-python-executor, Property 11: Output capture completeness
@given(
    code=code_with_both_outputs(),
    request_id=request_id_strategy()
)
@settings(max_examples=100, deadline=None)
def test_both_outputs_captured(code, request_id):
    """
    Property: For any code that writes to both stdout and stderr,
    the execution result must contain both outputs in their respective fields.
    
    This test verifies that stdout and stderr are captured independently
    and completely.
    """
    executor = SecureExecutor(default_timeout=5)
    result = executor.execute(code, request_id, timeout=5)
    
    # Verify both outputs are present
    assert result.stdout is not None, \
        "Stdout field must be present"
    assert result.stderr is not None, \
        "Stderr field must be present"
    
    # At least one should have content (depending on execution success)
    assert len(result.stdout) > 0 or len(result.stderr) > 0, \
        f"Code should produce some output: {code}"
    
    # Verify request_id is preserved
    assert result.request_id == request_id, \
        f"Request ID should be preserved"


# ============================================================================
# Property 19: Execution duration is recorded
# Validates: Requirements 6.2
# ============================================================================

# Feature: llm-python-executor, Property 19: Execution duration is recorded
@given(
    code=st.one_of(
        fast_executable_code(),
        code_with_output(),
        code_with_stderr()
    ),
    request_id=request_id_strategy()
)
@settings(max_examples=100, deadline=None)
def test_execution_duration_recorded(code, request_id):
    """
    Property: For any code execution that completes, the system must
    record the execution duration in milliseconds in the execution result.
    
    This test verifies that:
    1. Duration is always recorded
    2. Duration is in milliseconds
    3. Duration is positive
    4. Duration is reasonable (not wildly inaccurate)
    """
    executor = SecureExecutor(default_timeout=5)
    
    # Measure execution time externally
    start_time = time.perf_counter()
    result = executor.execute(code, request_id, timeout=5)
    end_time = time.perf_counter()
    
    actual_duration_ms = (end_time - start_time) * 1000
    
    # Verify duration is recorded
    assert result.duration_ms is not None, \
        "Duration must be recorded"
    
    # Verify duration is positive
    assert result.duration_ms > 0, \
        f"Duration must be positive, got {result.duration_ms}ms"
    
    # Verify duration is in reasonable range (within 1000ms of actual)
    # This accounts for measurement differences and overhead
    assert abs(result.duration_ms - actual_duration_ms) < 1000, \
        f"Recorded duration ({result.duration_ms}ms) should be close to actual ({actual_duration_ms:.0f}ms)"
    
    # Verify duration is recorded in milliseconds (not seconds)
    # Fast code should complete in less than 5000ms
    if "sleep" not in code.lower() and "while true" not in code.lower():
        assert result.duration_ms < 5000, \
            f"Fast code should complete quickly, got {result.duration_ms}ms"
    
    # Verify request_id is preserved
    assert result.request_id == request_id, \
        f"Request ID should be preserved"


# ============================================================================
# Additional Property: Successful execution returns correct status
# ============================================================================

# Feature: llm-python-executor, Property: Successful execution status
@given(
    code=fast_executable_code(),
    request_id=request_id_strategy()
)
@settings(max_examples=100, deadline=None)
def test_successful_execution_status(code, request_id):
    """
    Property: For any valid code that executes successfully without errors,
    the execution result must have SUCCESS status and exit code 0.
    
    This test verifies that successful executions are correctly identified.
    """
    executor = SecureExecutor(default_timeout=5)
    result = executor.execute(code, request_id, timeout=5)
    
    # Verify successful execution
    assert result.status == ExecutionStatus.SUCCESS, \
        f"Valid code should execute successfully, got {result.status}"
    
    # Verify exit code is 0
    assert result.exit_code == 0, \
        f"Successful execution should have exit code 0, got {result.exit_code}"
    
    # Verify no stderr for successful execution
    # (some warnings might appear, so we just check it's not an error)
    if result.stderr:
        assert "error" not in result.stderr.lower() or "traceback" not in result.stderr.lower(), \
            f"Successful execution should not have errors in stderr: {result.stderr}"
    
    # Verify request_id is preserved
    assert result.request_id == request_id, \
        f"Request ID should be preserved"


# ============================================================================
# Property 8: Lightweight code uses restricted namespace
# Validates: Requirements 3.1
# ============================================================================

@st.composite
def code_accessing_environment(draw):
    """Generate Python code that attempts to access environment variables or system resources."""
    env_access_patterns = [
        # Try to access environment variables
        "import os\nresult = os.environ.get('PATH', 'not found')",
        "import os\nresult = os.getenv('HOME', 'not found')",
        "import os\nresult = os.environ.get('USER', 'not found')",
        "import os\nresult = list(os.environ.keys())",
        # Try to access system information
        "import os\nresult = os.getcwd()",
        "import sys\nresult = sys.path",
        "import sys\nresult = sys.executable",
        # Simple code that should work in restricted environment
        "result = 1 + 1",
        "import sys\nresult = sys.version",
    ]
    return draw(st.sampled_from(env_access_patterns))


# Feature: llm-python-executor, Property 8: Lightweight code uses restricted namespace
@given(
    code=code_accessing_environment(),
    request_id=request_id_strategy(),
    timeout=st.integers(min_value=5, max_value=10)
)
@settings(max_examples=100, deadline=None)
def test_lightweight_code_uses_restricted_namespace(code, request_id, timeout):
    """
    Property: For any code classified as lightweight, execution must occur
    in a subprocess with a restricted namespace and timeout enforcement.
    
    This test verifies that:
    1. Code executes in a restricted environment (limited env vars)
    2. Timeout is enforced
    3. Environment variables are restricted (no PATH, limited vars)
    4. Execution completes within timeout or returns timeout status
    """
    executor = SecureExecutor(default_timeout=timeout)
    
    # Execute code
    result = executor.execute(code, request_id, timeout=timeout)
    
    # Verify execution completed (either success, failure, or timeout)
    assert result.status in [ExecutionStatus.SUCCESS, ExecutionStatus.FAILED, ExecutionStatus.TIMEOUT], \
        f"Execution must have a valid status, got {result.status}"
    
    # Verify timeout was enforced (if code didn't complete, it should timeout)
    if result.status == ExecutionStatus.TIMEOUT:
        assert result.exit_code == -1, \
            f"Timeout should result in exit code -1, got {result.exit_code}"
    
    # Verify restricted environment by checking that PATH is not available
    # If code tries to access PATH, it should either:
    # 1. Get 'not found' (our default in the test code)
    # 2. Get None/empty (if PATH is not in restricted env)
    if "PATH" in code and "environ" in code:
        # Code that successfully accesses PATH should show it's restricted
        if result.status == ExecutionStatus.SUCCESS:
            # The restricted environment should not have PATH
            # So the code should return 'not found' or similar
            assert "not found" in result.stdout.lower() or result.stdout == "" or "None" in result.stdout, \
                f"PATH should not be available in restricted environment, got stdout: {result.stdout}"
    
    # Verify request_id is preserved
    assert result.request_id == request_id, \
        f"Request ID should be preserved"
    
    # Verify duration is recorded
    assert result.duration_ms > 0, \
        "Duration must be recorded"
    
    # Verify the executor uses restricted environment
    restricted_env = executor.get_restricted_env()
    assert "PATH" not in restricted_env, \
        "Restricted environment should not contain PATH"
    assert "PYTHONHASHSEED" in restricted_env, \
        "Restricted environment should contain PYTHONHASHSEED"
    assert "PYTHONDONTWRITEBYTECODE" in restricted_env, \
        "Restricted environment should contain PYTHONDONTWRITEBYTECODE"
