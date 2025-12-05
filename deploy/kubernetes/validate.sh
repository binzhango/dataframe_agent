#!/bin/bash

# Kubernetes Manifest Validation Script
# Validates YAML syntax and Kubernetes resource definitions

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    ((ERRORS++))
}

print_info "Starting manifest validation..."

# Check if kubectl is installed
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl is not installed. Please install kubectl first."
    exit 1
fi

# Validate YAML syntax
print_info "Validating YAML syntax..."

for file in *.yaml; do
    if [[ -f "$file" ]]; then
        if kubectl apply -f "$file" --dry-run=client &> /dev/null; then
            print_info "✓ $file - Valid YAML"
        else
            print_error "✗ $file - Invalid YAML"
            kubectl apply -f "$file" --dry-run=client 2>&1 | head -5
        fi
    fi
done

# Check for placeholder values in secrets
print_info "Checking for placeholder values in secrets..."

if grep -q "REPLACE_WITH_ACTUAL" secrets.yaml; then
    print_warn "secrets.yaml contains placeholder values that need to be replaced"
else
    print_info "✓ No placeholder values found in secrets.yaml"
fi

# Validate resource limits
print_info "Validating resource limits..."

for deployment in llm-service-deployment.yaml executor-service-deployment.yaml; do
    if [[ -f "$deployment" ]]; then
        if grep -q "resources:" "$deployment"; then
            if grep -q "limits:" "$deployment" && grep -q "requests:" "$deployment"; then
                print_info "✓ $deployment has resource limits and requests"
            else
                print_warn "$deployment is missing resource limits or requests"
            fi
        else
            print_error "$deployment has no resource configuration"
        fi
    fi
done

# Validate security context
print_info "Validating security context..."

for deployment in llm-service-deployment.yaml executor-service-deployment.yaml; do
    if [[ -f "$deployment" ]]; then
        if grep -q "securityContext:" "$deployment"; then
            if grep -q "runAsNonRoot: true" "$deployment"; then
                print_info "✓ $deployment runs as non-root"
            else
                print_warn "$deployment may not be configured to run as non-root"
            fi
        else
            print_warn "$deployment has no security context"
        fi
    fi
done

# Validate health checks
print_info "Validating health checks..."

for deployment in llm-service-deployment.yaml executor-service-deployment.yaml; do
    if [[ -f "$deployment" ]]; then
        has_liveness=false
        has_readiness=false
        
        if grep -q "livenessProbe:" "$deployment"; then
            has_liveness=true
        fi
        
        if grep -q "readinessProbe:" "$deployment"; then
            has_readiness=true
        fi
        
        if [[ "$has_liveness" == true ]] && [[ "$has_readiness" == true ]]; then
            print_info "✓ $deployment has liveness and readiness probes"
        else
            print_warn "$deployment is missing health check probes"
        fi
    fi
done

# Validate HPA configuration
print_info "Validating HPA configuration..."

if [[ -f "executor-service-hpa.yaml" ]]; then
    if grep -q "minReplicas: 3" executor-service-hpa.yaml; then
        print_info "✓ HPA minReplicas is set to 3"
    else
        print_error "HPA minReplicas is not set to 3 as required"
    fi
    
    if grep -q "maxReplicas: 20" executor-service-hpa.yaml; then
        print_info "✓ HPA maxReplicas is set to 20"
    else
        print_error "HPA maxReplicas is not set to 20 as required"
    fi
    
    if grep -q "averageUtilization: 70" executor-service-hpa.yaml; then
        print_info "✓ HPA CPU target is set to 70%"
    else
        print_error "HPA CPU target is not set to 70% as required"
    fi
fi

# Validate RBAC
print_info "Validating RBAC configuration..."

if [[ -f "executor-service-rbac.yaml" ]]; then
    if grep -q "kind: ServiceAccount" executor-service-rbac.yaml; then
        print_info "✓ ServiceAccount is defined"
    else
        print_error "ServiceAccount is not defined"
    fi
    
    if grep -q "kind: Role" executor-service-rbac.yaml; then
        print_info "✓ Role is defined"
    else
        print_error "Role is not defined"
    fi
    
    if grep -q "kind: RoleBinding" executor-service-rbac.yaml; then
        print_info "✓ RoleBinding is defined"
    else
        print_error "RoleBinding is not defined"
    fi
fi

# Summary
print_info ""
print_info "Validation complete!"
print_info "Errors: $ERRORS"
print_info "Warnings: $WARNINGS"

if [[ $ERRORS -gt 0 ]]; then
    print_error "Validation failed with $ERRORS error(s)"
    exit 1
elif [[ $WARNINGS -gt 0 ]]; then
    print_warn "Validation passed with $WARNINGS warning(s)"
    exit 0
else
    print_info "All validations passed successfully!"
    exit 0
fi
