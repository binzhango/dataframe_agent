# Kubernetes Deployment Manifests

This directory contains Kubernetes manifests for deploying the LLM-Driven Secure Python Execution Platform.

## Architecture

The platform consists of two main services:

1. **LLM Service** - Handles code generation, validation, and routing
2. **Executor Service** - Executes lightweight code and manages heavy Kubernetes Jobs

## Components

### Deployments

- `llm-service-deployment.yaml` - LLM Service with 3 replicas
- `executor-service-deployment.yaml` - Executor Service with 5 replicas

### Services

- `llm-service-service.yaml` - ClusterIP service for LLM Service (port 8000)
- `executor-service-service.yaml` - ClusterIP service for Executor Service (port 8001)

### Autoscaling

- `executor-service-hpa.yaml` - HorizontalPodAutoscaler (min 3, max 20 replicas, 70% CPU target)

### Configuration

- `configmap.yaml` - Shared configuration for all components
- `secrets.yaml` - Sensitive credentials (Event Hub, storage, LLM API keys)

### RBAC

- `executor-service-rbac.yaml` - ServiceAccount, Role, and RoleBinding for Job management

## Prerequisites

1. Kubernetes cluster (v1.24+)
2. kubectl configured to access the cluster
3. Container images built and pushed to a registry:
   - `llm-service:latest`
   - `executor-service:latest`
   - `heavy-executor:latest`

## Deployment Steps

### 1. Update Secrets

**IMPORTANT**: Before deploying, update `secrets.yaml` with actual credentials:

```bash
# Edit secrets.yaml and replace placeholder values
vim secrets.yaml
```

Replace the following placeholders:
- `REPLACE_WITH_ACTUAL_LLM_API_KEY`
- `REPLACE_WITH_ACTUAL_EVENT_HUB_CONNECTION_STRING`
- `REPLACE_WITH_ACTUAL_STORAGE_CONNECTION_STRING`
- `REPLACE_WITH_ACTUAL_DB_PASSWORD`
- `REPLACE_WITH_ACTUAL_AWS_ACCESS_KEY` (if using S3)
- `REPLACE_WITH_ACTUAL_AWS_SECRET_KEY` (if using S3)

**Production Recommendation**: Use external secret management:
- Azure Key Vault with CSI driver
- HashiCorp Vault
- AWS Secrets Manager
- Sealed Secrets

### 2. Update ConfigMap (Optional)

Review and adjust configuration values in `configmap.yaml`:

```bash
vim configmap.yaml
```

Key configurations:
- `log_level` - Logging verbosity (INFO, DEBUG, WARNING, ERROR)
- `max_retries` - Maximum validation/execution retry attempts
- `execution_timeout` - Timeout for lightweight code execution (seconds)
- `heavy_job_*` - Resource limits for heavy Kubernetes Jobs

### 3. Deploy in Order

```bash
# Create namespace (optional)
kubectl create namespace llm-executor

# Deploy RBAC resources
kubectl apply -f executor-service-rbac.yaml

# Deploy ConfigMap and Secrets
kubectl apply -f configmap.yaml
kubectl apply -f secrets.yaml

# Deploy Services
kubectl apply -f llm-service-service.yaml
kubectl apply -f executor-service-service.yaml

# Deploy Deployments
kubectl apply -f llm-service-deployment.yaml
kubectl apply -f executor-service-deployment.yaml

# Deploy HorizontalPodAutoscaler
kubectl apply -f executor-service-hpa.yaml
```

### 4. Deploy All at Once (Alternative)

```bash
kubectl apply -f .
```

## Verification

### Check Deployment Status

```bash
# Check all resources
kubectl get all -l app=llm-service
kubectl get all -l app=executor-service

# Check pod status
kubectl get pods

# Check HPA status
kubectl get hpa executor-service-hpa
```

### Check Logs

```bash
# LLM Service logs
kubectl logs -l app=llm-service -f

# Executor Service logs
kubectl logs -l app=executor-service -f
```

### Test Health Endpoints

```bash
# Port-forward to test locally
kubectl port-forward svc/llm-service 8000:8000
kubectl port-forward svc/executor-service 8001:8001

# Test health endpoints
curl http://localhost:8000/api/v1/health
curl http://localhost:8001/api/v1/health
```

## Scaling

### Manual Scaling

