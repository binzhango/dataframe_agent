# Implementation Plan

- [x] 1. Set up project structure and shared library
  - Create monorepo directory structure with llm_service, executor_service, job_runner, shared, and infra folders
  - Implement shared Pydantic models for CodeExecutionRequest, ValidationResult, ExecutionResult, and ResourceLimits
  - Create common logging utility with structured logging format including request_id field
  - Implement configuration loader using Pydantic Settings for all components
  - Set up exception types for validation, execution, and job errors
  - _Requirements: 7.3, 7.4, 7.5_

- [x] 1.1 Write property test for structured logging
  - **Property 18: Structured logging includes request ID**
  - **Validates: Requirements 5.5, 6.1**

- [x] 2. Implement Code Validator with AST analysis
  - Create AST parser that analyzes Python code structure
  - Implement NoFileIORule validation rule that detects file operations (open, read, write)
  - Implement NoOSCommandsRule validation rule that detects OS command execution (os.system, subprocess)
  - Implement NoNetworkRule validation rule that detects network operations (socket, urllib, requests)
  - Implement ImportValidationRule that checks imports against allowlist and identifies prohibited imports
  - Create CodeValidator class that orchestrates all validation rules and returns ValidationResult
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 2.1 Write property test for AST parsing performance
  - **Property 4: AST parsing performance**
  - **Validates: Requirements 2.1**

- [x] 2.2 Write property test for restricted operations detection
  - **Property 5: Restricted operations are rejected**
  - **Validates: Requirements 2.2**

- [x] 2.3 Write property test for unauthorized imports detection
  - **Property 6: Unauthorized imports are detected**
  - **Validates: Requirements 2.3**

- [x] 3. Implement Code Classifier for routing logic
  - Create CodeComplexity enum with LIGHTWEIGHT and HEAVY values
  - Implement CodeClassifier class that analyzes code using AST
  - Add detection logic for heavy imports (pandas, modin, polars, pyarrow, dask, ray, pyspark)
  - Add detection logic for file I/O operations that trigger heavy classification
  - Add detection logic for large input sizes and loop complexity
  - _Requirements: 4.1, 4.2_

- [x] 3.1 Write property test for heavy imports classification
  - **Property 12: Heavy imports trigger heavy classification**
  - **Validates: Requirements 4.1**

- [x] 3.2 Write property test for file I/O classification
  - **Property 13: File I/O triggers heavy classification**
  - **Validates: Requirements 4.2**

- [x] 3.3 Write property test for routing matches classification
  - **Property 3: Routing matches classification**
  - **Validates: Requirements 1.4**

- [x] 4. Build LangGraph orchestration flow for LLM Service
  - Create InputParserNode that extracts intent and parameters from natural language queries
  - Create CodeGenerationNode that calls LLM with structured prompts
  - Create CodeValidatorNode that invokes the CodeValidator and returns validation results
  - Create CorrectionNode that sends validation errors back to LLM for code correction with retry limit (max 3)
  - Create ExecutionRouterNode that uses CodeClassifier to determine execution environment
  - Wire nodes together in LangGraph DAG with proper state management
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 4.1 Write property test for validation precedes execution
  - **Property 1: Validation precedes execution**
  - **Validates: Requirements 1.2**

- [x] 4.2 Write property test for validation errors trigger correction
  - **Property 2: Validation errors trigger correction**
  - **Validates: Requirements 1.3, 2.4**

- [x] 4.3 Write property test for valid code proceeds to routing
  - **Property 7: Valid code proceeds to routing**
  - **Validates: Requirements 2.5**

- [x] 4.4 Write property test for validation retry limit
  - **Property 23: Validation retry limit**
  - **Validates: Requirements 9.1**

- [x] 5. Implement LLM Service REST API
  - Create FastAPI application with CORS and error handling middleware
  - Implement POST /api/v1/query endpoint that accepts natural language queries
  - Wire endpoint to LangGraph flow for code generation, validation, and routing
  - Implement GET /api/v1/health endpoint that returns service status
  - Add request ID generation and propagation through the pipeline
  - _Requirements: 1.5, 6.5_

