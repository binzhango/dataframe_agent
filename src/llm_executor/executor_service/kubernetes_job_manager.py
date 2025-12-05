"""Kubernetes Job Manager for creating and managing heavy execution jobs.

This module implements the KubernetesJobManager class that creates and manages
Kubernetes Jobs for resource-intensive Python code execution.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from llm_executor.shared.models import JobCreationRequest, ResourceLimits
from llm_executor.shared.logging_util import get_logger

logger = get_logger(__name__)


class JobCreationResponse:
    """Response from job creation."""
    
    def __init__(self, job_id: str, status: str, created_at: str):
        self.job_id = job_id
        self.status = status
        self.created_at = created_at


class KubernetesJobManager:
    """
    Manages Kubernetes Job creation and lifecycle for heavy code execution.
    
    The KubernetesJobManager provides:
    - Job creation with unique identifiers
    - Resource limit configuration (CPU, memory)
    - Security context configuration
    - TTL-based automatic cleanup
    - PreStop lifecycle hooks for graceful shutdown
    
    Requirements:
    - 4.3: Create Kubernetes Jobs for heavy workloads
    - 8.1: Apply CPU and memory limits
    - 8.2: Enforce pod-level security policies
    - 8.3: Configure TTL for automatic cleanup
    - 8.4: Add PreStop hooks for graceful shutdown
    """
    
    def __init__(
        self,
        namespace: str = "default",
        image: str = "heavy-executor:latest",
        ttl_seconds: int = 3600,
    ):
        """
        Initialize the KubernetesJobManager.
        
        Args:
            namespace: Kubernetes namespace for job creation
            image: Container image for the heavy job runner
            ttl_seconds: TTL for automatic job cleanup after completion
        """
        self.namespace = namespace
        self.image = image
        self.ttl_seconds = ttl_seconds
        
        # Initialize Kubernetes client
        try:
            # Try to load in-cluster config first (for production)
            config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except Exception:
            # Fall back to kubeconfig (for development)
            try:
                config.load_kube_config()
                logger.info("Loaded kubeconfig configuration")
            except Exception as e:
                logger.error(
                    "Failed to load Kubernetes configuration",
                    extra={"error": str(e)},
                    exc_info=True
                )
                raise
        
        self.batch_v1 = client.BatchV1Api()
        
        logger.info(
            "KubernetesJobManager initialized",
            extra={
                "namespace": namespace,
                "image": image,
                "ttl_seconds": ttl_seconds,
            }
        )
    
    def create_job(
        self,
        request: JobCreationRequest,
    ) -> JobCreationResponse:
        """
        Create a Kubernetes Job for heavy code execution.
        
        This method:
        1. Generates a unique job ID based on request_id
        2. Creates a Job template with resource limits
        3. Configures security context
        4. Sets TTL for automatic cleanup
        5. Adds PreStop lifecycle hooks
        6. Submits the job to Kubernetes
        
        Args:
            request: Job creation request with code and resource limits
        
        Returns:
            JobCreationResponse with job_id, status, and created_at timestamp
        
        Raises:
            ApiException: If job creation fails
        """
        # Generate unique job ID
        job_id = self._generate_job_id(request.request_id)
        created_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        logger.info(
            "Creating Kubernetes Job",
            extra={
                "request_id": request.request_id,
                "job_id": job_id,
                "namespace": self.namespace,
            }
        )
        
        # Build job specification
        job = self._build_job_spec(
            job_id=job_id,
            request=request,
        )
        
        try:
            # Create the job
            self.batch_v1.create_namespaced_job(
                namespace=self.namespace,
                body=job,
            )
            
            logger.info(
                "Kubernetes Job created successfully",
                extra={
                    "request_id": request.request_id,
                    "job_id": job_id,
                    "namespace": self.namespace,
                }
            )
            
            return JobCreationResponse(
                job_id=job_id,
                status="created",
                created_at=created_at,
            )
        
        except ApiException as e:
            logger.error(
                "Failed to create Kubernetes Job",
                extra={
                    "request_id": request.request_id,
                    "job_id": job_id,
                    "error": str(e),
                    "status": e.status,
                },
                exc_info=True,
            )
            raise
    
    def _generate_job_id(self, request_id: str) -> str:
        """
        Generate a unique job ID based on request_id.
        
        Kubernetes job names must:
        - Be lowercase
        - Contain only alphanumeric characters and hyphens
        - Start with an alphanumeric character
        - Be no more than 63 characters
        
        Args:
            request_id: Request identifier
        
        Returns:
            Valid Kubernetes job name
        """
        # Extract alphanumeric portion of request_id
        clean_id = "".join(c for c in request_id if c.isalnum() or c == "-").lower()
        
        # Ensure it starts with alphanumeric
        if clean_id and not clean_id[0].isalnum():
            clean_id = "job-" + clean_id
        
        # Truncate if too long (leave room for prefix)
        if len(clean_id) > 50:
            clean_id = clean_id[:50]
        
        # Add prefix
        job_id = f"heavy-executor-{clean_id}"
        
        return job_id
    
    def _build_job_spec(
        self,
        job_id: str,
        request: JobCreationRequest,
    ) -> client.V1Job:
        """
        Build Kubernetes Job specification.
        
        Args:
            job_id: Unique job identifier
            request: Job creation request
        
        Returns:
            V1Job object ready for submission
        """
        resource_limits = request.resource_limits
        
        # Build container specification
        container = client.V1Container(
            name="executor",
            image=self.image,
            image_pull_policy="IfNotPresent",
            env=[
                client.V1EnvVar(name="CODE", value=request.code),
                client.V1EnvVar(name="REQUEST_ID", value=request.request_id),
                client.V1EnvVar(name="TIMEOUT", value=str(resource_limits.timeout_seconds)),
            ],
            resources=client.V1ResourceRequirements(
                limits={
                    "cpu": resource_limits.cpu_limit,
                    "memory": resource_limits.memory_limit,
                },
                requests={
                    "cpu": resource_limits.cpu_request,
                    "memory": resource_limits.memory_request,
                },
            ),
            security_context=client.V1SecurityContext(
                run_as_non_root=True,
                read_only_root_filesystem=True,
                allow_privilege_escalation=False,
                run_as_user=1000,
            ),
            lifecycle=client.V1Lifecycle(
                pre_stop=client.V1LifecycleHandler(
                    _exec=client.V1ExecAction(
                        command=["/bin/sh", "-c", "echo 'Graceful shutdown initiated'"]
                    )
                )
            ),
        )
        
        # Build pod template
        pod_template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    "app": "heavy-executor",
                    "request_id": request.request_id,
                    "component": "job-runner",
                }
            ),
            spec=client.V1PodSpec(
                restart_policy="Never",
                containers=[container],
            ),
        )
        
        # Build job specification
        job_spec = client.V1JobSpec(
            template=pod_template,
            backoff_limit=0,  # No automatic retries by Kubernetes
            ttl_seconds_after_finished=self.ttl_seconds,
        )
        
        # Build job object
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=job_id,
                labels={
                    "app": "heavy-executor",
                    "request_id": request.request_id,
                    "component": "job-runner",
                },
            ),
            spec=job_spec,
        )
        
        return job
    
    def get_job_status(self, job_id: str) -> Optional[dict]:
        """
        Get the status of a Kubernetes Job.
        
        Args:
            job_id: Job identifier
        
        Returns:
            Dictionary with job status information, or None if not found
        """
        try:
            job = self.batch_v1.read_namespaced_job(
                name=job_id,
                namespace=self.namespace,
            )
            
            status = {
                "job_id": job_id,
                "active": job.status.active or 0,
                "succeeded": job.status.succeeded or 0,
                "failed": job.status.failed or 0,
                "start_time": job.status.start_time.isoformat() if job.status.start_time else None,
                "completion_time": job.status.completion_time.isoformat() if job.status.completion_time else None,
            }
            
            return status
        
        except ApiException as e:
            if e.status == 404:
                logger.warning(
                    "Job not found",
                    extra={"job_id": job_id}
                )
                return None
            else:
                logger.error(
                    "Failed to get job status",
                    extra={
                        "job_id": job_id,
                        "error": str(e),
                    },
                    exc_info=True,
                )
                raise
    
    def delete_job(self, job_id: str) -> bool:
        """
        Delete a Kubernetes Job.
        
        Args:
            job_id: Job identifier
        
        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            self.batch_v1.delete_namespaced_job(
                name=job_id,
                namespace=self.namespace,
                propagation_policy="Background",
            )
            
            logger.info(
                "Job deleted successfully",
                extra={"job_id": job_id}
            )
            
            return True
        
        except ApiException as e:
            logger.error(
                "Failed to delete job",
                extra={
                    "job_id": job_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            return False
