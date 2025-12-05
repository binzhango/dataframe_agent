#!/bin/bash

# LLM Executor Platform Deployment Script
# This script deploys the LLM-Driven Secure Python Execution Platform to Kubernetes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
NAMESPACE="default"
ENVIRONMENT="base"
DRY_RUN=false
SKIP_SECRETS_CHECK=false

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy the LLM Executor Platform to Kubernetes

OPTIONS:
    -n, --namespace NAMESPACE    Kubernetes namespace (default: default)
    -e, --environment ENV        Environment: base, staging, production (default: base)
    -d, --dry-run               Perform a dry run without applying changes
    -s, --skip-secrets-check    Skip secrets validation check
    -h, --help                  Show this help message

EXAMPLES:
    # Deploy to default namespace
    $0

    # Deploy to staging environment
    $0 -e staging -n llm-executor-staging

    # Deploy to production with dry run
    $0 -e production -n llm-executor-prod -d

    # Deploy and skip secrets check (not recommended)
    $0 -s

EOF
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -s|--skip-secrets-check)
            SKIP_SECRETS_CHECK=true
            shift
            ;;
        -h|--help)
            usage
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            ;;
    esac
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(base|staging|production)$ ]]; then
    print_error "Invalid environment: $ENVIRONMENT. Must be base, staging, or production."
    exit 1
fi

print_info "Starting deployment..."
print_info "Environment: $ENVIRONMENT"
print_info "Namespace: $NAMESPACE"
print_info "Dry run: $DRY_RUN"

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl is not installed. Please install kubectl first."
    exit 1
fi

# Check if cluster is accessible
if ! kubectl cluster-info &> /dev/null; then
    print_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
    exit 1
fi

print_info "Connected to cluster: $(kubectl config current-context)"

# Check secrets if not skipped
if [[ "$SKIP_SECRETS_CHECK" == false ]]; then
    print_info "Checking secrets configuration..."
    
    if grep -q "REPLACE_WITH_ACTUAL" secrets.yaml; then
        print_error "Secrets file contains placeholder values!"
        print_error "Please update secrets.yaml with actual credentials before deploying."
        print_error "Use -s flag to skip this check (not recommended for production)."
        exit 1
    fi
    
    print_info "Secrets check passed."
fi

# Create namespace if it doesn't exist
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    print_info "Creating namespace: $NAMESPACE"
    if [[ "$DRY_RUN" == false ]]; then
        kubectl create namespace "$NAMESPACE"
    else
        print_info "[DRY RUN] Would create namespace: $NAMESPACE"
    fi
else
    print_info "Namespace $NAMESPACE already exists."
fi

# Determine deployment path
if [[ "$ENVIRONMENT" == "base" ]]; then
    DEPLOY_PATH="."
else
    DEPLOY_PATH="overlays/$ENVIRONMENT"
    
    if [[ ! -d "$DEPLOY_PATH" ]]; then
        print_error "Environment directory not found: $DEPLOY_PATH"
        exit 1
    fi
fi

# Deploy using kubectl or kustomize
if [[ "$ENVIRONMENT" == "base" ]]; then
    print_info "Deploying base manifests..."
    
    if [[ "$DRY_RUN" == true ]]; then
        print_info "[DRY RUN] Would apply the following resources:"
        kubectl apply -f . --dry-run=client -n "$NAMESPACE"
    else
        # Deploy in order
        print_info "Deploying RBAC resources..."
        kubectl apply -f executor-service-rbac.yaml -n "$NAMESPACE"
        
        print_info "Deploying ConfigMap and Secrets..."
        kubectl apply -f configmap.yaml -n "$NAMESPACE"
        kubectl apply -f secrets.yaml -n "$NAMESPACE"
        
        print_info "Deploying Services..."
        kubectl apply -f llm-service-service.yaml -n "$NAMESPACE"
        kubectl apply -f executor-service-service.yaml -n "$NAMESPACE"
        
        print_info "Deploying Deployments..."
        kubectl apply -f llm-service-deployment.yaml -n "$NAMESPACE"
        kubectl apply -f executor-service-deployment.yaml -n "$NAMESPACE"
        
        print_info "Deploying HorizontalPodAutoscaler..."
        kubectl apply -f executor-service-hpa.yaml -n "$NAMESPACE"
    fi
else
    # Check if kustomize is available
    if command -v kustomize &> /dev/null; then
        print_info "Deploying using kustomize..."
        
        if [[ "$DRY_RUN" == true ]]; then
            print_info "[DRY RUN] Would apply the following resources:"
            kustomize build "$DEPLOY_PATH" | kubectl apply --dry-run=client -f -
        else
            kustomize build "$DEPLOY_PATH" | kubectl apply -f -
        fi
    else
        print_warn "kustomize not found, using kubectl apply -k..."
        
        if [[ "$DRY_RUN" == true ]]; then
            print_info "[DRY RUN] Would apply the following resources:"
            kubectl apply -k "$DEPLOY_PATH" --dry-run=client
        else
            kubectl apply -k "$DEPLOY_PATH"
        fi
    fi
fi

if [[ "$DRY_RUN" == false ]]; then
    print_info "Deployment completed successfully!"
    
    # Wait for deployments to be ready
    print_info "Waiting for deployments to be ready..."
    kubectl wait --for=condition=available --timeout=300s \
        deployment/llm-service deployment/executor-service -n "$NAMESPACE" || true
    
    # Show deployment status
    print_info "Deployment status:"
    kubectl get deployments -n "$NAMESPACE"
    
    print_info "Pod status:"
    kubectl get pods -n "$NAMESPACE"
    
    print_info "Service status:"
    kubectl get services -n "$NAMESPACE"
    
    print_info "HPA status:"
    kubectl get hpa -n "$NAMESPACE"
    
    print_info ""
    print_info "To check logs:"
    print_info "  kubectl logs -l app=llm-service -n $NAMESPACE -f"
    print_info "  kubectl logs -l app=executor-service -n $NAMESPACE -f"
    print_info ""
    print_info "To test health endpoints:"
    print_info "  kubectl port-forward svc/llm-service 8000:8000 -n $NAMESPACE"
    print_info "  kubectl port-forward svc/executor-service 8001:8001 -n $NAMESPACE"
else
    print_info "Dry run completed. No changes were applied."
fi