- [x] 5.1 Write unit test for health endpoint
  - Test that /api/v1/health returns 200 status and service information
  - _Requirements: 6.5_

- [x] 6. Implement Executor Service core execution engine
  - Create executor_service directory structure under src/llm_executor/
  - Implement SecureExecutor class with subprocess-based code execution
  - Add timeout enforcement using subprocess timeout parameter
  - Implement output capture for stdout and stderr with duration tracking
  - Add restricted environment variables (no PATH, limited env vars)
  - Implement working directory isolation using temporary directories
  - _Requirements: 3.1, 3.4, 3.5, 6.2_

- [x] 6.1 Write property test for timeout termination
  - **Property 10: Timeout terminates execution**
  - **Validates: Requirements 3.4**

- [x] 6.2 Write property test for output capture
  - **Property 11: Output capture completeness**
  - **Validates: Requirements 3.5**

- [x] 6.3 Write property test for execution duration recording
  - **Property 19: Execution duration is recorded**
  - **Validates: Requirements 6.2**

- [x] 7. Implement Executor Service REST API
  - Create FastAPI application for Executor Service
  - Implement POST /api/v1/execute_snippet endpoint that executes lightweight code using SecureExecutor
  - Implement GET /api/v1/health endpoint with active executions count
  - Add request validation using Pydantic models
  - Add error handling for execution failures with appropriate HTTP status codes
  - Wire endpoint to SecureExecutor for code execution
  - _Requirements: 3.1, 6.5_

- [x] 7.1 Write property test for lightweight code uses restricted namespace
  - **Property 8: Lightweight code uses restricted namespace**
  - **Validates: Requirements 3.1**

- [x] 7.2 Write unit test for health endpoint
  - Test that /api/v1/health returns service status and active execution count
  - _Requirements: 6.5_

- [ ] 8. Implement Kubernetes Job creation and management
  - Create KubernetesJobManager class in executor_service
  - Implement job creation logic using Kubernetes Python client (kubernetes library)
  - Create Job template with CPU and memory limits from ResourceLimits model
  - Add job naming with unique identifiers (job_id based on request_id)
  - Configure TTL for automatic cleanup (ttlSecondsAfterFinished: 3600)
  - Add PreStop lifecycle hooks for graceful shutdown
  - Configure pod security context (runAsNonRoot, readOnlyRootFilesystem, no privilege escalation)
  - _Requirements: 4.3, 8.1, 8.2, 8.3, 8.4_

- [ ] 8.1 Implement POST /api/v1/create_heavy_job endpoint
  - Add endpoint to Executor Service API that creates Kubernetes Jobs
  - Wire endpoint to KubernetesJobManager for job creation
  - Return job_id, status, and created_at timestamp
  - _Requirements: 4.3_

- [ ] 8.2 Write property test for heavy code creates Kubernetes Job
  - **Property 14: Heavy code creates Kubernetes Job**
  - **Validates: Requirements 4.3, 8.1**

- [ ] 8.3 Write unit test for job security configuration
  - Test that created jobs have correct security context and resource limits
  - _Requirements: 8.2_

- [ ] 8.4 Write unit test for job TTL cleanup
  - Test that completed jobs are configured with TTL for automatic cleanup
  - _Requirements: 8.3_

- [ ] 8.5 Write unit test for PreStop hooks
  - Test that job pods have PreStop hooks configured
  - _Requirements: 8.4_

- [ ] 9. Build Heavy Job Runner execution logic
  - Create runner.py script in job_runner directory as main entry point
  - Implement code fetching from environment variables (CODE, REQUEST_ID, TIMEOUT)
  - Implement code execution in subprocess with timeout enforcement
  - Add result capture and serialization to JSON format
  - Implement result upload to Azure Blob Storage using fsspec and adlfs libraries
  - Add support for S3 result storage using s3fs library
  - Implement temporary file cleanup after execution (success or failure)
  - Add structured logging with request_id throughout execution
  - _Requirements: 4.4, 8.5_

