# Heavy Job Runner Docker Image

This Docker image is designed for executing resource-intensive Python code in Kubernetes Job pods. It includes data processing libraries and cloud storage support.

## Included Libraries

The image includes the following data processing libraries:
- **pandas**: Data manipulation and analysis
- **modin**: Distributed pandas alternative
- **polars**: Fast DataFrame library
- **pyarrow**: Apache Arrow Python bindings
- **cloudpickle**: Extended pickling support
- **numba**: JIT compiler for numerical functions
- **fsspec**: Filesystem abstraction
- **adlfs**: Azure Data Lake Storage support
- **s3fs**: S3 filesystem support

## Building the Image

From the repository root:

```bash
docker build -f deploy/docker/heavy-job-runner/Dockerfile -t heavy-job-runner:latest .
```

## Running the Image

The image expects the following environment variables:

- `CODE`: Python code to execute (required)
- `REQUEST_ID`: Unique request identifier (required)
- `TIMEOUT`: Execution timeout in seconds (optional, default: 300)
- `AZURE_STORAGE_CONNECTION_STRING`: Azure Blob Storage connection string (optional)
- `AZURE_STORAGE_CONTAINER`: Azure Blob Storage container name (optional)
- `S3_ACCESS_KEY`: S3 access key (optional)
- `S3_SECRET_KEY`: S3 secret key (optional)
- `S3_BUCKET`: S3 bucket name (optional)
- `EVENT_HUB_CONNECTION_STRING`: Azure Event Hub connection string (optional)

Example:

```bash
docker run --rm \
  -e CODE="import pandas as pd; print(pd.__version__)" \
  -e REQUEST_ID="test-123" \
  -e TIMEOUT="60" \
  heavy-job-runner:latest
```

## Security Features

- Runs as non-root user (UID 1000)
- Multi-stage build for smaller image size
- Minimal runtime dependencies
- Isolated execution environment

## Image Size

Target size: < 2GB (includes all data processing libraries)

## Kubernetes Usage

This image is designed to be used in Kubernetes Job specifications:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: heavy-executor-job
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: executor
        image: heavy-job-runner:latest
        env:
        - name: CODE
          value: "import pandas as pd; print(pd.DataFrame({'a': [1,2,3]}))"
        - name: REQUEST_ID
          value: "req-123"
        - name: TIMEOUT
          value: "300"
        resources:
          limits:
            cpu: "4"
            memory: "8Gi"
          requests:
            cpu: "2"
            memory: "4Gi"
```
