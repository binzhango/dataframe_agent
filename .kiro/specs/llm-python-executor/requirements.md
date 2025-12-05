# Requirements Document

## Introduction

The LLM-Driven Secure Python Execution Platform is a system that receives natural language queries, generates Python code using LangGraph and LLM, validates the generated code, and executes it in secure, isolated environments. The system intelligently routes code execution based on complexity and resource requirements: lightweight code executes in a fast executor service, while heavy data transformation jobs run in Kubernetes Job pods. The platform supports both REST API and Event Hub triggers, ensuring strong security and isolation throughout the execution pipeline.

## Glossary

- **LLM Service**: The container (Container A) responsible for receiving queries, generating Python code via LangGraph, and validating code before execution
- **Executor Service**: The long-running container (Container B) that executes validated Python code in a secure sandbox environment
- **Heavy Job Runner**: Kubernetes Job pods that execute resource-intensive data transformation tasks with specialized libraries
- **Code Validator**: Component that performs AST-based analysis to ensure generated code meets security constraints
- **LangGraph**: Framework used to orchestrate the code generation and validation workflow
- **Routing Logic**: Decision mechanism that classifies code as lightweight or heavy based on imports, complexity, and resource requirements
- **Event Hub**: Azure Event Hub service used for asynchronous job triggering and completion notifications
- **Sandbox**: Isolated execution environment with restricted capabilities (no file I/O, no OS commands, no network access)

## Requirements

### Requirement 1

**User Story:** As a data analyst, I want to submit natural language queries that generate and execute Python code, so that I can perform data analysis without writing code manually.

#### Acceptance Criteria

1. WHEN a user submits a natural language query via REST API, THEN the LLM Service SHALL generate Python code that addresses the query intent
2. WHEN the LLM Service generates Python code, THEN the LLM Service SHALL validate the code using AST-based analysis before execution
3. WHEN code validation fails, THEN the LLM Service SHALL send the validation errors back to the LLM for correction
4. WHEN code validation succeeds, THEN the LLM Service SHALL route the code to the appropriate execution environment based on complexity classification
5. WHEN code execution completes successfully, THEN the System SHALL return the execution results to the user via the REST API response

### Requirement 2

**User Story:** As a security engineer, I want all generated Python code to be validated against security constraints, so that malicious or unsafe code cannot execute in the system.

#### Acceptance Criteria

1. WHEN the Code Validator receives Python code, THEN the Code Validator SHALL parse the code using AST analysis within 30 milliseconds
2. WHEN the Code Validator detects restricted operations (file I/O, OS commands, socket operations), THEN the Code Validator SHALL reject the code and return specific validation errors
3. WHEN the Code Validator detects unauthorized imports, THEN the Code Validator SHALL reject the code and identify the prohibited imports
4. WHEN validation errors occur, THEN the LLM Service SHALL provide the errors to the LLM for code correction
5. WHEN the corrected code passes validation, THEN the System SHALL proceed with execution routing

### Requirement 3

**User Story:** As a platform operator, I want lightweight code to execute quickly in a long-running service, so that simple queries have minimal latency.

#### Acceptance Criteria

1. WHEN the Routing Logic classifies code as lightweight, THEN the Executor Service SHALL execute the code in a restricted namespace with timeout enforcement
2. WHEN the Executor Service executes code, THEN the Executor Service SHALL enforce CPU and memory limits using cgroups
3. WHEN the Executor Service executes code, THEN the Executor Service SHALL disable network access using network isolation
4. WHEN code execution exceeds the configured timeout, THEN the Executor Service SHALL terminate the execution and return a timeout error
5. WHEN code execution completes, THEN the Executor Service SHALL capture stdout and stderr and return them in the response

### Requirement 4

**User Story:** As a data engineer, I want resource-intensive data transformation code to execute in dedicated Kubernetes Job pods, so that heavy workloads do not impact the responsiveness of the core services.

#### Acceptance Criteria

1. WHEN the Routing Logic detects heavy imports (pandas, modin, polars, pyarrow), THEN the System SHALL classify the code as heavy and route it to Kubernetes Job execution
2. WHEN the Routing Logic detects file I/O operations or large input sizes, THEN the System SHALL classify the code as heavy
3. WHEN heavy code is identified, THEN the Executor Service SHALL create a Kubernetes Job with appropriate CPU and memory limits
4. WHEN the Heavy Job Runner executes code, THEN the Heavy Job Runner SHALL write results to Blob Storage or S3
5. WHEN the Heavy Job Runner completes execution, THEN the Heavy Job Runner SHALL emit a completion event to Event Hub with the result location

### Requirement 5