```bash
# Scale LLM Service
kubectl scale deployment llm-service --replicas=5

# Scale Executor Service (will be overridden by HPA)
kubectl scale deployment executor-service --replicas=10
```

### Autoscaling

The Executor Service uses HorizontalPodAutoscaler:
- **Min replicas**: 3
- **Max replicas**: 20
- **CPU target**: 70%
- **Memory target**: 80%

Monitor autoscaling:

```bash
kubectl get hpa executor-service-hpa --watch
```

## Resource Requirements

### LLM Service (per pod)

- **Requests**: 500m CPU, 1Gi memory
- **Limits**: 2 CPU, 4Gi memory
- **Replicas**: 3 (fixed)

### Executor Service (per pod)

- **Requests**: 1 CPU, 2Gi memory
- **Limits**: 4 CPU, 8Gi memory
- **Replicas**: 3-20 (autoscaled)

### Heavy Job Runner (per job)

- **Requests**: 2 CPU, 4Gi memory
- **Limits**: 4 CPU, 8Gi memory
- **TTL**: 3600 seconds (1 hour after completion)

## Security

### Pod Security

Both services run with security hardening:
- Non-root user (UID 1000)
- No privilege escalation
- Dropped capabilities
- Read-only root filesystem (Executor Service)

### RBAC

The Executor Service has minimal permissions:
- Create/manage Jobs in the same namespace
- Read Pod logs and status
- No cluster-wide permissions

### Secrets Management

**Development**: Kubernetes Secrets (base64 encoded)

**Production**: Use external secret management:

```yaml
# Example: Azure Key Vault CSI driver
apiVersion: secrets-store.csi.x-k8s.io/v1
kind: SecretProviderClass
metadata:
  name: llm-executor-secrets-provider
spec:
  provider: azure
  parameters:
    keyvaultName: "your-keyvault"
    objects: |
      array:
        - objectName: llm-api-key
          objectType: secret
```

## Monitoring

### Metrics

Both services expose Prometheus metrics (if implemented):

```bash
# Port-forward and check metrics
kubectl port-forward svc/llm-service 8000:8000
curl http://localhost:8000/metrics

kubectl port-forward svc/executor-service 8001:8001
curl http://localhost:8001/metrics
```

### Health Checks

- **Liveness Probe**: Restarts pod if unhealthy
- **Readiness Probe**: Removes pod from service if not ready

## Troubleshooting

### Pods Not Starting

```bash
# Check pod events
kubectl describe pod <pod-name>

# Check logs
kubectl logs <pod-name>

# Check resource constraints
kubectl top pods
```

### Jobs Not Creating

```bash
# Check executor service logs
kubectl logs -l app=executor-service | grep -i job

# Check RBAC permissions
kubectl auth can-i create jobs --as=system:serviceaccount:default:executor-service

# List jobs
kubectl get jobs
```

### Configuration Issues

```bash
# Check ConfigMap
kubectl get configmap llm-executor-config -o yaml

# Check Secrets (values are base64 encoded)
kubectl get secret llm-executor-secrets -o yaml
```

### HPA Not Scaling

```bash
# Check HPA status
kubectl describe hpa executor-service-hpa

# Check metrics server
kubectl top pods

# Check HPA events
kubectl get events --field-selector involvedObject.name=executor-service-hpa
```

## Cleanup

```bash
# Delete all resources
kubectl delete -f .

# Or delete by label
kubectl delete all -l app=llm-service
kubectl delete all -l app=executor-service
kubectl delete configmap llm-executor-config
kubectl delete secret llm-executor-secrets
kubectl delete serviceaccount executor-service
kubectl delete role executor-service-role
kubectl delete rolebinding executor-service-rolebinding
```

## Production Considerations

1. **Image Registry**: Update image references to your registry
2. **Ingress**: Add Ingress for external access
3. **TLS**: Configure TLS certificates
4. **Network Policies**: Restrict pod-to-pod communication
5. **Resource Quotas**: Set namespace resource limits
6. **Pod Disruption Budgets**: Ensure availability during updates
7. **Monitoring**: Deploy Prometheus and Grafana
8. **Logging**: Configure log aggregation (ELK, Azure Log Analytics)
9. **Backup**: Regular backup of ConfigMaps and Secrets
10. **Disaster Recovery**: Multi-region deployment strategy

## References

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [HorizontalPodAutoscaler](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)
- [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [RBAC Authorization](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
