"""Property-based tests for Code Classifier.

This module contains property-based tests that verify the correctness
properties of the code classification system for routing decisions.
"""

import ast
from hypothesis import given, settings, strategies as st

from llm_executor.executor.classifier import CodeClassifier
from llm_executor.shared.models import CodeComplexity


# ============================================================================
# Custom Strategies for Code Generation
# ============================================================================

@st.composite
def code_with_heavy_imports(draw):
    """Generate Python code with heavy library imports."""
    heavy_libraries = ["pandas", "modin", "polars", "pyarrow", "dask", "ray", "pyspark"]
    lib = draw(st.sampled_from(heavy_libraries))
    
    # Generate different import patterns
    import_patterns = [
        f"import {lib}",
        f"import {lib} as lib",
        f"from {lib} import DataFrame",
        f"import {lib}\nresult = {lib}.__version__",
        f"from {lib} import *",
    ]
    
    return draw(st.sampled_from(import_patterns))


@st.composite
def code_with_file_io(draw):
    """Generate Python code with file I/O operations."""
    file_io_patterns = [
        "with open('file.txt', 'r') as f:\n    data = f.read()",
        "f = open('data.txt', 'w')\nf.write('content')\nf.close()",
        "open('test.txt')",
        "file = open('output.csv', 'r')",
        "import pathlib\np = pathlib.Path('file.txt')",
        "from pathlib import Path\nPath('data.txt').read_text()",
        "import io\nbuffer = io.StringIO()",
        "from io import BytesIO\nstream = BytesIO()",
    ]
    
    return draw(st.sampled_from(file_io_patterns))


@st.composite
def lightweight_code(draw):
    """Generate lightweight Python code without heavy operations."""
    lightweight_patterns = [
        "result = 1 + 1",
        "result = [x**2 for x in range(10)]",
        "result = sum(range(100))",
        "import math\nresult = math.sqrt(16)",
        "from datetime import datetime\nresult = datetime.now()",
        "result = {'key': 'value'}",
        "result = list(map(lambda x: x * 2, [1, 2, 3]))",
        "def func():\n    return 42\nresult = func()",
        "x = 5\ny = 10\nresult = x + y",
        "import json\nresult = json.dumps({'a': 1})",
        "from collections import defaultdict\nd = defaultdict(list)",
        "import random\nresult = random.randint(1, 100)",
    ]
    
    return draw(st.sampled_from(lightweight_patterns))


@st.composite
def code_with_simple_loops(draw):
    """Generate code with simple (non-nested) loops."""
    simple_loop_patterns = [
        "for i in range(10):\n    print(i)",
        "result = []\nfor x in range(5):\n    result.append(x * 2)",
        "i = 0\nwhile i < 10:\n    i += 1",
        "total = 0\nfor num in [1, 2, 3, 4, 5]:\n    total += num",
    ]
    
    return draw(st.sampled_from(simple_loop_patterns))


@st.composite
def code_with_complex_loops(draw):
    """Generate code with deeply nested loops (3+ levels)."""
    complex_loop_patterns = [
        # 3-level nested loop
        "for i in range(10):\n    for j in range(10):\n        for k in range(10):\n            result = i * j * k",
        # 4-level nested loop
        "for a in range(5):\n    for b in range(5):\n        for c in range(5):\n            for d in range(5):\n                pass",
        # Mixed for and while loops
        "for i in range(10):\n    j = 0\n    while j < 10:\n        for k in range(10):\n            pass\n        j += 1",
    ]
    
    return draw(st.sampled_from(complex_loop_patterns))


# ============================================================================
# Property 12: Heavy imports trigger heavy classification
# Validates: Requirements 4.1
# ============================================================================

# Feature: llm-python-executor, Property 12: Heavy imports trigger heavy classification
@given(code=code_with_heavy_imports())
@settings(max_examples=100)
def test_heavy_imports_classification(code):
    """
    Property: For any code that imports heavy libraries (pandas, modin, polars,
    pyarrow, dask, ray, pyspark), the classification function must return
    CodeComplexity.HEAVY.
    
    This test verifies that heavy data processing libraries are consistently
    detected and routed to Kubernetes Job execution.
    """
    classifier = CodeClassifier()
    result = classifier.classify(code)
    
    # Verify heavy classification
    assert result == CodeComplexity.HEAVY, \
        f"Code with heavy imports should be classified as HEAVY: {code}"
    
    # Verify the code actually contains a heavy import
    try:
        tree = ast.parse(code)
        has_heavy_import = False
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    if module_name in classifier.HEAVY_IMPORTS:
                        has_heavy_import = True
                        break
            
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    if module_name in classifier.HEAVY_IMPORTS:
                        has_heavy_import = True
                        break
        
        assert has_heavy_import, \
            f"Test code should contain a heavy import: {code}"
    except SyntaxError:
        # If there's a syntax error, the test is still valid
        # as long as the classifier returned HEAVY
        pass


