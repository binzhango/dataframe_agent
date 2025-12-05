# Heavy Job Runner Docker Image - Build Instructions

## Overview

This document provides instructions for building and testing the Heavy Job Runner Docker image.

## Prerequisites

- Docker installed and running
- Access to the repository root directory
- (Optional) Container registry credentials for pushing the image

## Building the Image

### Local Build

From the repository root, run:

```bash
docker build -f deploy/docker/heavy-job-runner/Dockerfile -t heavy-job-runner:latest .
```

### Build with Version Tag

```bash
VERSION=0.1.0
docker build -f deploy/docker/heavy-job-runner/Dockerfile -t heavy-job-runner:${VERSION} -t heavy-job-runner:latest .
```

### Multi-platform Build (Optional)

For building images that work on both AMD64 and ARM64:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -f deploy/docker/heavy-job-runner/Dockerfile \
  -t heavy-job-runner:latest .
```

## Testing the Image

### Quick Test

Test that the image can run and import libraries:

```bash
docker run --rm \
  -e CODE="import pandas as pd; print(f'pandas version: {pd.__version__}')" \
  -e REQUEST_ID="test-001" \
  -e TIMEOUT="30" \
  heavy-job-runner:latest
```

### Test with Data Processing

```bash
docker run --rm \
  -e CODE="import pandas as pd; df = pd.DataFrame({'a': [1,2,3], 'b': [4,5,6]}); print(df.sum())" \
  -e REQUEST_ID="test-002" \
  -e TIMEOUT="30" \
  heavy-job-runner:latest
```

### Test with Polars

```bash
docker run --rm \
  -e CODE="import polars as pl; df = pl.DataFrame({'a': [1,2,3], 'b': [4,5,6]}); print(df)" \
  -e REQUEST_ID="test-003" \
  -e TIMEOUT="30" \
  heavy-job-runner:latest
```

### Test with PyArrow

```bash
docker run --rm \
  -e CODE="import pyarrow as pa; arr = pa.array([1,2,3,4,5]); print(f'Array length: {len(arr)}')" \
  -e REQUEST_ID="test-004" \
  -e TIMEOUT="30" \
  heavy-job-runner:latest
```

### Test with Numba

```bash
docker run --rm \
  -e CODE="from numba import jit; @jit(nopython=True); def add(a,b): return a+b; print(f'Result: {add(5,3)}')" \
  -e REQUEST_ID="test-005" \
  -e TIMEOUT="30" \
  heavy-job-runner:latest
```

## Verifying Image Contents

### Check Installed Libraries

```bash
docker run --rm heavy-job-runner:latest python -c "
import sys
libraries = ['pandas', 'modin', 'polars', 'pyarrow', 'cloudpickle', 'fsspec', 'adlfs', 's3fs', 'numba']
for lib in libraries:
    try:
        __import__(lib)
        print(f'✓ {lib}')
    except ImportError:
        print(f'✗ {lib} - NOT FOUND')
"
```

### Check Image Size

```bash
docker images heavy-job-runner:latest
```

Expected size: < 2GB

### Inspect Image Layers

```bash
docker history heavy-job-runner:latest
```

### Check User Configuration

```bash
docker run --rm heavy-job-runner:latest id
```

Expected output: `uid=1000(jobrunner) gid=1000(jobrunner) groups=1000(jobrunner)`

## Pushing to Registry

### Docker Hub

```bash
docker tag heavy-job-runner:latest yourusername/heavy-job-runner:latest
docker push yourusername/heavy-job-runner:latest
```

### Azure Container Registry

```bash
az acr login --name yourregistry
docker tag heavy-job-runner:latest yourregistry.azurecr.io/heavy-job-runner:latest
docker push yourregistry.azurecr.io/heavy-job-runner:latest
```

### AWS ECR

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
docker tag heavy-job-runner:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/heavy-job-runner:latest
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/heavy-job-runner:latest
```

## Troubleshooting

### Build Fails with Memory Error

Increase Docker memory allocation in Docker Desktop settings or use:

```bash
docker build --memory=8g -f deploy/docker/heavy-job-runner/Dockerfile -t heavy-job-runner:latest .
```

### Import Errors in Container

Verify the virtual environment is properly activated:

```bash
docker run --rm heavy-job-runner:latest which python
docker run --rm heavy-job-runner:latest python -c "import sys; print(sys.path)"
```

### Permission Errors

Ensure the jobrunner user has proper permissions:

```bash
docker run --rm heavy-job-runner:latest ls -la /app
docker run --rm heavy-job-runner:latest ls -la /tmp
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build Heavy Job Runner

on:
  push:
    branches: [main]
    paths:
      - 'src/llm_executor/job_runner/**'
      - 'deploy/docker/heavy-job-runner/**'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Build image
        run: |
          docker build -f deploy/docker/heavy-job-runner/Dockerfile \
            -t heavy-job-runner:${{ github.sha }} \
            -t heavy-job-runner:latest .
      
      - name: Test image
        run: |
          docker run --rm \
            -e CODE="import pandas; print('OK')" \
            -e REQUEST_ID="ci-test" \
            -e TIMEOUT="30" \
            heavy-job-runner:latest
      
      - name: Push to registry
        run: |
          echo "${{ secrets.REGISTRY_PASSWORD }}" | docker login -u "${{ secrets.REGISTRY_USERNAME }}" --password-stdin
          docker push heavy-job-runner:latest
```

## Security Scanning

### Scan with Trivy

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image heavy-job-runner:latest
```

### Scan with Snyk

```bash
snyk container test heavy-job-runner:latest
```

## Performance Optimization

### Reduce Image Size

The multi-stage build already optimizes size. Additional optimizations:

1. Use `--no-cache-dir` with pip (already implemented)
2. Remove unnecessary build dependencies (already implemented)
3. Use slim Python base image (already implemented)

### Build Cache

Use BuildKit for better caching:

```bash
DOCKER_BUILDKIT=1 docker build -f deploy/docker/heavy-job-runner/Dockerfile -t heavy-job-runner:latest .
```

## Maintenance

### Updating Dependencies

1. Update version numbers in `pyproject.toml`
2. Rebuild the image
3. Run all tests
4. Update version tag

### Regular Security Updates

Rebuild the image monthly to get base image security updates:

```bash
docker build --no-cache -f deploy/docker/heavy-job-runner/Dockerfile -t heavy-job-runner:latest .
```
