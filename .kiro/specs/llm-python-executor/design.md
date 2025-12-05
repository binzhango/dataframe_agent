# Design Document

## Overview

The LLM-Driven Secure Python Execution Platform is a distributed system that transforms natural language queries into executable Python code through an LLM-powered pipeline. The architecture consists of three primary execution environments: an LLM Service for code generation and validation, an Executor Service for lightweight code execution, and Kubernetes Job pods for heavy data transformation workloads. The system employs intelligent routing to classify code complexity and direct execution to the appropriate environment, ensuring optimal resource utilization and security isolation.

The platform supports both synchronous REST API interactions and asynchronous Event Hub-driven workflows, providing flexibility for different use cases. Security is enforced at multiple layers through AST-based code validation, sandboxed execution environments, and Kubernetes pod-level isolation.

## Architecture

### System Components

The system follows a microservices architecture with three primary containers:

**Container A: LLM Service**
- Hosts the LangGraph orchestration flow
- Integrates with LLM for code generation
- Performs AST-based code validation
- Routes validated code to appropriate execution environments
- Exposes REST API for query submission

**Container B: Executor Service**
- Long-running FastAPI service
- Executes lightweight Python code in sandboxed subprocesses
- Creates Kubernetes Jobs for heavy workloads
- Consumes Event Hub messages for asynchronous processing
- Provides health check endpoints

**Kubernetes Jobs: Heavy Job Runner**
- Ephemeral pods for resource-intensive workloads
- Pre-loaded with data processing libraries (pandas, polars, modin, etc.)
- Writes results to cloud storage (Azure Blob/S3)
- Emits completion events to Event Hub
- Auto-cleanup via TTL policies

### Communication Flow

```
User Query (REST) → LLM Service → Code Generation → Validation
                                                      ↓
                                              [Light or Heavy?]
                                                      ↓
                                    ┌─────────────────┴─────────────────┐
                                    ↓                                   ↓
                            Executor Service                    Kubernetes Job
                            (subprocess sandbox)                (heavy libraries)
                                    ↓                                   ↓
                            Return Results                      Write to Blob
                                                                        ↓
                                                                Event Hub Event
```

### Technology Stack

- **LangGraph**: Orchestration framework for LLM workflows
- **FastAPI**: REST API framework for both services
- **Pydantic**: Data validation and settings management
- **Azure Event Hub**: Asynchronous messaging
- **Kubernetes**: Container orchestration for heavy jobs
- **Python AST**: Code validation and analysis
- **seccomp/cgroups**: Linux kernel security features

## Components and Interfaces

### LLM Service (Container A)

#### LangGraph Flow Nodes

1. **Input Parser Node**
   - Receives natural language query
   - Extracts intent and parameters
   - Formats prompt for LLM

2. **Code Generation Node**
   - Calls LLM with structured prompt
   - Receives generated Python code
   - Passes to validation

3. **Code Validator Node**
   - Performs AST parsing
   - Checks for restricted operations
   - Validates imports against allowlist
   - Returns validation result

4. **Correction Node**
   - Activated on validation failure
   - Sends validation errors back to LLM
   - Requests corrected code
   - Limits retry attempts (max 3)

5. **Execution Router Node**
   - Classifies code as light or heavy
   - Routes to Executor Service or Job creation
   - Returns execution handle

#### REST API Endpoints

```python
POST /api/v1/query
Request: {
  "query": str,
  "timeout": int (optional),
  "max_retries": int (optional)
}
Response: {
  "request_id": str,
  "generated_code": str,
  "execution_result": dict,
  "status": str
}

GET /api/v1/health
Response: {
  "status": "healthy",
  "version": str
}
```

### Executor Service (Container B)

#### REST API Endpoints

```python
POST /api/v1/execute_snippet
Request: {
  "code": str,
  "timeout": int,
  "request_id": str
}
Response: {
  "stdout": str,
  "stderr": str,
  "exit_code": int,
  "duration_ms": int
}

POST /api/v1/create_heavy_job
Request: {
  "code": str,
  "request_id": str,
  "resource_limits": dict
}
Response: {
  "job_id": str,
  "status": str,
  "created_at": str
}

GET /api/v1/health
Response: {
  "status": "healthy",
  "active_executions": int
}
```

#### Event Hub Consumer

