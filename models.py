import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Float, Text, Date,
    DateTime, ForeignKey, ARRAY, JSON
)
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship
from database import Base

class Region(Base):
    __tablename__ = "regions"
    id         = Column(Integer, primary_key=True)
    code       = Column(String(10), unique=True, nullable=False)
    name_fr    = Column(String(100), nullable=False)
    name_en    = Column(String(100), nullable=False)
    district   = Column(String(100))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    branches   = relationship("Branch", back_populates="region")

class Department(Base):
    __tablename__ = "departments"
    id         = Column(Integer, primary_key=True)
    code       = Column(String(10), unique=True, nullable=False)
    name_fr    = Column(String(100), nullable=False)
    name_en    = Column(String(100), nullable=False)
    region_id  = Column(Integer, ForeignKey("regions.id"))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class User(Base):
    __tablename__ = "users"
    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email         = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name     = Column(String(200), nullable=False)
    phone         = Column(String(20))
    role          = Column(String(20), default="branch")
    language      = Column(String(5), default="fr")
    is_active     = Column(Boolean, default=True)
    last_login    = Column(DateTime(timezone=True))
    created_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at    = Column(DateTime(timezone=True), default=datetime.utcnow)
    branch_links  = relationship("BranchUser", back_populates="user")

class Branch(Base):
    __tablename__ = "branches"
    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code            = Column(String(20), unique=True, nullable=False)
    name            = Column(String(200), nullable=False)
    city            = Column(String(100), nullable=False)
    address         = Column(Text)
    region_id       = Column(Integer, ForeignKey("regions.id"))
    department_id   = Column(Integer, ForeignKey("departments.id"))
    latitude        = Column(Float)
    longitude       = Column(Float)
    status          = Column(String(20), default="pending")
    is_verified     = Column(Boolean, default=False)
    verified_at     = Column(DateTime(timezone=True))
    verified_by     = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    president_name  = Column(String(200))
    president_phone = Column(String(20))
    president_email = Column(String(255))
    member_count    = Column(Integer, default=0)
    founded_date    = Column(Date)
    notes           = Column(Text)
    created_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at      = Column(DateTime(timezone=True), default=datetime.utcnow)
    region          = relationship("Region", back_populates="branches")
    reports         = relationship("PresenceReport", back_populates="branch")
    user_links      = relationship("BranchUser", back_populates="branch")

class BranchUser(Base):
    __tablename__ = "branch_users"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    branch_id  = Column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"))
    role       = Column(String(20), default="secretary")
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    user       = relationship("User", back_populates="branch_links")
    branch     = relationship("Branch", back_populates="user_links")

class PresenceReport(Base):
    __tablename__ = "presence_reports"
    id                = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id         = Column(UUID(as_uuid=True), ForeignKey("branches.id", ondelete="CASCADE"))
    submitted_by      = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    latitude          = Column(Float, nullable=False)
    longitude         = Column(Float, nullable=False)
    location_accuracy = Column(Float)
    location_address  = Column(Text)
    report_type       = Column(String(30), default="presence")
    title             = Column(String(255), nullable=False)
    description       = Column(Text)
    activity_count    = Column(Integer, default=0)
    status            = Column(String(20), default="submitted")
    reviewed_by       = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at       = Column(DateTime(timezone=True))
    review_notes      = Column(Text)
    period_start      = Column(Date)
    period_end        = Column(Date)
    photos_urls       = Column(ARRAY(Text))
    documents_urls    = Column(ARRAY(Text))
    created_at        = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at        = Column(DateTime(timezone=True), default=datetime.utcnow)
    branch            = relationship("Branch", back_populates="reports")
    form_answers      = relationship("ReportFormAnswer", back_populates="report")

class ReportFormAnswer(Base):
    __tablename__ = "report_form_answers"
    id         = Column(Integer, primary_key=True)
    report_id  = Column(UUID(as_uuid=True), ForeignKey("presence_reports.id", ondelete="CASCADE"))
    question   = Column(String(500), nullable=False)
    answer     = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    report     = relationship("PresenceReport", back_populates="form_answers")

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    id         = Column(Integer, primary_key=True)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    branch_id  = Column(UUID(as_uuid=True), ForeignKey("branches.id"))
    action     = Column(String(100), nullable=False)
    details    = Column(JSONB)
    ip_address = Column(INET)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    title_fr   = Column(String(255), nullable=False)
    title_en   = Column(String(255))
    body_fr    = Column(Text)
    body_en    = Column(Text)
    type       = Column(String(30), default="info")
    is_read    = Column(Boolean, default=False)
    link       = Column(String(500))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
