"""Repository pattern for job history storage and retrieval."""

import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc

from llm_executor.shared.database import JobHistory
from llm_executor.shared.models import ExecutionResult, ExecutionStatus


class JobHistoryRepository:
    """
    Repository for storing and querying job execution history.
    
    Implements the repository pattern to abstract database operations
    for job history management.
    
    Requirements: 6.3
    """
    
    def __init__(self, session: Session):
        """
        Initialize repository with database session.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
    
    def save_execution(
        self,
        execution_result: ExecutionResult,
        code: str,
        classification: Optional[str] = None,
        resource_usage: Optional[Dict[str, Any]] = None
    ) -> JobHistory:
        """
        Save execution result to job history.
        
        Args:
            execution_result: Execution result to save
            code: The Python code that was executed
            classification: Code classification (lightweight/heavy)
            resource_usage: Resource usage metrics
            
        Returns:
            Saved JobHistory record
            
        Requirements: 6.3
        """
        # Check if record already exists
        existing = self.session.query(JobHistory).filter_by(
            request_id=execution_result.request_id
        ).first()
        
        if existing:
            # Update existing record
            existing.status = execution_result.status.value
            existing.stdout = execution_result.stdout
            existing.stderr = execution_result.stderr
            existing.exit_code = execution_result.exit_code
            existing.duration_ms = execution_result.duration_ms
            existing.timestamp = datetime.now(timezone.utc)
            existing.updated_at = datetime.now(timezone.utc)
            
            if classification:
                existing.classification = classification
            
            if resource_usage:
                existing.resource_usage = json.dumps(resource_usage)
            
            self.session.commit()
            self.session.refresh(existing)
            return existing
        else:
            # Create new record
            job_history = JobHistory(
                request_id=execution_result.request_id,
                timestamp=datetime.now(timezone.utc),
                status=execution_result.status.value,
                code=code,
                stdout=execution_result.stdout,
                stderr=execution_result.stderr,
                exit_code=execution_result.exit_code,
                duration_ms=execution_result.duration_ms,
                classification=classification,
                resource_usage=json.dumps(resource_usage) if resource_usage else None
            )
            
            self.session.add(job_history)
            self.session.commit()
            self.session.refresh(job_history)
            return job_history
    
    def get_by_request_id(self, request_id: str) -> Optional[JobHistory]:
        """
        Retrieve job history by request ID.
        
        Args:
            request_id: Request identifier
            
        Returns:
            JobHistory record or None if not found
        """
        return self.session.query(JobHistory).filter_by(request_id=request_id).first()
    
    def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "timestamp",
        order_direction: str = "desc"
    ) -> List[JobHistory]:
        """
        Retrieve all job history records with pagination.
        
        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            order_by: Field to order by (timestamp, status, duration_ms)
            order_direction: Order direction (asc or desc)
            
        Returns:
            List of JobHistory records
        """
        query = self.session.query(JobHistory)
        
        # Apply ordering
        order_field = getattr(JobHistory, order_by, JobHistory.timestamp)
        if order_direction.lower() == "desc":
            query = query.order_by(desc(order_field))
        else:
            query = query.order_by(asc(order_field))
        
        # Apply pagination
        query = query.limit(limit).offset(offset)
        
        return query.all()
    
    def get_by_status(
        self,
        status: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[JobHistory]:
        """
        Retrieve job history records by status.
        
        Args:
            status: Execution status to filter by
            limit: Maximum number of records to return
            offset: Number of records to skip
            
        Returns:
            List of JobHistory records with the specified status
        """
        return (
            self.session.query(JobHistory)
            .filter_by(status=status)
            .order_by(desc(JobHistory.timestamp))
            .limit(limit)
            .offset(offset)
            .all()
        )
    
    def get_recent(self, limit: int = 10) -> List[JobHistory]:
        """
        Retrieve most recent job history records.
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of most recent JobHistory records
        """
        return (
            self.session.query(JobHistory)
            .order_by(desc(JobHistory.timestamp))
            .limit(limit)
            .all()
        )
    
    def count_by_status(self, status: str) -> int:
        """
        Count job history records by status.
        
        Args:
            status: Execution status to count
            
        Returns:
            Number of records with the specified status
        """
        return self.session.query(JobHistory).filter_by(status=status).count()
    
    def get_total_count(self) -> int:
        """
        Get total count of job history records.
        
        Returns:
            Total number of records
        """
        return self.session.query(JobHistory).count()
    
    def delete_by_request_id(self, request_id: str) -> bool:
        """
        Delete job history record by request ID.
        
        Args:
            request_id: Request identifier
            
        Returns:
            True if record was deleted, False if not found
        """
        record = self.get_by_request_id(request_id)
        if record:
            self.session.delete(record)
            self.session.commit()
            return True
        return False
    
    def to_dict(self, job_history: JobHistory) -> Dict[str, Any]:
        """
        Convert JobHistory record to dictionary.
        
        Args:
            job_history: JobHistory record
            
        Returns:
            Dictionary representation of the record
        """
        return {
            "id": job_history.id,
            "request_id": job_history.request_id,
            "timestamp": job_history.timestamp.isoformat() if job_history.timestamp else None,
            "status": job_history.status,
            "code": job_history.code,
            "stdout": job_history.stdout,
            "stderr": job_history.stderr,
            "exit_code": job_history.exit_code,
            "duration_ms": job_history.duration_ms,
            "resource_usage": json.loads(job_history.resource_usage) if job_history.resource_usage else None,
            "classification": job_history.classification,
            "created_at": job_history.created_at.isoformat() if job_history.created_at else None,
            "updated_at": job_history.updated_at.isoformat() if job_history.updated_at else None
        }