# ============================================================================
# Property 13: File I/O triggers heavy classification
# Validates: Requirements 4.2
# ============================================================================

# Feature: llm-python-executor, Property 13: File I/O triggers heavy classification
@given(code=code_with_file_io())
@settings(max_examples=100)
def test_file_io_classification(code):
    """
    Property: For any code containing file I/O operations (open, read, write),
    the classification function must return CodeComplexity.HEAVY.
    
    This test verifies that file I/O operations are consistently detected
    and routed to heavy execution environments.
    """
    classifier = CodeClassifier()
    result = classifier.classify(code)
    
    # Verify heavy classification
    assert result == CodeComplexity.HEAVY, \
        f"Code with file I/O should be classified as HEAVY: {code}"


# ============================================================================
# Property 3: Routing matches classification
# Validates: Requirements 1.4
# ============================================================================

# Feature: llm-python-executor, Property 3: Routing matches classification
@given(code=st.one_of(
    code_with_heavy_imports(),
    code_with_file_io(),
    lightweight_code(),
    code_with_simple_loops(),
    code_with_complex_loops()
))
@settings(max_examples=100)
def test_routing_matches_classification(code):
    """
    Property: For any validated code, the routing decision (lightweight vs heavy)
    must match the result of the complexity classification function.
    
    This test verifies that the classification is consistent and deterministic.
    When the same code is classified multiple times, it should always return
    the same result.
    """
    classifier = CodeClassifier()
    
    # Classify the code multiple times
    result1 = classifier.classify(code)
    result2 = classifier.classify(code)
    result3 = classifier.classify(code)
    
    # Verify consistency
    assert result1 == result2 == result3, \
        f"Classification must be deterministic: got {result1}, {result2}, {result3} for code: {code}"
    
    # Verify result is a valid CodeComplexity value
    assert result1 in [CodeComplexity.LIGHTWEIGHT, CodeComplexity.HEAVY], \
        f"Classification must return a valid CodeComplexity value: {result1}"
    
    # Verify classification logic is correct based on code content
    try:
        tree = ast.parse(code)
        
        # Check if code has heavy imports
        has_heavy_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    if module_name in classifier.HEAVY_IMPORTS:
                        has_heavy_import = True
                        break
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    if module_name in classifier.HEAVY_IMPORTS:
                        has_heavy_import = True
                        break
        
        # If code has heavy imports, it must be classified as HEAVY
        if has_heavy_import:
            assert result1 == CodeComplexity.HEAVY, \
                f"Code with heavy imports must be classified as HEAVY: {code}"
        
    except SyntaxError:
        # Invalid syntax should still return a classification
        # (defaults to LIGHTWEIGHT in current implementation)
        assert result1 == CodeComplexity.LIGHTWEIGHT, \
            f"Invalid syntax should default to LIGHTWEIGHT: {code}"


# ============================================================================
# Additional Property: Lightweight code stays lightweight
# ============================================================================

# Feature: llm-python-executor, Property: Lightweight code classification
@given(code=lightweight_code())
@settings(max_examples=100)
def test_lightweight_code_classification(code):
    """
    Property: For any code without heavy imports, file I/O, or complex loops,
    the classification function should return CodeComplexity.LIGHTWEIGHT.
    
    This test verifies that simple code is correctly identified as lightweight
    and will be executed in the fast executor service.
    """
    classifier = CodeClassifier()
    result = classifier.classify(code)
    
    # Verify lightweight classification
    assert result == CodeComplexity.LIGHTWEIGHT, \
        f"Simple code should be classified as LIGHTWEIGHT: {code}"


# Feature: llm-python-executor, Property: Complex loops trigger heavy classification
@given(code=code_with_complex_loops())
@settings(max_examples=100)
def test_complex_loops_classification(code):
    """
    Property: For any code with deeply nested loops (3+ levels), the
    classification function should return CodeComplexity.HEAVY.
    
    This test verifies that computationally intensive loop structures
    are routed to heavy execution environments.
    """
    classifier = CodeClassifier()
    result = classifier.classify(code)
    
    # Verify heavy classification
    assert result == CodeComplexity.HEAVY, \
        f"Code with complex nested loops should be classified as HEAVY: {code}"