- [ ] 9.1 Write property test for temporary file cleanup
  - **Property 22: Temporary file cleanup**
  - **Validates: Requirements 8.5**

- [ ] 10. Implement Event Hub integration for Heavy Job Runner
  - Add Azure Event Hub producer client initialization in runner.py
  - Implement completion event emission with request_id, status, result_location, and duration_ms
  - Add error event emission for failed executions with error details
  - Implement structured event payload using ExecutionResult model
  - Add connection string configuration from HeavyJobRunnerConfig
  - _Requirements: 4.5, 5.3_

- [ ] 10.1 Write property test for job completion emits event
  - **Property 15: Job completion emits event**
  - **Validates: Requirements 4.5, 5.3**

- [ ] 11. Implement Event Hub consumer in Executor Service
  - Create EventHubConsumer class in executor_service
  - Implement consumer that subscribes to code-execution-requests topic
  - Implement message parsing and validation using CodeExecutionRequest model
  - Add routing logic that uses CodeClassifier to determine execution path
  - For heavy code, invoke KubernetesJobManager to create jobs
  - For lightweight code, invoke SecureExecutor directly
  - Implement error handling that logs failures without blocking Event Hub retry
  - Add structured logging with request_id for all Event Hub message processing
  - _Requirements: 5.1, 5.2, 5.4, 5.5_

- [ ] 11.1 Write property test for Event Hub message parsing
  - **Property 16: Event Hub message parsing**
  - **Validates: Requirements 5.1**

- [ ] 11.2 Write property test for Event Hub heavy code routing
  - **Property 17: Event Hub heavy code routing**
  - **Validates: Requirements 5.2**

- [ ] 11.3 Write unit test for Event Hub error handling
  - Test that processing failures are logged and message is not acknowledged
  - _Requirements: 5.4_

- [ ] 12. Build Heavy Job Runner Docker image with data libraries
  - Create deploy/docker/heavy-job-runner/Dockerfile based on python:3.11
  - Install pandas, modin, polars, pyarrow, cloudpickle, fsspec, adlfs, s3fs, and numba
  - Copy job_runner source code and install llm_executor package
  - Configure non-root user (UID 1000) for security
  - Set ENTRYPOINT to python -m llm_executor.job_runner.runner
  - Add labels for version and component identification
  - Optimize image size with multi-stage build if needed
  - _Requirements: 10.1, 10.2, 10.3_

- [ ] 12.1 Write property test for supported libraries are importable
  - **Property 27: Supported libraries are importable**
  - **Validates: Requirements 10.2**

- [ ] 12.2 Write unit test for library availability
  - Test that all required libraries can be imported without errors
  - _Requirements: 10.1_

- [ ] 12.3 Write unit test for cloud storage support
  - Test that fsspec with adlfs and s3fs can access mock storage
  - _Requirements: 10.3_

- [ ] 13. Implement error handling and retry logic
  - Create error_handlers.py module in executor_service
  - Implement ExecutionErrorHandler that categorizes errors as retryable or non-retryable
  - Add exponential backoff calculation for retryable execution errors (2^attempt, max 60s)
  - Add logic to mark TimeoutError as non-retryable
  - Implement retry wrapper for SecureExecutor that respects max_retries from config
  - Implement max retry exhaustion handling that returns detailed failure response
  - Add JobErrorHandler that monitors Kubernetes Job status via watch API
  - Implement failure event emission for jobs that exceed retry limits
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 13.1 Write property test for execution retry policy
  - **Property 24: Execution retry policy**
  - **Validates: Requirements 9.2**

- [ ] 13.2 Write property test for timeout errors are not retried
  - **Property 25: Timeout errors are not retried**
  - **Validates: Requirements 9.4**

- [ ] 13.3 Write property test for max retries returns failure
  - **Property 26: Max retries returns failure**
  - **Validates: Requirements 9.5**

