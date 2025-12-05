# Kubernetes Deployment Checklist

Use this checklist to ensure a successful deployment of the LLM Executor Platform.

## Pre-Deployment Checklist

### 1. Prerequisites
- [ ] Kubernetes cluster is running (v1.24+)
- [ ] kubectl is installed and configured
- [ ] kubectl can connect to the cluster (`kubectl cluster-info`)
- [ ] Container images are built and pushed to registry:
  - [ ] `llm-service:latest`
  - [ ] `executor-service:latest`
  - [ ] `heavy-executor:latest`

### 2. Configuration

#### Secrets (CRITICAL)
- [ ] Open `secrets.yaml`
- [ ] Replace `REPLACE_WITH_ACTUAL_LLM_API_KEY` with actual LLM API key
- [ ] Replace `REPLACE_WITH_ACTUAL_EVENT_HUB_CONNECTION_STRING` with Azure Event Hub connection string
- [ ] Replace `REPLACE_WITH_ACTUAL_STORAGE_CONNECTION_STRING` with Azure Storage connection string
- [ ] Replace `REPLACE_WITH_ACTUAL_DB_PASSWORD` with database password
- [ ] (Optional) Replace AWS credentials if using S3

**WARNING**: Never commit secrets.yaml with actual credentials to version control!

#### ConfigMap (Optional)
- [ ] Review `configmap.yaml` settings
- [ ] Adjust `log_level` if needed (INFO, DEBUG, WARNING, ERROR)
- [ ] Adjust `max_retries` if needed (default: 3)
- [ ] Adjust `execution_timeout` if needed (default: 30 seconds)
- [ ] Adjust resource limits for heavy jobs if needed

#### Image References
- [ ] Update image names in deployment manifests if using custom registry
- [ ] Update image tags if not using `latest`

### 3. Namespace
- [ ] Decide on namespace (default: `default`)
- [ ] Create namespace if it doesn't exist: `kubectl create namespace <name>`

## Deployment Steps

### Option 1: Using Deployment Script (Recommended)

```bash
# Deploy to default namespace
./deploy.sh

# Deploy to custom namespace
./deploy.sh -n llm-executor

# Deploy staging environment
./deploy.sh -e staging -n llm-executor-staging

# Deploy production environment
./deploy.sh -e production -n llm-executor-prod

# Dry run (test without applying)
./deploy.sh -d
```

### Option 2: Manual Deployment

```bash
# Set namespace
NAMESPACE=default

# 1. Deploy RBAC
kubectl apply -f executor-service-rbac.yaml -n $NAMESPACE

# 2. Deploy ConfigMap and Secrets
kubectl apply -f configmap.yaml -n $NAMESPACE
kubectl apply -f secrets.yaml -n $NAMESPACE

# 3. Deploy Services
kubectl apply -f llm-service-service.yaml -n $NAMESPACE
kubectl apply -f executor-service-service.yaml -n $NAMESPACE

# 4. Deploy Deployments
kubectl apply -f llm-service-deployment.yaml -n $NAMESPACE
kubectl apply -f executor-service-deployment.yaml -n $NAMESPACE

# 5. Deploy HPA
kubectl apply -f executor-service-hpa.yaml -n $NAMESPACE
```

### Option 3: Using Kustomize

```bash
# Base deployment
kubectl apply -k .

# Staging deployment
kubectl apply -k overlays/staging

# Production deployment
kubectl apply -k overlays/production
```

## Post-Deployment Verification

### 1. Check Deployment Status
```bash
NAMESPACE=default

# Check all resources
kubectl get all -n $NAMESPACE

# Check deployments
kubectl get deployments -n $NAMESPACE

# Expected output:
# NAME               READY   UP-TO-DATE   AVAILABLE   AGE
# llm-service        3/3     3            3           1m
# executor-service   5/5     5            5           1m
```

### 2. Check Pod Status
```bash
# Check pods
kubectl get pods -n $NAMESPACE

# All pods should be Running
# Expected: 3 llm-service pods, 5 executor-service pods
```

### 3. Check Services
```bash
# Check services
kubectl get services -n $NAMESPACE

# Expected output:
# NAME               TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
# llm-service        ClusterIP   10.x.x.x        <none>        8000/TCP   1m
# executor-service   ClusterIP   10.x.x.x        <none>        8001/TCP   1m
```

