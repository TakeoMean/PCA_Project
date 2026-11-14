from typing import Literal, Optional
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


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
    source: Optional[str] = Field(default=None, max_length=160)
    causes: Optional[str] = Field(default=None, max_length=4000)
    existing_measures: Optional[str] = Field(default=None, max_length=4000)
    review_date: Optional[datetime] = None
    probability: int = Field(default=3, ge=1, le=5)
    impact: int = Field(default=3, ge=1, le=5)
    owner_id: Optional[int] = None


class RiskUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=2, max_length=30)
    name: Optional[str] = Field(default=None, min_length=3, max_length=160)
    description: Optional[str] = Field(default=None, min_length=3, max_length=6000)
    category: Optional[str] = Field(default=None, min_length=2, max_length=80)
    department_id: Optional[int] = None
    activity_id: Optional[int] = None
    threat: Optional[str] = Field(default=None, max_length=160)
    vulnerability: Optional[str] = Field(default=None, max_length=1000)
    consequence: Optional[str] = Field(default=None, max_length=4000)
    source: Optional[str] = Field(default=None, max_length=160)
    causes: Optional[str] = Field(default=None, max_length=4000)
    existing_measures: Optional[str] = Field(default=None, max_length=4000)
    review_date: Optional[datetime] = None
    owner_id: Optional[int] = None
    status: Optional[Literal['Draft', 'Validated', 'Under treatment', 'Accepted', 'Closed', 'Archived']] = None
    acceptance_justification: Optional[str] = Field(default=None, max_length=4000)


class SmcaScopeUpdate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=10, max_length=6000)
    objectives: Optional[str] = Field(default=None, max_length=6000)
    exclusions: Optional[str] = Field(default=None, max_length=4000)
    stakeholders: Optional[str] = Field(default=None, max_length=4000)
    status: Literal['Draft', 'Approved', 'Under review'] = 'Draft'
    review_date: Optional[datetime] = None
    acceptance_threshold: int = Field(default=9, ge=1, le=25)


class BusinessImpactCreate(BaseModel):
    financial_impact: int = Field(ge=1, le=5)
    operational_impact: int = Field(ge=1, le=5)
    legal_impact: int = Field(ge=1, le=5)
    reputational_impact: int = Field(ge=1, le=5)
    rto_hours: int = Field(ge=0, le=8760)
    rpo_hours: int = Field(ge=0, le=8760)
    mtpd_hours: int = Field(ge=1, le=17520)
    dependencies: Optional[str] = Field(default=None, max_length=4000)
    recovery_requirements: Optional[str] = Field(default=None, max_length=4000)
    comments: Optional[str] = Field(default=None, max_length=4000)


class RiskControlCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=3, max_length=4000)
    control_type: Literal['Preventive', 'Detective', 'Corrective']
    owner_id: Optional[int] = None
    effectiveness: int = Field(default=3, ge=1, le=5)
    status: Literal['Planned', 'Implemented', 'Needs improvement', 'Inactive'] = 'Implemented'
    evidence_reference: Optional[str] = Field(default=None, max_length=2000)
    last_tested_at: Optional[datetime] = None
    next_test_date: Optional[datetime] = None


class RiskControlUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=160)
    description: Optional[str] = Field(default=None, min_length=3, max_length=4000)
    control_type: Optional[Literal['Preventive', 'Detective', 'Corrective']] = None
    owner_id: Optional[int] = None
    effectiveness: Optional[int] = Field(default=None, ge=1, le=5)
    status: Optional[Literal['Planned', 'Implemented', 'Needs improvement', 'Inactive']] = None
    evidence_reference: Optional[str] = Field(default=None, max_length=2000)
    last_tested_at: Optional[datetime] = None
    next_test_date: Optional[datetime] = None


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


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=10, max_length=72)

    @field_validator('new_password')
    @classmethod
    def new_password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode('utf-8')) > 72:
            raise ValueError('Password must be at most 72 UTF-8 bytes')
        return value


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=10, max_length=72)

    @field_validator('new_password')
    @classmethod
    def reset_password_fits_bcrypt(cls, value: str) -> str:
        if len(value.encode('utf-8')) > 72:
            raise ValueError('Password must be at most 72 UTF-8 bytes')
        return value


class ActivityDependencyCreate(BaseModel):
    source_activity_id: int
    target_activity_id: int
    dependency_type: Literal['Technology', 'Supplier', 'People', 'Site', 'Data', 'Process', 'Utility', 'Other']
    criticality: int = Field(default=3, ge=1, le=5)
    description: Optional[str] = Field(default=None, max_length=3000)
    recovery_order: Optional[int] = Field(default=None, ge=1, le=999)


class ThreatScenarioCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=3, max_length=4000)
    common_causes: Optional[str] = Field(default=None, max_length=4000)
    common_vulnerabilities: Optional[str] = Field(default=None, max_length=4000)
    default_probability: int = Field(default=3, ge=1, le=5)


class IncidentCreate(BaseModel):
    code: str = Field(min_length=2, max_length=40)
    title: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=3, max_length=6000)
    severity: Literal['Minor', 'Moderate', 'Major', 'Critical'] = 'Moderate'
    status: Literal['Open', 'Investigating', 'Resolved', 'Closed'] = 'Open'
    occurred_at: datetime
    department_id: int
    risk_id: Optional[int] = None
    impact: Optional[str] = Field(default=None, max_length=4000)
    lessons_learned: Optional[str] = Field(default=None, max_length=6000)


class IncidentUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=180)
    description: Optional[str] = Field(default=None, min_length=3, max_length=6000)
    severity: Optional[Literal['Minor', 'Moderate', 'Major', 'Critical']] = None
    status: Optional[Literal['Open', 'Investigating', 'Resolved', 'Closed']] = None
    occurred_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    risk_id: Optional[int] = None
    impact: Optional[str] = Field(default=None, max_length=4000)
    lessons_learned: Optional[str] = Field(default=None, max_length=6000)


class RiskIndicatorCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    unit: str = Field(min_length=1, max_length=40)
    direction: Literal['Above is bad', 'Below is bad'] = 'Above is bad'
    warning_threshold: float
    critical_threshold: float
    current_value: float
    frequency: Literal['Daily', 'Weekly', 'Monthly', 'Quarterly'] = 'Monthly'
    owner_id: Optional[int] = None


class RiskIndicatorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=3, max_length=160)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=40)
    direction: Optional[Literal['Above is bad', 'Below is bad']] = None
    warning_threshold: Optional[float] = None
    critical_threshold: Optional[float] = None
    current_value: Optional[float] = None
    frequency: Optional[Literal['Daily', 'Weekly', 'Monthly', 'Quarterly']] = None
    owner_id: Optional[int] = None