- Subscribes to `code-execution-requests` topic
- Processes messages asynchronously
- Creates Kubernetes Jobs for heavy workloads
- Publishes to `execution-results` topic on completion

#### Sandbox Configuration

```python
# Subprocess execution with restrictions
subprocess.run(
    ["python", "-c", code],
    timeout=timeout_seconds,
    capture_output=True,
    env=restricted_env,  # No PATH, limited env vars
    cwd=temp_dir,  # Isolated working directory
    # Additional security via systemd-run or firejail
)
```

### Heavy Job Runner (Kubernetes Job)

#### Job Template

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: heavy-executor-{job_id}
spec:
  ttlSecondsAfterFinished: 3600
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: executor
        image: heavy-executor:latest
        resources:
          limits:
            cpu: "4"
            memory: "8Gi"
          requests:
            cpu: "2"
            memory: "4Gi"
        securityContext:
          runAsNonRoot: true
          readOnlyRootFilesystem: true
          allowPrivilegeEscalation: false
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "cleanup.sh"]
```

#### Execution Flow

1. Fetch code from job specification
2. Write code to temporary file in `/tmp`
3. Execute using subprocess with timeout
4. Capture results and write to cloud storage
5. Emit completion event to Event Hub
6. Exit (Kubernetes handles cleanup)

### Shared Library

#### Pydantic Models

```python
class CodeExecutionRequest(BaseModel):
    request_id: str
    code: str
    timeout: int = 30
    max_retries: int = 3

class ValidationResult(BaseModel):
    is_valid: bool
    errors: List[str]
    warnings: List[str]

class ExecutionResult(BaseModel):
    request_id: str
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    status: ExecutionStatus

class JobCreationRequest(BaseModel):
    request_id: str
    code: str
    resource_limits: ResourceLimits
```

## Data Models

### Code Classification

```python
class CodeComplexity(Enum):
    LIGHTWEIGHT = "lightweight"
    HEAVY = "heavy"

class CodeClassifier:
    HEAVY_IMPORTS = {
        "pandas", "modin", "polars", "pyarrow",
        "dask", "ray", "pyspark"
    }
    
    RESTRICTED_OPERATIONS = {
        "open", "file", "os.system", "subprocess",
        "socket", "urllib", "requests"
    }
    
    def classify(self, code: str) -> CodeComplexity:
        tree = ast.parse(code)
        
        # Check imports
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.HEAVY_IMPORTS:
                        return CodeComplexity.HEAVY
        
        # Check for file I/O
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if self._is_restricted_call(node):
                    return CodeComplexity.HEAVY
        
        return CodeComplexity.LIGHTWEIGHT
```

### Validation Rules

```python
class ValidationRule(ABC):
    @abstractmethod
    def validate(self, tree: ast.AST) -> ValidationResult:
        pass

class NoFileIORule(ValidationRule):
    def validate(self, tree: ast.AST) -> ValidationResult:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if self._is_file_operation(node):
                    return ValidationResult(
                        is_valid=False,
                        errors=["File I/O operations are not allowed"]
                    )
        return ValidationResult(is_valid=True, errors=[])

class NoOSCommandsRule(ValidationRule):
    def validate(self, tree: ast.AST) -> ValidationResult:
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if self._is_os_command(node):
                    return ValidationResult(
                        is_valid=False,
                        errors=["OS command execution is not allowed"]
                    )
        return ValidationResult(is_valid=True, errors=[])
```

### Resource Limits

```python
class ResourceLimits(BaseModel):
    cpu_limit: str = "4"
    memory_limit: str = "8Gi"
    cpu_request: str = "2"
    memory_request: str = "4Gi"
    timeout_seconds: int = 300
    disk_limit: str = "10Gi"