### 4. Check HPA
```bash
# Check HPA
kubectl get hpa -n $NAMESPACE

# Expected output:
# NAME                    REFERENCE                     TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
# executor-service-hpa    Deployment/executor-service   0%/70%    3         20        5          1m
```

### 5. Check Logs
```bash
# LLM Service logs
kubectl logs -l app=llm-service -n $NAMESPACE --tail=50

# Executor Service logs
kubectl logs -l app=executor-service -n $NAMESPACE --tail=50

# Look for:
# - No error messages
# - Successful startup messages
# - Health check passes
```

### 6. Test Health Endpoints
```bash
# Port-forward LLM Service
kubectl port-forward svc/llm-service 8000:8000 -n $NAMESPACE &

# Port-forward Executor Service
kubectl port-forward svc/executor-service 8001:8001 -n $NAMESPACE &

# Test health endpoints
curl http://localhost:8000/api/v1/health
curl http://localhost:8001/api/v1/health

# Expected: {"status": "healthy", ...}
```

### 7. Verify RBAC
```bash
# Check ServiceAccount
kubectl get serviceaccount executor-service -n $NAMESPACE

# Check Role
kubectl get role executor-service-role -n $NAMESPACE

# Check RoleBinding
kubectl get rolebinding executor-service-rolebinding -n $NAMESPACE

# Test permissions
kubectl auth can-i create jobs --as=system:serviceaccount:$NAMESPACE:executor-service -n $NAMESPACE
# Expected: yes
```

## Troubleshooting

### Pods Not Starting

```bash
# Describe pod to see events
kubectl describe pod <pod-name> -n $NAMESPACE

# Common issues:
# - ImagePullBackOff: Image not found in registry
# - CrashLoopBackOff: Application error, check logs
# - Pending: Resource constraints or scheduling issues
```

### Configuration Issues

```bash
# Check ConfigMap
kubectl get configmap llm-executor-config -o yaml -n $NAMESPACE

# Check Secrets (values are base64 encoded)
kubectl get secret llm-executor-secrets -o yaml -n $NAMESPACE

# Decode secret value
kubectl get secret llm-executor-secrets -o jsonpath='{.data.llm_api_key}' -n $NAMESPACE | base64 -d
```

### Service Not Accessible

```bash
# Check service endpoints
kubectl get endpoints -n $NAMESPACE

# Check if pods are ready
kubectl get pods -n $NAMESPACE

# Test service from within cluster
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n $NAMESPACE -- curl http://llm-service:8000/api/v1/health
```

### HPA Not Scaling

```bash
# Check HPA status
kubectl describe hpa executor-service-hpa -n $NAMESPACE

# Check metrics server
kubectl top pods -n $NAMESPACE

# Check HPA events
kubectl get events --field-selector involvedObject.name=executor-service-hpa -n $NAMESPACE
```

## Rollback

If deployment fails, rollback to previous version:

```bash
# Rollback deployment
kubectl rollout undo deployment/llm-service -n $NAMESPACE
kubectl rollout undo deployment/executor-service -n $NAMESPACE

# Check rollout status
kubectl rollout status deployment/llm-service -n $NAMESPACE
kubectl rollout status deployment/executor-service -n $NAMESPACE
```

## Cleanup

To remove all resources:

```bash
# Delete all resources
kubectl delete -f . -n $NAMESPACE

# Or delete by label
kubectl delete all -l platform=llm-executor -n $NAMESPACE

# Delete namespace (if created)
kubectl delete namespace $NAMESPACE
```

## Production Considerations

- [ ] Set up Ingress for external access
- [ ] Configure TLS certificates
- [ ] Set up monitoring (Prometheus, Grafana)
- [ ] Configure log aggregation
- [ ] Set up alerting
- [ ] Configure backup strategy
- [ ] Set up disaster recovery
- [ ] Configure network policies
- [ ] Set up pod disruption budgets
- [ ] Configure resource quotas
- [ ] Use external secret management (Azure Key Vault, etc.)
- [ ] Set up CI/CD pipeline
- [ ] Configure multi-region deployment

## Validation

Run the validation script before deployment:

```bash
./validate.sh
```

This checks:
- YAML syntax
- Resource limits
- Security context
- Health checks
- HPA configuration
- RBAC setup

## Support

For issues or questions:
1. Check logs: `kubectl logs -l app=<service> -n $NAMESPACE`
2. Check events: `kubectl get events -n $NAMESPACE`
3. Review README.md for detailed documentation
4. Check design.md for architecture details
