"""Property-based tests for Code Validator.

This module contains property-based tests that verify the correctness
properties of the AST-based code validator.
"""

import ast
import time
from hypothesis import given, settings, strategies as st

from llm_executor.executor.validator import CodeValidator
from llm_executor.shared.models import ValidationResult


# ============================================================================
# Custom Strategies for Code Generation
# ============================================================================

@st.composite
def valid_python_code(draw):
    """Generate valid Python code strings."""
    code_samples = [
        "result = 1 + 1",
        "result = [x**2 for x in range(10)]",
        "result = sum(range(100))",
        "x = 5\ny = 10\nresult = x + y",
        "import math\nresult = math.sqrt(16)",
        "from datetime import datetime\nresult = datetime.now()",
        "result = {'key': 'value'}",
        "result = list(map(lambda x: x * 2, [1, 2, 3]))",
        "def func():\n    return 42\nresult = func()",
        "class MyClass:\n    pass\nresult = MyClass()",
    ]
    return draw(st.sampled_from(code_samples))


@st.composite
def code_with_file_operations(draw):
    """Generate Python code containing file I/O operations."""
    file_ops = [
        "open('file.txt', 'r')",
        "with open('data.txt') as f:\n    content = f.read()",
        "file = open('output.txt', 'w')\nfile.write('data')",
        "f = open('test.txt')\ndata = f.read()\nf.close()",
        "from pathlib import Path\np = Path('file.txt')",
        "import io\nbuffer = io.StringIO()",
    ]
    return draw(st.sampled_from(file_ops))


@st.composite
def code_with_os_commands(draw):
    """Generate Python code containing OS command execution."""
    os_ops = [
        "import os\nos.system('ls')",
        "import subprocess\nsubprocess.run(['echo', 'hello'])",
        "import os\nos.popen('pwd')",
        "eval('1 + 1')",
        "exec('x = 5')",
        "compile('x = 1', '<string>', 'exec')",
        "__import__('os')",
    ]
    return draw(st.sampled_from(os_ops))


@st.composite
def code_with_network_operations(draw):
    """Generate Python code containing network operations."""
    network_ops = [
        "import socket\ns = socket.socket()",
        "import urllib.request\nurllib.request.urlopen('http://example.com')",
        "import requests\nrequests.get('http://example.com')",
        "from urllib import request\nrequest.urlopen('http://test.com')",
        "import http.client\nconn = http.client.HTTPConnection('example.com')",
        "import aiohttp\nsession = aiohttp.ClientSession()",
    ]
    return draw(st.sampled_from(network_ops))


@st.composite
def code_with_unauthorized_imports(draw):
    """Generate Python code with unauthorized imports."""
    unauthorized = [
        "import os",
        "import sys",
        "import subprocess",
        "import socket",
        "import pickle",
        "import ctypes",
        "import multiprocessing",
        "import threading",
        "from os import system",
        "from subprocess import run",
        "import shutil",
        "import tempfile",
    ]
    return draw(st.sampled_from(unauthorized))


@st.composite
def code_with_authorized_imports(draw):
    """Generate Python code with authorized imports."""
    authorized = [
        "import math",
        "import random",
        "import datetime",
        "import json",
        "import re",
        "from collections import defaultdict",
        "from itertools import chain",
        "import functools",
        "import statistics",
        "from typing import List",
    ]
    return draw(st.sampled_from(authorized))


@st.composite
def code_with_restricted_operations(draw):
    """Generate code with any type of restricted operation."""
    strategy = draw(st.sampled_from([
        code_with_file_operations(),
        code_with_os_commands(),
        code_with_network_operations(),
    ]))
    return strategy


# ============================================================================
# Property 4: AST parsing performance
# Validates: Requirements 2.1
# ============================================================================

# Feature: llm-python-executor, Property 4: AST parsing performance
@given(code=valid_python_code())
@settings(max_examples=100)
def test_ast_parsing_performance(code):
    """
    Property: For any valid Python code string, AST parsing must complete
    within 30 milliseconds.
    
    This test verifies that the validator can parse code quickly enough
    to meet the performance requirements.
    """
    validator = CodeValidator()
    
    # Measure parsing time
    start_time = time.perf_counter()
    result = validator.validate(code)
    end_time = time.perf_counter()
    
    duration_ms = (end_time - start_time) * 1000
    
    # Verify parsing completed within 30ms
    assert duration_ms < 30, \
        f"AST parsing took {duration_ms:.2f}ms, exceeds 30ms limit"
    
    # Verify we got a valid result
    assert isinstance(result, ValidationResult), \
        "Validator must return a ValidationResult"


# ============================================================================
# Property 5: Restricted operations are rejected
# Validates: Requirements 2.2
# ============================================================================