```

## 
Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Validation precedes execution

*For any* generated Python code, the validation function must be invoked and complete before any execution function is called.

**Validates: Requirements 1.2**

### Property 2: Validation errors trigger correction

*For any* code that fails validation, the correction node must be invoked with the validation errors as input.

**Validates: Requirements 1.3, 2.4**

### Property 3: Routing matches classification

*For any* validated code, the routing decision (lightweight vs heavy) must match the result of the complexity classification function.

**Validates: Requirements 1.4**

### Property 4: AST parsing performance

*For any* valid Python code string, AST parsing must complete within 30 milliseconds.

**Validates: Requirements 2.1**

### Property 5: Restricted operations are rejected

*For any* code containing restricted operations (file I/O, OS commands, socket operations), the validator must reject the code and return specific error messages identifying the restricted operation.

**Validates: Requirements 2.2**

### Property 6: Unauthorized imports are detected

*For any* code containing unauthorized imports, the validator must reject the code and identify the specific prohibited import names in the error message.

**Validates: Requirements 2.3**

### Property 7: Valid code proceeds to routing

*For any* code that passes validation, the system must invoke the routing logic to determine execution environment.

**Validates: Requirements 2.5**

### Property 8: Lightweight code uses restricted namespace

*For any* code classified as lightweight, execution must occur in a subprocess with a restricted namespace and timeout enforcement.

**Validates: Requirements 3.1**

### Property 9: Network isolation blocks access

*For any* code that attempts network operations (socket, HTTP requests), execution in the Executor Service must fail with a network access error.

**Validates: Requirements 3.3**

### Property 10: Timeout terminates execution

*For any* code execution that exceeds the configured timeout, the Executor Service must terminate the process and return a timeout error.

**Validates: Requirements 3.4**

### Property 11: Output capture completeness

*For any* code that writes to stdout or stderr, the execution result must contain the complete output in the respective fields.

**Validates: Requirements 3.5**

### Property 12: Heavy imports trigger heavy classification

*For any* code that imports heavy libraries (pandas, modin, polars, pyarrow, dask, ray, pyspark), the classification function must return CodeComplexity.HEAVY.

**Validates: Requirements 4.1**

### Property 13: File I/O triggers heavy classification

*For any* code containing file I/O operations (open, read, write), the classification function must return CodeComplexity.HEAVY.

**Validates: Requirements 4.2**

### Property 14: Heavy code creates Kubernetes Job

*For any* code classified as heavy, the Executor Service must create a Kubernetes Job with CPU and memory limits matching the configured resource limits.

**Validates: Requirements 4.3, 8.1**

### Property 15: Job completion emits event

*For any* Heavy Job Runner execution that completes (success or failure), the system must emit a completion event to Event Hub containing the request ID, status, and result location.

**Validates: Requirements 4.5, 5.3**

### Property 16: Event Hub message parsing

*For any* valid Event Hub message in the code-execution-requests format, the Executor Service must successfully parse the message and extract a valid CodeExecutionRequest object.

**Validates: Requirements 5.1**

### Property 17: Event Hub heavy code routing

*For any* Event Hub message containing code classified as heavy, the Executor Service must create a Kubernetes Job rather than executing locally.

**Validates: Requirements 5.2**

### Property 18: Structured logging includes request ID

*For any* request processed by any component, all log entries related to that request must include the request_id field.

**Validates: Requirements 5.5, 6.1**

### Property 19: Execution duration is recorded

*For any* code execution that completes, the system must record the execution duration in milliseconds in the execution result.

**Validates: Requirements 6.2**

### Property 20: Job history contains metadata

*For any* job execution stored in history, the record must contain timestamp, status, and resource_usage fields.

**Validates: Requirements 6.3**

### Property 21: Error logs contain stack traces

*For any* error that occurs during execution, the error log entry must contain a stack_trace field with the complete exception traceback.

**Validates: Requirements 6.4**

### Property 22: Temporary file cleanup

*For any* code execution that creates temporary files, those files must be removed from the filesystem after execution completes or fails.

**Validates: Requirements 8.5**

### Property 23: Validation retry limit

*For any* code that repeatedly fails validation, the LLM Service must stop retrying after the maximum retry count is reached and return a failure response.

**Validates: Requirements 9.1**

### Property 24: Execution retry policy

*For any* code execution that fails with a retryable error, the Executor Service must retry execution according to the configured retry policy (count and backoff).

**Validates: Requirements 9.2**

### Property 25: Timeout errors are not retried

*For any* code execution that fails with a timeout error, the system must not automatically retry and must return the timeout error to the caller.

**Validates: Requirements 9.4**

### Property 26: Max retries returns failure

*For any* execution that fails and exhausts all retry attempts, the system must return a failure response containing detailed error information from all attempts.

**Validates: Requirements 9.5**

### Property 27: Supported libraries are importable

*For any* library in the supported set (pandas, modin, polars, pyarrow, cloudpickle, fsspec, adlfs, s3fs, numba), code that imports that library must execute without ImportError in the Heavy Job Runner.

**Validates: Requirements 10.2**

## Error Handling

### Validation Errors

**Strategy**: Validation errors are recoverable through LLM correction. The system maintains a retry counter and provides detailed feedback to the LLM for each failed attempt.

**Error Types**:
- `RestrictedOperationError`: Code contains forbidden operations (file I/O, OS commands, network)
- `UnauthorizedImportError`: Code imports prohibited modules
- `SyntaxError`: Code is not valid Python
- `MaxRetriesExceededError`: Validation failed after maximum correction attempts

**Handling**:
```python
class ValidationErrorHandler:
    def handle(self, error: ValidationError, attempt: int) -> Response:
        if attempt >= MAX_RETRIES:
            return Response(
                status="failed",
                error="Maximum validation retries exceeded",
                details=error.to_dict()
            )
        
        # Send to correction node
        return self.correction_node.invoke(
            code=error.code,
            errors=error.errors,
            attempt=attempt + 1
        )