- [ ] 13.4 Write unit test for Kubernetes Job retry
  - Test that failed jobs trigger retry according to backoff policy
  - _Requirements: 9.3_

- [ ] 14. Implement job history and metadata storage
  - Create database schema for job execution history (timestamp, status, resource_usage, request_id)
  - Implement repository pattern for storing and querying job history
  - Add metadata recording for all completed executions
  - Implement query endpoints for job history retrieval
  - _Requirements: 6.3_

- [ ] 14.1 Write property test for job history contains metadata
  - **Property 20: Job history contains metadata**
  - **Validates: Requirements 6.3**

- [ ] 15. Implement comprehensive error logging
  - Update all error handlers to include stack traces in log entries
  - Add context information (request_id, component, operation) to all error logs
  - Implement log aggregation configuration for Azure Log Analytics
  - Set up log retention policies (30 days INFO, 90 days ERROR)
  - _Requirements: 6.4_

- [ ] 15.1 Write property test for error logs contain stack traces
  - **Property 21: Error logs contain stack traces**
  - **Validates: Requirements 6.4**

- [ ] 16. Create Kubernetes deployment manifests
  - Create Deployment manifest for LLM Service with 3 replicas and resource limits
  - Create Deployment manifest for Executor Service with 5 replicas and security context
  - Create HorizontalPodAutoscaler for Executor Service (min 3, max 20, 70% CPU target)
  - Create Service manifests for both deployments
  - Create ConfigMap for shared configuration
  - Create Secret manifests for sensitive credentials (Event Hub, storage)
  - _Requirements: 7.1, 7.2_

- [ ] 17. Implement monitoring and observability
  - Add Prometheus metrics endpoints to both services (request_rate, validation_success_rate, execution_duration)
  - Implement OpenTelemetry instrumentation for distributed tracing
  - Add span annotations for key operations (generation, validation, classification, execution)
  - Configure trace propagation across service boundaries
  - Set up health check probes (liveness and readiness) for Kubernetes
  - _Requirements: 6.1, 6.2_

- [ ] 17.1 Write unit test for metrics endpoint
  - Test that metrics endpoint exposes required metrics in Prometheus format
  - _Requirements: 6.2_

- [ ] 18. Create end-to-end integration tests
  - Write test for REST API query → code generation → validation → lightweight execution → response
  - Write test for REST API query → code generation → validation → heavy job creation → completion
  - Write test for Event Hub message → parsing → job creation → execution → completion event
  - Write test for validation failure → correction → retry → success flow
  - Write test for execution failure → retry → success flow
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.3, 4.5, 5.1, 5.2, 5.3_

- [ ] 19. Implement configuration management
  - Create Pydantic Settings classes for LLM Service configuration (LLM endpoint, validation rules, retry limits)
  - Create Pydantic Settings classes for Executor Service configuration (timeout, resource limits, Event Hub connection)
  - Create Pydantic Settings classes for Heavy Job Runner configuration (storage credentials, Event Hub connection)
  - Add environment variable loading with validation
  - Implement configuration validation on service startup
  - _Requirements: 7.4_

- [ ] 19.1 Write unit test for configuration loading
  - Test that each component loads configuration independently from environment
  - _Requirements: 7.4_

- [ ] 20. Build Docker images for all components
  - Create Dockerfile for LLM Service (python:3.11-slim, < 500MB target)
  - Create Dockerfile for Executor Service (python:3.11-slim, < 400MB target)
  - Optimize images with multi-stage builds and minimal dependencies
  - Configure non-root users in all images
  - Add health check commands to Dockerfiles
  - _Requirements: 7.1, 7.2_

- [ ] 21. Set up CI/CD pipeline
  - Create GitHub Actions workflow for running unit tests and property tests
  - Add Docker image building and pushing to container registry
  - Implement Kubernetes manifest validation
  - Add integration test execution in CI
  - Configure automated deployment to staging environment
  - _Requirements: 7.1, 7.2_

- [ ] 22. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
