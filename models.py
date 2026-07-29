"""
models.py – SQLAlchemy ORM models
Tables: personnel, assessments, competency_scores, summary_scores, audit_log
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime,
    Boolean, ForeignKey, Text, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class Personnel(Base):
    __tablename__ = "personnel"

    id                      = Column(Integer, primary_key=True)
    staff_id                = Column(String(30), unique=True, nullable=False, index=True)
    name                    = Column(String(200), nullable=False)
    email                   = Column(String(120))
    gender                  = Column(String(10))
    age                     = Column(Integer)
    birth_year              = Column(Integer)
    nationality             = Column(String(60))
    employment_category     = Column(String(60))

    # Employment
    department              = Column(String(60), index=True)
    section_name            = Column(String(100))
    unit_name               = Column(String(100))
    sub_unit                = Column(String(100))
    staff_position          = Column(String(60), index=True)
    sg                      = Column(String(20), index=True)    # P1-P8, CDH, UPTREX
    joining_date            = Column(Date)
    contract_expire_date    = Column(Date)
    years_in_pet            = Column(Float)
    years_re_experience     = Column(Float)
    sg_years                = Column(Float)
    sg_start_date           = Column(Date)
    age_promoted            = Column(Float)
    current_assignment      = Column(String(200))
    assignment_date         = Column(Date)
    assignment_length       = Column(Float)

    # Assessment meta
    chat_status             = Column(String(20))   # Yes / No / No Need
    chat_date               = Column(Date)
    assessment_level        = Column(String(60))
    last_assessment_date    = Column(Date)
    sub_disciplines         = Column(String(200))
    potential               = Column(String(200))
    strength                = Column(String(500))
    recommendation          = Column(String(500))
    resource_sme            = Column(String(200))
    interest                = Column(String(200))
    preference              = Column(String(200))
    comment                 = Column(Text)
    assessor1               = Column(String(100))
    assessor2               = Column(String(100))
    supervisor              = Column(String(100))
    remarks                 = Column(Text)

    is_active               = Column(Boolean, default=True)
    is_deleted              = Column(Boolean, default=False)
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assessments     = relationship("Assessment",     back_populates="personnel", cascade="all, delete-orphan")
    summary_scores  = relationship("SummaryScore",   back_populates="personnel", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Personnel {self.staff_id} – {self.name}>"


class Assessment(Base):
    __tablename__ = "assessments"

    id                  = Column(Integer, primary_key=True)
    personnel_id        = Column(Integer, ForeignKey("personnel.id"), nullable=False, index=True)
    assessment_date     = Column(Date, nullable=False, index=True)
    assessment_level    = Column(String(60))
    assessor1           = Column(String(100))
    assessor2           = Column(String(100))
    supervisor          = Column(String(100))
    remarks             = Column(Text)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    personnel   = relationship("Personnel",        back_populates="assessments")
    scores      = relationship("CompetencyScore",  back_populates="assessment", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Assessment id={self.id} personnel_id={self.personnel_id} date={self.assessment_date}>"


class CompetencyScore(Base):
    """One row per competency per assessment (B1-E2 = 24 rows per assessment)."""
    __tablename__ = "competency_scores"

    id                      = Column(Integer, primary_key=True)
    assessment_id           = Column(Integer, ForeignKey("assessments.id"), nullable=False, index=True)
    personnel_id            = Column(Integer, ForeignKey("personnel.id"),   nullable=False, index=True)
    competency_code         = Column(String(10), nullable=False, index=True)  # B1, K3, P2, E1 …
    competency_type         = Column(String(1),  nullable=False, index=True)  # B, K, P, E
    actual_score            = Column(Float)
    requirement_score       = Column(Float)
    gap_score               = Column(Float)     # actual – requirement
    achievement_pct         = Column(Float)     # (actual / requirement) * 100
    created_at              = Column(DateTime, default=datetime.utcnow)

    assessment  = relationship("Assessment", back_populates="scores")

    def __repr__(self):
        return f"<Score {self.competency_code} actual={self.actual_score}>"


class SummaryScore(Base):
    """Pre-computed summary scores imported from Excel summary columns."""
    __tablename__ = "summary_scores"

    id              = Column(Integer, primary_key=True)
    personnel_id    = Column(Integer, ForeignKey("personnel.id"), nullable=False, index=True)
    assessment_id   = Column(Integer, ForeignKey("assessments.id"), nullable=True)

    staff_base      = Column(Float)
    staff_keys      = Column(Float)
    staff_pacing    = Column(Float)
    staff_emerging  = Column(Float)
    staff_cti       = Column(Float)

    principal_base      = Column(Float)
    principal_keys      = Column(Float)
    principal_pacing    = Column(Float)
    principal_emerging  = Column(Float)
    principal_cti       = Column(Float)

    custodian_base      = Column(Float)
    custodian_keys      = Column(Float)
    custodian_pacing    = Column(Float)
    custodian_emerging  = Column(Float)
    custodian_cti       = Column(Float)

    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    personnel   = relationship("Personnel", back_populates="summary_scores")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id          = Column(Integer, primary_key=True)
    entity_type = Column(String(50))
    entity_id   = Column(Integer)
    action      = Column(String(20))    # CREATE UPDATE DELETE
    changed_by  = Column(String(100))
    old_values  = Column(Text)
    new_values  = Column(Text)
    timestamp   = Column(DateTime, default=datetime.utcnow, index=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_engine(db_url: str):
    return create_engine(db_url, echo=False)


def init_db(db_url: str):
    engine = get_engine(db_url)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()