**User Story:** As a system administrator, I want the system to support Event Hub triggers for asynchronous job processing, so that jobs can be queued and processed independently of REST API requests.

#### Acceptance Criteria

1. WHEN the Executor Service receives a message from Event Hub, THEN the Executor Service SHALL parse the message and extract the code execution request
2. WHEN an Event Hub message contains heavy code, THEN the Executor Service SHALL create a Kubernetes Job for execution
3. WHEN a Kubernetes Job completes, THEN the System SHALL publish a completion event to Event Hub with execution status and results
4. WHEN Event Hub message processing fails, THEN the System SHALL log the error and allow Event Hub retry mechanisms to handle reprocessing
5. WHEN the Executor Service processes Event Hub messages, THEN the Executor Service SHALL maintain structured logs for job tracking

### Requirement 6

**User Story:** As a DevOps engineer, I want comprehensive logging and telemetry throughout the execution pipeline, so that I can monitor system health and troubleshoot issues.

#### Acceptance Criteria

1. WHEN any component processes a request, THEN the component SHALL emit structured logs with request identifiers
2. WHEN code execution completes, THEN the System SHALL record execution duration statistics
3. WHEN the System maintains job run history, THEN the System SHALL store execution metadata including timestamps, status, and resource usage
4. WHEN errors occur in any component, THEN the System SHALL log detailed error information including stack traces and context
5. WHEN the Executor Service or Heavy Job Runner starts, THEN the component SHALL expose health check endpoints that report service status

### Requirement 7

**User Story:** As a platform architect, I want clear separation between the LLM service, executor service, and heavy job runner, so that the system is maintainable and each component can scale independently.

#### Acceptance Criteria

1. WHEN the LLM Service generates and validates code, THEN the LLM Service SHALL communicate with the Executor Service only via REST API
2. WHEN the Executor Service creates Kubernetes Jobs, THEN the Executor Service SHALL use the Kubernetes API without direct coupling to job implementation
3. WHEN shared data models are needed, THEN all components SHALL use Pydantic models from a shared library
4. WHEN configuration changes occur, THEN each component SHALL load configuration independently using Pydantic Settings
5. WHEN components log events, THEN all components SHALL use a common logging utility from the shared library

### Requirement 8

**User Story:** As a security engineer, I want the Heavy Job Runner to execute in isolated Kubernetes pods with strict resource limits, so that heavy workloads cannot compromise cluster stability.

#### Acceptance Criteria

1. WHEN a Kubernetes Job is created, THEN the System SHALL apply CPU and memory limits defined in the job template
2. WHEN a Heavy Job Runner pod starts, THEN the pod SHALL enforce pod-level security policies including seccomp profiles
3. WHEN a Kubernetes Job completes, THEN the System SHALL automatically clean up the job based on TTL configuration
4. WHEN a Heavy Job Runner pod terminates, THEN the pod SHALL execute PreStop hooks to ensure graceful shutdown
5. WHEN disk usage accumulates, THEN the System SHALL clean up temporary files created during job execution

### Requirement 9

**User Story:** As a developer, I want the system to automatically retry failed validations and executions with appropriate backoff strategies, so that transient failures do not require manual intervention.

#### Acceptance Criteria

1. WHEN code validation fails due to correctable issues, THEN the LLM Service SHALL retry code generation with validation feedback up to a maximum retry count
2. WHEN code execution fails in the Executor Service, THEN the System SHALL retry execution according to configured retry policies
3. WHEN a Kubernetes Job fails, THEN the System SHALL retry job creation according to Kubernetes backoff policies
4. WHEN timeout errors occur, THEN the System SHALL not retry automatically but SHALL return the timeout error to the caller
5. WHEN maximum retry attempts are reached, THEN the System SHALL return a failure response with detailed error information

### Requirement 10

**User Story:** As a data scientist, I want the Heavy Job Runner to support common data processing libraries, so that I can perform complex data transformations using familiar tools.

#### Acceptance Criteria

1. WHEN the Heavy Job Runner image is built, THEN the image SHALL include pandas, modin, polars, pyarrow, cloudpickle, fsspec, adlfs, s3fs, and numba libraries
2. WHEN heavy code imports supported libraries, THEN the Heavy Job Runner SHALL execute the code without import errors
3. WHEN heavy code requires cloud storage access, THEN the Heavy Job Runner SHALL support Azure Data Lake Storage and S3 via fsspec
4. WHEN the Heavy Job Runner executes code, THEN the Heavy Job Runner SHALL provide sufficient memory for typical data transformation workloads
5. WHEN library dependencies are updated, THEN the Heavy Job Runner image SHALL be rebuilt with updated versions
