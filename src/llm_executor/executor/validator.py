"""Code validation using AST-based analysis.

This module provides security-focused validation of Python code through
Abstract Syntax Tree (AST) analysis. It detects restricted operations,
unauthorized imports, and other security concerns before code execution.
"""

import ast
from abc import ABC, abstractmethod
from typing import List, Set

from llm_executor.shared.models import ValidationResult
from llm_executor.shared.exceptions import (
    RestrictedOperationError,
    UnauthorizedImportError,
)


class ValidationRule(ABC):
    """Abstract base class for validation rules."""

    @abstractmethod
    def validate(self, tree: ast.AST) -> ValidationResult:
        """Validate the AST against this rule.
        
        Args:
            tree: The AST to validate
            
        Returns:
            ValidationResult with validation status and any errors
        """
        pass


class NoFileIORule(ValidationRule):
    """Validation rule that detects file I/O operations."""

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

    def validate(self, tree: ast.AST) -> ValidationResult:
        """Detect file I/O operations in the code.
        
        Args:
            tree: The AST to validate
            
        Returns:
            ValidationResult indicating if file operations were found
        """
        errors = []

        for node in ast.walk(tree):
            # Check for direct file operation calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.FILE_OPERATIONS:
                        errors.append(
                            f"File I/O operation not allowed: {node.func.id}"
                        )
                elif isinstance(node.func, ast.Attribute):
                    # Check for methods like file.read(), file.write()
                    if node.func.attr in self.FILE_OPERATIONS:
                        errors.append(
                            f"File I/O operation not allowed: {node.func.attr}"
                        )

            # Check for 'with open()' statements
            if isinstance(node, ast.With):
                for item in node.items:
                    if isinstance(item.context_expr, ast.Call):
                        if isinstance(item.context_expr.func, ast.Name):
                            if item.context_expr.func.id == "open":
                                errors.append(
                                    "File I/O operation not allowed: open (in with statement)"
                                )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[]
        )


class NoOSCommandsRule(ValidationRule):
    """Validation rule that detects OS command execution."""

    OS_OPERATIONS = {
        "system",
        "popen",
        "exec",
        "eval",
        "compile",
        "__import__",
    }

    OS_MODULES = {
        "os",
        "subprocess",
        "commands",
    }

    def validate(self, tree: ast.AST) -> ValidationResult:
        """Detect OS command execution in the code.
        
        Args:
            tree: The AST to validate
            
        Returns:
            ValidationResult indicating if OS commands were found
        """
        errors = []

        for node in ast.walk(tree):
            # Check for direct OS operation calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.OS_OPERATIONS:
                        errors.append(
                            f"OS command execution not allowed: {node.func.id}"
                        )
                elif isinstance(node.func, ast.Attribute):
                    # Check for os.system(), subprocess.run(), etc.
                    if node.func.attr in self.OS_OPERATIONS:
                        errors.append(
                            f"OS command execution not allowed: {node.func.attr}"
                        )
                    # Check for module.operation patterns
                    if isinstance(node.func.value, ast.Name):
                        if node.func.value.id in self.OS_MODULES:
                            errors.append(
                                f"OS command execution not allowed: {node.func.value.id}.{node.func.attr}"
                            )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[]
        )


class NoNetworkRule(ValidationRule):
    """Validation rule that detects network operations."""

    NETWORK_OPERATIONS = {
        "socket",
        "urlopen",
        "request",
        "get",
        "post",
        "put",
        "delete",
        "patch",
    }

    NETWORK_MODULES = {
        "socket",
        "urllib",
        "urllib2",
        "urllib3",
        "requests",
        "http",
        "httplib",
        "httplib2",
        "aiohttp",
    }

    def validate(self, tree: ast.AST) -> ValidationResult:
        """Detect network operations in the code.
        
        Args:
            tree: The AST to validate
            
        Returns:
            ValidationResult indicating if network operations were found
        """
        errors = []

        for node in ast.walk(tree):
            # Check for network operation calls
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.NETWORK_OPERATIONS:
                        errors.append(
                            f"Network operation not allowed: {node.func.id}"
                        )
                elif isinstance(node.func, ast.Attribute):
                    # Check for module.operation patterns
                    if node.func.attr in self.NETWORK_OPERATIONS:
                        errors.append(
                            f"Network operation not allowed: {node.func.attr}"
                        )
                    if isinstance(node.func.value, ast.Name):
                        if node.func.value.id in self.NETWORK_MODULES:
                            errors.append(
                                f"Network operation not allowed: {node.func.value.id}.{node.func.attr}"
                            )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[]
        )