# Feature: llm-python-executor, Property 5: Restricted operations are rejected
@given(code=code_with_file_operations())
@settings(max_examples=100)
def test_file_operations_rejected(code):
    """
    Property: For any code containing file I/O operations, the validator
    must reject the code and return specific error messages.
    
    This test verifies that file operations are consistently detected
    and rejected.
    """
    validator = CodeValidator()
    result = validator.validate(code)
    
    # Verify code is rejected
    assert not result.is_valid, \
        f"File I/O code should be rejected: {code}"
    
    # Verify errors are present
    assert len(result.errors) > 0, \
        "Rejected code must have error messages"
    
    # Verify error message mentions file operations or unauthorized imports
    # (file I/O can be caught by either the file I/O rule or import rule)
    error_text = " ".join(result.errors).lower()
    assert any(keyword in error_text for keyword in ["file", "i/o", "open", "read", "write", "import", "pathlib", "io"]), \
        f"Error message should mention file operations or imports: {result.errors}"


# Feature: llm-python-executor, Property 5: Restricted operations are rejected
@given(code=code_with_os_commands())
@settings(max_examples=100)
def test_os_commands_rejected(code):
    """
    Property: For any code containing OS command execution, the validator
    must reject the code and return specific error messages.
    
    This test verifies that OS commands are consistently detected
    and rejected.
    """
    validator = CodeValidator()
    result = validator.validate(code)
    
    # Verify code is rejected
    assert not result.is_valid, \
        f"OS command code should be rejected: {code}"
    
    # Verify errors are present
    assert len(result.errors) > 0, \
        "Rejected code must have error messages"
    
    # Verify error message mentions OS operations or specific commands
    error_text = " ".join(result.errors).lower()
    assert any(keyword in error_text for keyword in ["os", "command", "execution", "system", "subprocess", "eval", "exec", "compile", "import"]), \
        f"Error message should mention OS operations: {result.errors}"


# Feature: llm-python-executor, Property 5: Restricted operations are rejected
@given(code=code_with_network_operations())
@settings(max_examples=100)
def test_network_operations_rejected(code):
    """
    Property: For any code containing network operations, the validator
    must reject the code and return specific error messages.
    
    This test verifies that network operations are consistently detected
    and rejected.
    """
    validator = CodeValidator()
    result = validator.validate(code)
    
    # Verify code is rejected
    assert not result.is_valid, \
        f"Network operation code should be rejected: {code}"
    
    # Verify errors are present
    assert len(result.errors) > 0, \
        "Rejected code must have error messages"
    
    # Verify error message mentions network operations
    error_text = " ".join(result.errors).lower()
    assert any(keyword in error_text for keyword in ["network", "socket", "http", "request", "url"]), \
        f"Error message should mention network operations: {result.errors}"


# ============================================================================
# Property 6: Unauthorized imports are detected
# Validates: Requirements 2.3
# ============================================================================

# Feature: llm-python-executor, Property 6: Unauthorized imports are detected
@given(code=code_with_unauthorized_imports())
@settings(max_examples=100)
def test_unauthorized_imports_detected(code):
    """
    Property: For any code containing unauthorized imports, the validator
    must reject the code and identify the specific prohibited import names
    in the error message.
    
    This test verifies that unauthorized imports are consistently detected
    and reported with specific module names.
    """
    validator = CodeValidator()
    result = validator.validate(code)
    
    # Verify code is rejected
    assert not result.is_valid, \
        f"Code with unauthorized imports should be rejected: {code}"
    
    # Verify errors are present
    assert len(result.errors) > 0, \
        "Rejected code must have error messages"
    
    # Verify error message mentions imports
    error_text = " ".join(result.errors).lower()
    assert "import" in error_text, \
        f"Error message should mention imports: {result.errors}"
    
    # Extract the imported module name from the code
    try:
        tree = ast.parse(code)
        imported_modules = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_modules.add(node.module.split('.')[0])
        
        # Verify at least one imported module is mentioned in errors
        assert any(module in error_text for module in imported_modules), \
            f"Error should mention the unauthorized module(s): {imported_modules}, got: {result.errors}"
    except SyntaxError:
        # If code has syntax errors, that's acceptable for this test
        pass


# Feature: llm-python-executor, Property 6: Unauthorized imports are detected
@given(code=code_with_authorized_imports())
@settings(max_examples=100)
def test_authorized_imports_accepted(code):
    """
    Property: For any code containing only authorized imports, the validator
    must accept the code (assuming no other violations).
    
    This test verifies that the allowlist works correctly and doesn't
    reject safe imports.
    """
    validator = CodeValidator()
    result = validator.validate(code)
    
    # Verify code is accepted (no import-related errors)
    # Note: We check that there are no import-related errors specifically
    if not result.is_valid:
        error_text = " ".join(result.errors).lower()
        assert "import" not in error_text, \
            f"Authorized imports should not trigger import errors: {result.errors}"
