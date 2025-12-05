"""Property-based tests for Docker image requirements.

This module contains property-based tests that verify the Heavy Job Runner
Docker image meets the requirements for library availability and cloud storage support.
"""

import subprocess
import os
from pathlib import Path
from hypothesis import given, settings, strategies as st
from typing import List


def get_python_executable() -> str:
    """Get the Python executable from the uv venv."""
    # Check if we're in a uv venv
    venv_path = Path(".venv")
    if venv_path.exists():
        python_path = venv_path / "bin" / "python"
        if python_path.exists():
            return str(python_path)
    
    # Fallback to python3 in PATH
    return "python3"


# Feature: llm-python-executor, Property 27: Supported libraries are importable
# Validates: Requirements 10.2
@given(library=st.sampled_from([
    "pandas",
    "modin",
    "polars",
    "pyarrow",
    "cloudpickle",
    "fsspec",
    "adlfs",
    "s3fs",
    "numba",
]))
@settings(max_examples=100, deadline=5000)
def test_supported_libraries_are_importable(library: str):
    """
    Property 27: Supported libraries are importable.
    
    For any library in the supported set (pandas, modin, polars, pyarrow,
    cloudpickle, fsspec, adlfs, s3fs, numba), code that imports that library
    must execute without ImportError in the Heavy Job Runner.
    
    This test verifies that all required data processing libraries can be
    imported successfully, which is essential for the Heavy Job Runner to
    execute resource-intensive workloads.
    """
    # Test that the library can be imported
    code = f"import {library}"
    python_exec = get_python_executable()
    
    result = subprocess.run(
        [python_exec, "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
    )
    
    # Verify import succeeded
    assert result.returncode == 0, (
        f"Failed to import {library}. "
        f"stderr: {result.stderr}, stdout: {result.stdout}"
    )
    
    # Verify no error messages in stderr
    assert "ImportError" not in result.stderr, (
        f"ImportError found when importing {library}: {result.stderr}"
    )
    assert "ModuleNotFoundError" not in result.stderr, (
        f"ModuleNotFoundError found when importing {library}: {result.stderr}"
    )


@given(libraries=st.lists(
    st.sampled_from([
        "pandas",
        "modin",
        "polars",
        "pyarrow",
        "cloudpickle",
        "fsspec",
        "adlfs",
        "s3fs",
        "numba",
    ]),
    min_size=1,
    max_size=5,
    unique=True
))
@settings(max_examples=50, deadline=10000)
def test_multiple_libraries_can_be_imported_together(libraries: List[str]):
    """
    Property: Multiple supported libraries can be imported together.
    
    For any combination of supported libraries, they should be importable
    together without conflicts. This ensures that the Heavy Job Runner
    can execute code that uses multiple data processing libraries.
    """
    # Create import statements for all libraries
    import_statements = "\n".join([f"import {lib}" for lib in libraries])
    python_exec = get_python_executable()
    
    result = subprocess.run(
        [python_exec, "-c", import_statements],
        capture_output=True,
        text=True,
        timeout=15,
    )
    
    # Verify all imports succeeded
    assert result.returncode == 0, (
        f"Failed to import libraries {libraries}. "
        f"stderr: {result.stderr}, stdout: {result.stdout}"
    )
    
    # Verify no error messages
    assert "ImportError" not in result.stderr
    assert "ModuleNotFoundError" not in result.stderr


@given(library=st.sampled_from([
    "pandas",
    "polars",
    "pyarrow",
    "numba",
]))
@settings(max_examples=20, deadline=10000)
def test_library_has_version_attribute(library: str):
    """
    Property: Supported libraries expose version information.
    
    For any major supported library, it should expose version information
    through __version__ attribute. This helps with debugging and ensures
    the libraries are properly installed.
    """
    code = f"import {library}; print({library}.__version__)"
    python_exec = get_python_executable()
    
    result = subprocess.run(
        [python_exec, "-c", code],
        capture_output=True,
        text=True,
        timeout=10,
    )
    
    # Verify execution succeeded
    assert result.returncode == 0, (
        f"Failed to get version for {library}. "
        f"stderr: {result.stderr}"
    )
    
    # Verify version was printed (non-empty output)
    assert result.stdout.strip(), (
        f"No version output for {library}"
    )
    
    # Verify output looks like a version string (contains digits and dots)
    version = result.stdout.strip()
    assert any(char.isdigit() for char in version), (
        f"Version string for {library} doesn't contain digits: {version}"
    )
