"""Database models and session management for job history storage."""

from datetime import datetime
from typing import Optional
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Float, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

Base = declarative_base()


class JobHistory(Base):
    """
    Database model for job execution history.
    
    Stores metadata for all completed executions including timestamps,
    status, and resource usage.
    
    Requirements: 6.3
    """
    __tablename__ = "job_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(255), unique=True, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(String(50), nullable=False)
    code = Column(Text, nullable=False)
    stdout = Column(Text, nullable=True)
    stderr = Column(Text, nullable=True)
    exit_code = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=False)
    
    # Resource usage fields
    resource_usage = Column(Text, nullable=True)  # JSON string for flexibility
    classification = Column(String(50), nullable=True)  # lightweight or heavy
    
    # Additional metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<JobHistory(request_id='{self.request_id}', status='{self.status}', timestamp='{self.timestamp}')>"


class DatabaseManager:
    """
    Manages database connections and session lifecycle.
    """
    
    def __init__(self, database_url: str = "sqlite:///./job_history.db"):
        """
        Initialize database manager.
        
        Args:
            database_url: SQLAlchemy database URL
        """
        self.engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {}
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)
        
    def get_session(self) -> Session:
        """
        Get a new database session.
        
        Returns:
            SQLAlchemy session
        """
        return self.SessionLocal()
    
    def close(self):
        """Close database connections."""
        self.engine.dispose()
