from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID

# ── Auth ─────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    full_name: str
    role: str
    language: str
    branch_id: Optional[str] = None

# ── User ─────────────────────────────────────────────────────
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    phone: Optional[str] = None
    role: str = "branch"
    language: str = "fr"

class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: str
    phone: Optional[str]
    role: str
    language: str
    is_active: bool
    created_at: datetime
    class Config: from_attributes = True

# ── Branch ───────────────────────────────────────────────────
class BranchCreate(BaseModel):
    code: str
    name: str
    city: str
    address: Optional[str] = None
    region_id: Optional[int] = None
    department_id: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    president_name: Optional[str] = None
    president_phone: Optional[str] = None
    president_email: Optional[EmailStr] = None
    member_count: int = 0
    founded_date: Optional[date] = None
    notes: Optional[str] = None

class BranchUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: Optional[str] = None
    president_name: Optional[str] = None
    president_phone: Optional[str] = None
    president_email: Optional[EmailStr] = None
    member_count: Optional[int] = None
    notes: Optional[str] = None

class BranchOut(BaseModel):
    id: UUID
    code: str
    name: str
    city: str
    address: Optional[str]
    region_id: Optional[int]
    department_id: Optional[int]
    latitude: Optional[float]
    longitude: Optional[float]
    status: str
    is_verified: bool
    president_name: Optional[str]
    president_phone: Optional[str]
    president_email: Optional[str]
    member_count: int
    founded_date: Optional[date]
    created_at: datetime
    class Config: from_attributes = True

# ── Report ───────────────────────────────────────────────────
class FormAnswerIn(BaseModel):
    question: str
    answer: Optional[str] = None

class ReportCreate(BaseModel):
    title: str
    description: Optional[str] = None
    report_type: str = "presence"
    latitude: float
    longitude: float
    location_accuracy: Optional[float] = None
    location_address: Optional[str] = None
    activity_count: int = 0
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    form_answers: List[FormAnswerIn] = []

class ReportOut(BaseModel):
    id: UUID
    branch_id: UUID
    title: str
    description: Optional[str]
    report_type: str
    latitude: float
    longitude: float
    location_address: Optional[str]
    activity_count: int
    status: str
    period_start: Optional[date]
    period_end: Optional[date]
    created_at: datetime
    class Config: from_attributes = True

# ── Map ──────────────────────────────────────────────────────
class MapBranchPoint(BaseModel):
    id: str
    name: str
    code: str
    city: str
    latitude: float
    longitude: float
    status: str
    is_verified: bool
    region_id: Optional[int]
    region_name: Optional[str]
    report_count: int

class MapStatsOut(BaseModel):
    total_branches: int
    active_branches: int
    pending_branches: int
    verified_branches: int
    covered_regions: int
    total_regions: int
    coverage_pct: float
    points: List[MapBranchPoint]

# ── Notification ─────────────────────────────────────────────
class NotificationOut(BaseModel):
    id: UUID
    title_fr: str
    title_en: Optional[str]
    body_fr: Optional[str]
    body_en: Optional[str]
    type: str
    is_read: bool
    created_at: datetime
    class Config: from_attributes = True

# ── Region ───────────────────────────────────────────────────
class RegionOut(BaseModel):
    id: int
    code: str
    name_fr: str
    name_en: str
    district: Optional[str]
    class Config: from_attributes = True