```

### Execution Errors

**Strategy**: Execution errors are categorized as retryable or non-retryable. Retryable errors trigger exponential backoff retry logic. Non-retryable errors return immediately.

**Error Types**:
- `TimeoutError`: Execution exceeded time limit (non-retryable)
- `MemoryError`: Execution exceeded memory limit (non-retryable)
- `RuntimeError`: Code raised an exception (retryable)
- `NetworkError`: Network operation attempted (non-retryable)
- `ResourceExhaustedError`: System resources unavailable (retryable)

**Handling**:
```python
class ExecutionErrorHandler:
    RETRYABLE_ERRORS = {RuntimeError, ResourceExhaustedError}
    
    def handle(self, error: ExecutionError, attempt: int) -> Response:
        if type(error) not in self.RETRYABLE_ERRORS:
            return Response(
                status="failed",
                error=str(error),
                retryable=False
            )
        
        if attempt >= MAX_EXECUTION_RETRIES:
            return Response(
                status="failed",
                error="Maximum execution retries exceeded",
                attempts=attempt
            )
        
        # Exponential backoff
        delay = min(2 ** attempt, 60)
        time.sleep(delay)
        return self.retry_execution(error.code, attempt + 1)
```

### Kubernetes Job Errors

**Strategy**: Kubernetes Job failures are handled by Kubernetes backoff policies. The system monitors job status and emits failure events to Event Hub for downstream handling.

**Error Types**:
- `JobCreationError`: Failed to create Kubernetes Job
- `PodFailureError`: Pod crashed or was evicted
- `ImagePullError`: Container image unavailable
- `DeadlineExceededError`: Job exceeded activeDeadlineSeconds

**Handling**:
```python
class JobErrorHandler:
    def handle(self, job_status: V1JobStatus) -> None:
        if job_status.failed >= MAX_JOB_RETRIES:
            self.emit_failure_event(
                job_id=job_status.metadata.name,
                reason=job_status.conditions[-1].reason,
                message=job_status.conditions[-1].message
            )
            self.cleanup_job(job_status.metadata.name)
```

### Event Hub Errors

**Strategy**: Event Hub processing errors are logged but not retried by the application. Event Hub's built-in retry and dead-letter queue mechanisms handle reprocessing.

**Error Types**:
- `MessageParsingError`: Invalid message format
- `ProcessingError`: Error during message handling
- `PublishError`: Failed to publish completion event

**Handling**:
```python
class EventHubErrorHandler:
    def handle(self, error: EventHubError, message: EventData) -> None:
        logger.error(
            "Event Hub processing failed",
            error=str(error),
            message_id=message.message_id,
            partition_key=message.partition_key,
            exc_info=True
        )
        # Do not acknowledge message - let Event Hub retry