class ImportValidationRule(ValidationRule):
    """Validation rule that checks imports against an allowlist."""

    # Default allowlist of safe modules
    DEFAULT_ALLOWLIST = {
        "math",
        "random",
        "datetime",
        "json",
        "re",
        "collections",
        "itertools",
        "functools",
        "operator",
        "string",
        "decimal",
        "fractions",
        "statistics",
        "typing",
        "dataclasses",
        "enum",
        "copy",
        "pprint",
        "textwrap",
        "unicodedata",
        "hashlib",
        "hmac",
        "secrets",
        "uuid",
        "time",
        "calendar",
        "zoneinfo",
    }

    # Explicitly prohibited modules
    PROHIBITED_MODULES = {
        "os",
        "sys",
        "subprocess",
        "socket",
        "urllib",
        "urllib2",
        "urllib3",
        "requests",
        "http",
        "httplib",
        "httplib2",
        "aiohttp",
        "io",
        "pathlib",
        "shutil",
        "tempfile",
        "glob",
        "pickle",
        "shelve",
        "dbm",
        "sqlite3",
        "ctypes",
        "multiprocessing",
        "threading",
        "asyncio",
        "concurrent",
        "__builtin__",
        "builtins",
        "importlib",
    }

    def __init__(self, allowlist: Set[str] = None):
        """Initialize the import validation rule.
        
        Args:
            allowlist: Set of allowed module names. If None, uses DEFAULT_ALLOWLIST.
        """
        self.allowlist = allowlist if allowlist is not None else self.DEFAULT_ALLOWLIST

    def validate(self, tree: ast.AST) -> ValidationResult:
        """Check imports against the allowlist.
        
        Args:
            tree: The AST to validate
            
        Returns:
            ValidationResult indicating if unauthorized imports were found
        """
        errors = []
        unauthorized_imports = []

        for node in ast.walk(tree):
            # Check 'import module' statements
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name.split('.')[0]  # Get base module
                    if module_name in self.PROHIBITED_MODULES:
                        unauthorized_imports.append(module_name)
                        errors.append(
                            f"Unauthorized import detected: {alias.name}"
                        )
                    elif module_name not in self.allowlist:
                        unauthorized_imports.append(module_name)
                        errors.append(
                            f"Unauthorized import detected: {alias.name}"
                        )

            # Check 'from module import ...' statements
            if isinstance(node, ast.ImportFrom):
                if node.module:
                    module_name = node.module.split('.')[0]  # Get base module
                    if module_name in self.PROHIBITED_MODULES:
                        unauthorized_imports.append(module_name)
                        errors.append(
                            f"Unauthorized import detected: {node.module}"
                        )
                    elif module_name not in self.allowlist:
                        unauthorized_imports.append(module_name)
                        errors.append(
                            f"Unauthorized import detected: {node.module}"
                        )

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[]
        )


class CodeValidator:
    """Orchestrates all validation rules and returns comprehensive validation results."""

    def __init__(self, import_allowlist: Set[str] = None):
        """Initialize the code validator with validation rules.
        
        Args:
            import_allowlist: Optional set of allowed module names for imports.
        """
        self.rules: List[ValidationRule] = [
            NoFileIORule(),
            NoOSCommandsRule(),
            NoNetworkRule(),
            ImportValidationRule(import_allowlist),
        ]

    def validate(self, code: str) -> ValidationResult:
        """Validate Python code against all security rules.
        
        Args:
            code: Python code string to validate
            
        Returns:
            ValidationResult with combined results from all rules
            
        Raises:
            SyntaxError: If the code is not valid Python
        """
        # Parse the code into an AST
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return ValidationResult(
                is_valid=False,
                errors=[f"Syntax error: {str(e)}"],
                warnings=[]
            )

        # Run all validation rules
        all_errors = []
        all_warnings = []

        for rule in self.rules:
            result = rule.validate(tree)
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)

        return ValidationResult(
            is_valid=len(all_errors) == 0,
            errors=all_errors,
            warnings=all_warnings
        )
