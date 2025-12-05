"""Unit tests for Docker image requirements.

This module contains unit tests that verify the Heavy Job Runner Docker image
meets the requirements for library availability and cloud storage support.
"""

import subprocess
import pytest
from pathlib import Path


def get_python_executable() -> str:
    """Get the Python executable from the uv venv."""
    venv_path = Path(".venv")
    if venv_path.exists():
        python_path = venv_path / "bin" / "python"
        if python_path.exists():
            return str(python_path)
    return "python3"


class TestLibraryAvailability:
    """Test that all required libraries can be imported without errors.
    
    Requirements: 10.1
    """
    
    REQUIRED_LIBRARIES = [
        "pandas",
        "modin",
        "polars",
        "pyarrow",
        "cloudpickle",
        "fsspec",
        "adlfs",
        "s3fs",
        "numba",
    ]
    
    @pytest.mark.parametrize("library", REQUIRED_LIBRARIES)
    def test_library_can_be_imported(self, library: str):
        """Test that each required library can be imported."""
        code = f"import {library}"
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"Failed to import {library}. "
            f"stderr: {result.stderr}"
        )
    
    def test_all_libraries_can_be_imported_together(self):
        """Test that all required libraries can be imported together."""
        import_statements = "\n".join([
            f"import {lib}" for lib in self.REQUIRED_LIBRARIES
        ])
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", import_statements],
            capture_output=True,
            text=True,
            timeout=20,
        )
        
        assert result.returncode == 0, (
            f"Failed to import all libraries together. "
            f"stderr: {result.stderr}"
        )
    
    @pytest.mark.parametrize("library,expected_modules", [
        ("pandas", ["DataFrame", "Series"]),
        ("polars", ["DataFrame", "LazyFrame"]),
        ("pyarrow", ["Table", "Array"]),
        ("fsspec", ["filesystem", "open"]),
    ])
    def test_library_has_expected_modules(self, library: str, expected_modules: list):
        """Test that libraries expose expected modules/classes."""
        for module in expected_modules:
            code = f"import {library}; assert hasattr({library}, '{module}')"
            python_exec = get_python_executable()
            
            result = subprocess.run(
                [python_exec, "-c", code],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            assert result.returncode == 0, (
                f"{library} does not have expected module/class: {module}. "
                f"stderr: {result.stderr}"
            )
    
    def test_data_processing_workflow(self):
        """Test a simple data processing workflow using pandas."""
        code = """
import pandas as pd
df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
result = df['a'].sum()
assert result == 6, f"Expected 6, got {result}"
print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"Data processing workflow failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
    
    def test_polars_workflow(self):
        """Test a simple data processing workflow using polars."""
        code = """
import polars as pl
df = pl.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
result = df['a'].sum()
assert result == 6, f"Expected 6, got {result}"
print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"Polars workflow failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
    
    def test_pyarrow_workflow(self):
        """Test a simple workflow using pyarrow."""
        code = """
import pyarrow as pa
array = pa.array([1, 2, 3, 4, 5])
assert len(array) == 5
assert array[0].as_py() == 1
print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"PyArrow workflow failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
    
    def test_numba_jit_compilation(self):
        """Test that numba can JIT compile functions."""
        code = """
from numba import jit

@jit(nopython=True)
def add(a, b):
    return a + b

result = add(5, 3)
assert result == 8, f"Expected 8, got {result}"
print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=15,
        )
        
        assert result.returncode == 0, (
            f"Numba JIT compilation failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
    
    def test_cloudpickle_serialization(self):
        """Test that cloudpickle can serialize and deserialize objects."""
        code = """
import cloudpickle

def my_function(x):
    return x * 2

serialized = cloudpickle.dumps(my_function)
deserialized = cloudpickle.loads(serialized)
result = deserialized(5)
assert result == 10, f"Expected 10, got {result}"
print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"Cloudpickle serialization failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout



class TestCloudStorageSupport:
    """Test that fsspec with adlfs and s3fs can access mock storage.
    
    Requirements: 10.3
    """
    
    def test_fsspec_is_available(self):
        """Test that fsspec can be imported and used."""
        code = """
import fsspec
# Test basic fsspec functionality
fs = fsspec.filesystem('memory')
with fs.open('/test.txt', 'w') as f:
    f.write('test data')
with fs.open('/test.txt', 'r') as f:
    data = f.read()
assert data == 'test data'
print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"fsspec test failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
    
    def test_adlfs_can_be_imported(self):
        """Test that adlfs (Azure Data Lake Storage) can be imported."""
        code = """
import adlfs
# Verify the module has expected attributes
assert hasattr(adlfs, 'AzureBlobFileSystem')
print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"adlfs import failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
    
    def test_s3fs_can_be_imported(self):
        """Test that s3fs can be imported."""
        code = """
import s3fs
# Verify the module has expected attributes
assert hasattr(s3fs, 'S3FileSystem')
print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"s3fs import failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
    
    def test_fsspec_with_memory_backend(self):
        """Test fsspec with memory backend as a mock storage."""
        code = """
import fsspec
import json

# Create a memory filesystem (mock storage)
fs = fsspec.filesystem('memory')

# Write JSON data
data = {'request_id': 'test-123', 'status': 'success', 'result': 42}
with fs.open('/results/test-123.json', 'w') as f:
    json.dump(data, f)

# Read JSON data back
with fs.open('/results/test-123.json', 'r') as f:
    loaded_data = json.load(f)

assert loaded_data == data
assert loaded_data['request_id'] == 'test-123'
assert loaded_data['result'] == 42
print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"fsspec memory backend test failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
    
    def test_fsspec_supports_azure_protocol(self):
        """Test that fsspec recognizes Azure Blob Storage protocol."""
        code = """
import fsspec

# Test that fsspec can recognize the abfs protocol (Azure Blob File System)
# We don't actually connect, just verify the protocol is registered
try:
    # This will fail without credentials, but should recognize the protocol
    fs = fsspec.filesystem('abfs')
    # If we get here, the protocol is recognized
    print("SUCCESS")
except ImportError:
    # Protocol not available
    print("FAILED: abfs protocol not available")
except ValueError as e:
    # ValueError for missing credentials means the protocol is recognized
    # but we don't have valid credentials (which is expected)
    if "connection_string" in str(e) or "account_name" in str(e):
        print("SUCCESS")
    else:
        raise
except Exception as e:
    # Other errors might indicate the protocol is recognized
    # but there's a configuration issue (which is fine for this test)
    print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"Azure protocol test failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
    
    def test_fsspec_supports_s3_protocol(self):
        """Test that fsspec recognizes S3 protocol."""
        code = """
import fsspec

# Test that fsspec can recognize the s3 protocol
# We don't actually connect, just verify the protocol is registered
try:
    # This will fail without credentials, but should recognize the protocol
    fs = fsspec.filesystem('s3', anon=True)
    # If we get here, the protocol is recognized
    print("SUCCESS")
except ImportError:
    # Protocol not available
    print("FAILED: s3 protocol not available")
except Exception as e:
    # Other errors are expected without real S3 access
    # As long as it's not ImportError, the protocol is recognized
    print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"S3 protocol test failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
    
    def test_fsspec_open_with_storage_options(self):
        """Test that fsspec.open accepts storage_options parameter."""
        code = """
import fsspec

# Test that fsspec.open can accept storage_options
# Using memory backend with custom options
storage_options = {'some_option': 'value'}

# This should work even if the option is ignored by memory backend
with fsspec.open('memory://test.txt', 'w', **storage_options) as f:
    f.write('test')

with fsspec.open('memory://test.txt', 'r') as f:
    data = f.read()

assert data == 'test'
print("SUCCESS")
"""
        python_exec = get_python_executable()
        
        result = subprocess.run(
            [python_exec, "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        assert result.returncode == 0, (
            f"fsspec storage_options test failed. stderr: {result.stderr}"
        )
        assert "SUCCESS" in result.stdout
