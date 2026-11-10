from typing import Literal, Optional
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class UserBase(BaseModel):
    username: str
    email: str
    full_name: str


class UserOut(UserBase):
    id: int
    role: str
    department: Optional[str] = None


class DepartmentCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ActivityCreate(BaseModel):
    name: str
    description: Optional[str] = None
    department_id: int


class RiskCreate(BaseModel):
    code: str
    name: str
    description: str
    category: str
    department_id: int
    activity_id: Optional[int] = None
    threat: Optional[str] = None
    vulnerability: Optional[str] = None
    consequence: Optional[str] = None
    probability: int = Field(default=3, ge=1, le=5)
    impact: int = Field(default=3, ge=1, le=5)
    owner_id: Optional[int] = None


class RiskTreatmentCreate(BaseModel):
    strategy: Literal['Avoid', 'Reduce', 'Transfer', 'Accept']
    treatment_plan: str = Field(min_length=10, max_length=4000)
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    expected_result: Optional[str] = Field(default=None, max_length=2000)
    resources_required: Optional[str] = Field(default=None, max_length=2000)


class TreatmentDecision(BaseModel):
    decision: Literal['approve', 'reject']
    comment: str = Field(min_length=3, max_length=2000)


class TreatmentStatusUpdate(BaseModel):
    status: Literal['In progress', 'Completed', 'Cancelled']
    residual_probability: Optional[int] = Field(default=None, ge=1, le=5)
    residual_impact: Optional[int] = Field(default=None, ge=1, le=5)


class RiskAssessmentCreate(BaseModel):
    probability: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    comments: Optional[str] = Field(default=None, max_length=2000)


class TreatmentActionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=140)
    owner_id: Optional[int] = None
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    expected_result: Optional[str] = Field(default=None, max_length=2000)
    resources_required: Optional[str] = Field(default=None, max_length=2000)


class TreatmentActionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=140)
    owner_id: Optional[int] = None
    start_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    status: Optional[Literal['Planned', 'In progress', 'Blocked', 'Completed']] = None
    result: Optional[str] = Field(default=None, max_length=2000)
    expected_result: Optional[str] = Field(default=None, max_length=2000)
    resources_required: Optional[str] = Field(default=None, max_length=2000)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=72)
    role: Literal['Administrator', 'SMCA Manager', 'Risk Manager', 'Department Manager', 'Auditor']
    department_id: Optional[int] = None

    @field_validator('password')
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode('utf-8')) > 72:
            raise ValueError('Password must be at most 72 UTF-8 bytes')
        return value


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    email: Optional[str] = Field(default=None, min_length=5, max_length=120)
    role: Optional[Literal['Administrator', 'SMCA Manager', 'Risk Manager', 'Department Manager', 'Auditor']] = None
    department_id: Optional[int] = None
    is_active: Optional[bool] = None
