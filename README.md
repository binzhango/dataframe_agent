# LLM-Driven Secure Python Execution Platform

A distributed system that transforms natural language queries into executable Python code through an LLM-powered pipeline with intelligent routing and secure execution environments.

## Features

- 🤖 Natural language to Python code generation using LangGraph
- 🔒 Multi-layer security with AST-based validation and sandboxed execution
- ⚡ Intelligent routing between lightweight and heavy workloads
- 🎯 Kubernetes-based execution for resource-intensive tasks
- 📊 Support for data processing libraries (pandas, polars, modin, etc.)
- 🔄 Event-driven architecture with Azure Event Hub
- 📝 Comprehensive structured logging and observability

## Architecture

The platform consists of three primary components:

- **LLM Service**: Code generation and validation orchestration
- **Executor Service**: Lightweight code execution and job management
- **Heavy Job Runner**: Kubernetes Jobs for resource-intensive workloads

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/llm-python-executor.git
cd llm-python-executor

# Install dependencies
pip install -e ".[dev]"
```

## Development

```bash
# Install development dependencies
pip install -e ".[dev,test]"

# Run tests
pytest

# Run property-based tests
pytest tests/test_properties/
```

## Project Structure

```
llm-python-executor/
├── src/
│   └── llm_executor/
│       ├── shared/          # Shared models, utilities, and exceptions
│       ├── llm_service/     # LLM Service implementation
│       ├── executor/        # Executor Service implementation
│       └── job_runner/      # Heavy Job Runner implementation
├── tests/                   # Test suite
├── docs/                    # Documentation
├── deploy/                  # Deployment configurations
│   ├── kubernetes/          # K8s manifests
│   └── docker/              # Dockerfiles
└── examples/                # Usage examples

```

## License

See [LICENSE](LICENSE) file for details.