```

## Testing Strategy

The system employs a dual testing approach combining unit tests for specific scenarios and property-based tests for universal correctness properties.

### Unit Testing

Unit tests verify specific examples, integration points, and edge cases:

**LLM Service Tests**:
- LangGraph flow execution with mock LLM responses
- Validation of specific code patterns (file operations, imports)
- Routing decisions for known code samples
- API endpoint request/response handling
- Health check endpoint availability

**Executor Service Tests**:
- Subprocess execution with timeout
- Output capture for known code
- Kubernetes Job creation with specific parameters
- Event Hub message consumption
- Health check endpoint availability

**Heavy Job Runner Tests**:
- Library import verification (pandas, polars, etc.)
- Result writing to mock storage
- Event emission to mock Event Hub
- Cleanup of temporary files

**Shared Library Tests**:
- Pydantic model validation
- Configuration loading
- Logging utility formatting

### Property-Based Testing

Property-based tests verify universal properties across randomly generated inputs. The system uses **Hypothesis** for Python property-based testing, configured to run a minimum of 100 iterations per test.

**Test Annotation Format**: Each property-based test must include a comment explicitly referencing the correctness property:
```python
# Feature: llm-python-executor, Property 5: Restricted operations are rejected
@given(code=strategies.code_with_restricted_operations())
@settings(max_examples=100)
def test_restricted_operations_rejected(code):
    result = validator.validate(code)
    assert not result.is_valid
    assert any("restricted" in err.lower() for err in result.errors)
```

**Property Test Coverage**:

1. **Validation Properties** (Properties 1, 2, 5, 6, 7):
   - Generate random Python code with various patterns
   - Verify validation rules consistently reject/accept
   - Verify validation always precedes execution
   - Verify correction workflow triggers on failures

2. **Classification Properties** (Properties 3, 12, 13):
   - Generate code with different import patterns
   - Generate code with different operation types
   - Verify classification consistency
   - Verify routing matches classification

3. **Execution Properties** (Properties 8, 9, 10, 11):
   - Generate random executable code
   - Verify timeout enforcement
   - Verify output capture completeness
   - Verify network isolation

4. **Resource Management Properties** (Properties 14, 22):
   - Generate code requiring different resources
   - Verify resource limits are applied
   - Verify cleanup occurs

5. **Event and Logging Properties** (Properties 15, 16, 17, 18, 19, 20, 21):
   - Generate random request IDs and messages
   - Verify event emission consistency
   - Verify logging completeness
   - Verify metadata recording

6. **Retry Properties** (Properties 23, 24, 25, 26):
   - Generate failing scenarios
   - Verify retry limits are enforced
   - Verify retry policies are followed
   - Verify timeout errors skip retry

7. **Library Support Properties** (Property 27):
   - Generate import statements for all supported libraries
   - Verify imports succeed in Heavy Job Runner

**Custom Strategies**:

```python
import hypothesis.strategies as st
from hypothesis import given, settings

@st.composite
def code_with_restricted_operations(draw):
    """Generate Python code containing restricted operations."""
    operations = ["open('file.txt')", "os.system('ls')", "socket.socket()"]
    op = draw(st.sampled_from(operations))
    return f"result = {op}"

@st.composite
def code_with_heavy_imports(draw):
    """Generate Python code with heavy library imports."""
    libraries = ["pandas", "modin", "polars", "pyarrow", "dask"]
    lib = draw(st.sampled_from(libraries))
    return f"import {lib}\nresult = {lib}.__version__"

@st.composite
def valid_lightweight_code(draw):
    """Generate valid lightweight Python code."""
    operations = [
        "result = 1 + 1",
        "result = [x**2 for x in range(10)]",
        "result = sum(range(100))"
    ]
    return draw(st.sampled_from(operations))
