"""Code classification for routing decisions.

This module provides classification of Python code based on complexity
and resource requirements. It analyzes code using AST to determine whether
it should be executed in a lightweight executor or a heavy Kubernetes Job.
"""

import ast
from typing import Set

from llm_executor.shared.models import CodeComplexity


class CodeClassifier:
    """Classifies Python code as lightweight or heavy based on imports and operations."""

    # Heavy data processing libraries that trigger heavy classification
    HEAVY_IMPORTS = {
        "pandas",
        "modin",
        "polars",
        "pyarrow",
        "dask",
        "ray",
        "pyspark",
    }

    # File I/O operations that may indicate heavy workloads
    FILE_OPERATIONS = {
        "open",
        "read",
        "write",
        "file",
    }

    FILE_MODULES = {
        "io",
        "pathlib",
    }

    def __init__(self):
        """Initialize the code classifier."""
        pass

    def classify(self, code: str) -> CodeComplexity:
        """Classify code as lightweight or heavy based on AST analysis.
        
        This method analyzes the code to determine if it requires heavy
        resources (Kubernetes Job) or can run in a lightweight executor.
        
        Classification triggers for HEAVY:
        - Imports heavy data processing libraries (pandas, polars, etc.)
        - Contains file I/O operations
        - Large input sizes or complex loops (future enhancement)
        
        Args:
            code: Python code string to classify
            
        Returns:
            CodeComplexity.HEAVY if code requires heavy resources,
            CodeComplexity.LIGHTWEIGHT otherwise
            
        Raises:
            SyntaxError: If the code is not valid Python
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            # Invalid code defaults to lightweight (will fail validation anyway)
            return CodeComplexity.LIGHTWEIGHT

        # Check for heavy imports
        if self._has_heavy_imports(tree):
            return CodeComplexity.HEAVY

        # Check for file I/O operations
        if self._has_file_io(tree):
            return CodeComplexity.HEAVY

        # Check for loop complexity (basic heuristic)
        if self._has_complex_loops(tree):
            return CodeComplexity.HEAVY

        return CodeComplexity.LIGHTWEIGHT

    def _has_heavy_imports(self, tree: ast.AST) -> bool:
        """Check if code imports heavy data processing libraries.
        
        Args:
            tree: The AST to analyze
            
        Returns:
            True if heavy imports are detected, False otherwise
        """
        for node in ast.walk(tree):
            # Check 'import module' statements
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    if module_name in self.HEAVY_IMPORTS:
                        return True

            # Check 'from module import ...' statements
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    if module_name in self.HEAVY_IMPORTS:
                        return True

        return False

    def _has_file_io(self, tree: ast.AST) -> bool:
        """Check if code contains file I/O operations.
        
        Args:
            tree: The AST to analyze
            
        Returns:
            True if file I/O operations are detected, False otherwise
        """
        for node in ast.walk(tree):
            # Check for direct file operation calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.FILE_OPERATIONS:
                        return True
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr in self.FILE_OPERATIONS:
                        return True

            # Check for 'with open()' statements
            if isinstance(node, ast.With):
                for item in node.items:
                    if isinstance(item.context_expr, ast.Call):
                        if isinstance(item.context_expr.func, ast.Name):
                            if item.context_expr.func.id == "open":
                                return True

            # Check for file-related module imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]
                    if module_name in self.FILE_MODULES:
                        return True

            if isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]
                    if module_name in self.FILE_MODULES:
                        return True

        return False

    def _has_complex_loops(self, tree: ast.AST) -> bool:
        """Check if code has complex nested loops.
        
        This is a basic heuristic that detects deeply nested loops
        which may indicate computationally intensive operations.
        
        Args:
            tree: The AST to analyze
            
        Returns:
            True if complex loops are detected, False otherwise
        """
        def count_loop_depth(node: ast.AST, current_depth: int = 0) -> int:
            """Recursively count maximum loop nesting depth."""
            max_depth = current_depth
            
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.For, ast.While)):
                    # Found a loop, increase depth
                    child_depth = count_loop_depth(child, current_depth + 1)
                    max_depth = max(max_depth, child_depth)
                else:
                    # Continue traversing
                    child_depth = count_loop_depth(child, current_depth)
                    max_depth = max(max_depth, child_depth)
            
            return max_depth

        # Consider loops nested 3+ levels deep as complex
        max_depth = count_loop_depth(tree)
        return max_depth >= 3
