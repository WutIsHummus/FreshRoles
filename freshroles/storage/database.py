"""SQLite database storage layer."""

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from freshroles.models.job import JobPosting, ScoredJobPosting


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


class CompanyRecord(Base):
    """Company configuration stored in database."""
    
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    config_json = Column(Text, nullable=False)
    last_sync_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    jobs = relationship("JobRecord", back_populates="company")


class JobRecord(Base):
    """Job posting record."""
    
    __tablename__ = "jobs"
    
    id = Column(String(32), primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    source_job_id = Column(String(255), nullable=False)
    source_system = Column(String(50), nullable=False)
    
    title = Column(String(500), nullable=False)
    location = Column(String(255))
    remote_type = Column(String(50))
    employment_type = Column(String(50))
    department = Column(String(255))
    team = Column(String(255))
    
    apply_url = Column(Text)
    source_url = Column(Text)
    
    posted_at = Column(DateTime)
    updated_at = Column(DateTime)
    
    description_text = Column(Text)
    seniority = Column(String(100))
    
    score = Column(Float, default=0.0)
    vector_score = Column(Float, default=0.0)
    keyword_score = Column(Float, default=0.0)
    recency_score = Column(Float, default=0.0)
    
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    notified_at = Column(DateTime)
    
    company = relationship("CompanyRecord", back_populates="jobs")
    versions = relationship("JobVersionRecord", back_populates="job")


class JobVersionRecord(Base):
    """Historical versions of job postings."""
    
    __tablename__ = "job_versions"
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String(32), ForeignKey("jobs.id"))
    raw_json = Column(Text)
    fetched_at = Column(DateTime, default=datetime.utcnow)
    
    job = relationship("JobRecord", back_populates="versions")


class RunRecord(Base):
    """Scan run history."""
    
    __tablename__ = "runs"
    
    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    jobs_found = Column(Integer, default=0)
    jobs_new = Column(Integer, default=0)
    status = Column(String(50))
    error_message = Column(Text)


class NotificationRecord(Base):
    """Notification history."""
    
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True)
    job_id = Column(String(32), ForeignKey("jobs.id"))
    sent_at = Column(DateTime, default=datetime.utcnow)
    mode = Column(String(50))
    target = Column(String(255))
    success = Column(Integer, default=1)


class Database:
    """Database manager for FreshRoles."""
    
    def __init__(self, db_path: str | Path = "freshroles.db"):
        self.db_path = Path(db_path)
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(self.engine)
    
    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()
    
    def save_job(
        self,
        job: JobPosting,
        company_id: int,
        scores: dict[str, float] | None = None,
    ) -> tuple[JobRecord, bool]:
        """
        Save a job posting to the database.
        
        Returns:
            Tuple of (job_record, is_new).
        """
        import json
        
        with self.get_session() as session:
            existing = session.get(JobRecord, job.id)
            is_new = existing is None
            
            if is_new:
                record = JobRecord(
                    id=job.id,
                    company_id=company_id,
                    source_job_id=job.source_job_id,
                    source_system=job.source_system.value,
                    title=job.title,
                    location=job.location,
                    remote_type=job.remote_type.value,
                    employment_type=job.employment_type.value,
                    department=job.department,
                    team=job.team,
                    apply_url=str(job.apply_url),
                    source_url=str(job.source_url),
                    posted_at=job.posted_at,
                    updated_at=job.updated_at,
                    description_text=job.description_text,
                    seniority=job.seniority,
                    score=scores.get("final", 0.0) if scores else 0.0,
                    vector_score=scores.get("vector", 0.0) if scores else 0.0,
                    keyword_score=scores.get("keyword", 0.0) if scores else 0.0,
                    recency_score=scores.get("recency", 0.0) if scores else 0.0,
                )
                session.add(record)
            else:
                record = existing
                record.updated_at = datetime.utcnow()
                if scores:
                    record.score = scores.get("final", record.score)
            
            version = JobVersionRecord(
                job_id=job.id,
                raw_json=json.dumps(job.raw),
            )
            session.add(version)
            
            session.commit()
            session.refresh(record)
            return record, is_new
    
    def get_unseen_jobs(
        self,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[JobRecord]:
        """Get jobs that haven't been notified yet."""
        from sqlalchemy.orm import joinedload
        
        with self.get_session() as session:
            query = session.query(JobRecord).options(
                joinedload(JobRecord.company)
            ).filter(
                JobRecord.notified_at.is_(None)
            )
            
            if since:
                query = query.filter(JobRecord.first_seen_at >= since)
            
            results = query.order_by(JobRecord.score.desc()).limit(limit).all()
            # Expunge from session so we can use them after closing
            for r in results:
                session.expunge(r)
            return results
    
    def mark_notified(self, job_ids: list[str], mode: str, target: str):
        """Mark jobs as notified."""
        with self.get_session() as session:
            now = datetime.utcnow()
            
            for job_id in job_ids:
                job = session.get(JobRecord, job_id)
                if job:
                    job.notified_at = now
                    
                    notification = NotificationRecord(
                        job_id=job_id,
                        mode=mode,
                        target=target,
                    )
                    session.add(notification)
            
            session.commit()
    
    def job_exists(self, job_id: str) -> bool:
        """Check if a job already exists in the database."""
        with self.get_session() as session:
            return session.get(JobRecord, job_id) is not None
    
    def get_company_by_name(self, name: str) -> CompanyRecord | None:
        """Get company by name."""
        with self.get_session() as session:
            return session.query(CompanyRecord).filter(
                CompanyRecord.name == name
            ).first()
    
    def save_company(self, name: str, config_json: str) -> CompanyRecord:
        """Save or update company config."""
        with self.get_session() as session:
            existing = session.query(CompanyRecord).filter(
                CompanyRecord.name == name
            ).first()
            
            if existing:
                existing.config_json = config_json
                record = existing
            else:
                record = CompanyRecord(name=name, config_json=config_json)
                session.add(record)
            
            session.commit()
            session.refresh(record)
            return record
    
    def start_run(self) -> RunRecord:
        """Start a new scan run."""
        with self.get_session() as session:
            run = RunRecord(status="running")
            session.add(run)
            session.commit()
            session.refresh(run)
            return run
    
    def complete_run(
        self,
        run_id: int,
        jobs_found: int,
        jobs_new: int,
        status: str = "completed",
        error: str | None = None,
    ):
        """Complete a scan run."""
        with self.get_session() as session:
            run = session.get(RunRecord, run_id)
            if run:
                run.completed_at = datetime.utcnow()
                run.jobs_found = jobs_found
                run.jobs_new = jobs_new
                run.status = status
                run.error_message = error
                session.commit()