```

### Integration Testing

Integration tests verify end-to-end workflows:

- REST API query → code generation → validation → execution → response
- Event Hub message → parsing → job creation → execution → completion event
- Validation failure → correction → retry → success
- Heavy code → Kubernetes Job → result storage → event emission

### Performance Testing

Performance tests verify system meets latency and throughput requirements:

- Validation completes within 30ms (Property 4)
- Lightweight execution completes within configured timeout
- System handles concurrent requests without degradation
- Kubernetes Job creation completes within 5 seconds

## Security Considerations

### Code Validation Layer

The AST-based validator provides the first line of defense:
- Prevents file system access
- Blocks OS command execution
- Restricts network operations
- Validates imports against allowlist

### Execution Isolation

Multiple layers of isolation protect the system:

**Subprocess Isolation**:
- Restricted environment variables
- Isolated working directory
- No access to parent process resources

**Container Isolation**:
- Read-only root filesystem
- Non-root user execution
- No privilege escalation
- seccomp profiles block dangerous syscalls

**Network Isolation**:
- `--network=none` for lightweight execution
- Kubernetes NetworkPolicy for heavy jobs
- No external network access by default

**Resource Limits**:
- CPU limits prevent resource exhaustion
- Memory limits prevent OOM attacks
- Disk limits prevent storage exhaustion
- Timeout limits prevent infinite loops

### Kubernetes Security

Heavy Job Runner pods enforce additional security:
- Pod Security Standards (restricted)
- Service account with minimal permissions
- No host path mounts
- Immutable container filesystem
- Automatic cleanup via TTL

### Secrets Management

Sensitive configuration is managed securely:
- Azure Key Vault for API keys and credentials
- Kubernetes Secrets for pod-level secrets
- Environment variable injection (not hardcoded)
- Rotation policies for credentials

## Deployment Architecture

### Container Images

**llm-service:latest**
- Base: python:3.11-slim
- Dependencies: langgraph, fastapi, pydantic, azure-eventhub
- Size target: < 500MB
- Security: non-root user, minimal packages

**executor-service:latest**
- Base: python:3.11-slim
- Dependencies: fastapi, pydantic, kubernetes, azure-eventhub
- Size target: < 400MB
- Security: non-root user, seccomp profile

**heavy-executor:latest**
- Base: python:3.11
- Dependencies: pandas, polars, modin, pyarrow, fsspec, adlfs, s3fs, numba
- Size target: < 2GB
- Security: non-root user, read-only filesystem

### Kubernetes Deployment

**LLM Service Deployment**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: llm-service
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: llm-service
        image: llm-service:latest
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "2"
            memory: "4Gi"
        livenessProbe:
          httpGet:
            path: /api/v1/health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
```

**Executor Service Deployment**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: executor-service
spec:
  replicas: 5
  template:
    spec:
      containers:
      - name: executor-service
        image: executor-service:latest
        resources:
          requests:
            cpu: "1"
            memory: "2Gi"
          limits:
            cpu: "4"
            memory: "8Gi"
        securityContext:
          runAsNonRoot: true
          readOnlyRootFilesystem: true
```

### Scaling Strategy

**Horizontal Scaling**:
- LLM Service: Scale based on API request rate
- Executor Service: Scale based on active executions
- Heavy Job Runner: Kubernetes autoscaling based on pending jobs

**Vertical Scaling**:
- Executor Service: Increase memory for larger code executions
- Heavy Job Runner: Increase CPU/memory for data-intensive workloads

**Auto-scaling Configuration**:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: executor-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: executor-service
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

## Monitoring and Observability

### Metrics

**System Metrics**:
- Request rate (requests/second)
- Validation success rate
- Execution success rate
- Average execution duration
- Active executions count
- Kubernetes Job queue depth

**Performance Metrics**:
- Validation latency (p50, p95, p99)
- Execution latency (p50, p95, p99)
- Job creation latency
- End-to-end request latency

**Error Metrics**:
- Validation failure rate by error type
- Execution failure rate by error type
- Job failure rate
- Retry rate

### Logging

**Structured Logging Format**:
```json
{
  "timestamp": "2024-12-04T10:30:00Z",
  "level": "INFO",
  "service": "executor-service",
  "request_id": "req-123",
  "message": "Code execution completed",
  "duration_ms": 150,
  "exit_code": 0,
  "classification": "lightweight"
}
```

**Log Aggregation**:
- Centralized logging via Azure Log Analytics
- Log retention: 30 days for INFO, 90 days for ERROR
- Searchable by request_id, service, error_type

### Tracing

**Distributed Tracing**:
- OpenTelemetry instrumentation
- Trace propagation across services
- Span annotations for key operations:
  - Code generation
  - Validation
  - Classification
  - Execution
  - Job creation

### Alerting

**Critical Alerts**:
- Validation failure rate > 50%
- Execution failure rate > 30%
- Job failure rate > 20%
- Service health check failures
- Resource exhaustion (CPU/memory > 90%)

**Warning Alerts**:
- Validation latency > 50ms
- Execution latency > 10s
- Job queue depth > 100
- Retry rate > 10%

## Future Enhancements

### Code Optimization

- LLM-driven code optimization before execution
- Caching of frequently executed code patterns
- Pre-compilation of validated code

### Advanced Security

- Machine learning-based anomaly detection
- Runtime behavior monitoring
- Automated threat response

### Performance Improvements

- Code execution result caching
- Warm pool of executor containers
- GPU support for ML workloads

### Extended Capabilities

- Multi-language support (R, Julia, SQL)
- Interactive execution with state preservation
- Collaborative code execution sessions
- Integration with data catalogs and lineage tracking
