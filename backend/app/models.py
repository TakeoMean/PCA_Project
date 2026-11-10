from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role(Base):
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

    users = relationship('User', back_populates='role')


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=False)
    department_id = Column(Integer, ForeignKey('departments.id'), nullable=True)

    role = relationship('Role', back_populates='users')
    department = relationship('Department', back_populates='users')
    audit_logs = relationship('AuditLog', back_populates='user')
    treatment_actions = relationship('TreatmentAction', back_populates='owner')


class Department(Base):
    __tablename__ = 'departments'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False)
    description = Column(Text, nullable=True)

    activities = relationship('Activity', back_populates='department')
    users = relationship('User', back_populates='department')
    risks = relationship('Risk', back_populates='department')


class Activity(Base):
    __tablename__ = 'activities'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text)
    department_id = Column(Integer, ForeignKey('departments.id'), nullable=False)

    department = relationship('Department', back_populates='activities')
    resources = relationship('Resource', back_populates='activity')
    risks = relationship('Risk', back_populates='activity')


class Resource(Base):
    __tablename__ = 'resources'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    category = Column(String(80), nullable=False)
    description = Column(Text)
    activity_id = Column(Integer, ForeignKey('activities.id'), nullable=False)

    activity = relationship('Activity', back_populates='resources')


class Risk(Base):
    __tablename__ = 'risks'

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(30), unique=True, nullable=False)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(80), nullable=False)
    department_id = Column(Integer, ForeignKey('departments.id'), nullable=False)
    activity_id = Column(Integer, ForeignKey('activities.id'), nullable=True)
    threat = Column(String(120), nullable=True)
    vulnerability = Column(String(120), nullable=True)
    consequence = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    department = relationship('Department', back_populates='risks')
    activity = relationship('Activity', back_populates='risks')
    owner = relationship('User', foreign_keys=[owner_id])
    assessments = relationship('RiskAssessment', back_populates='risk', cascade='all, delete-orphan')
    treatments = relationship('RiskTreatment', back_populates='risk', cascade='all, delete-orphan')
    audit_logs = relationship('AuditLog', back_populates='risk')


class RiskAssessment(Base):
    __tablename__ = 'risk_assessments'

    id = Column(Integer, primary_key=True, index=True)
    risk_id = Column(Integer, ForeignKey('risks.id'), nullable=False)
    probability = Column(Integer, nullable=False)
    impact = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)
    level = Column(String(30), nullable=False)
    assessment_type = Column(String(30), nullable=False, default='Inherent')
    assessment_date = Column(DateTime, default=_utcnow)
    comments = Column(Text, nullable=True)

    risk = relationship('Risk', back_populates='assessments')


class RiskTreatment(Base):
    __tablename__ = 'risk_treatments'

    id = Column(Integer, primary_key=True, index=True)
    risk_id = Column(Integer, ForeignKey('risks.id'), nullable=False)
    strategy = Column(String(80), nullable=False)
    treatment_plan = Column(Text, nullable=False)
    expected_result = Column(Text, nullable=True)
    resources_required = Column(Text, nullable=True)
    residual_risk = Column(String(30), nullable=False, default='Moderate')
    status = Column(String(30), nullable=False, default='Planned')
    start_date = Column(DateTime, default=_utcnow)
    due_date = Column(DateTime, nullable=True)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    reviewed_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    review_comment = Column(Text, nullable=True)
    residual_probability = Column(Integer, nullable=True)
    residual_impact = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    risk = relationship('Risk', back_populates='treatments')
    actions = relationship('TreatmentAction', back_populates='treatment', cascade='all, delete-orphan')
    created_by = relationship('User', foreign_keys=[created_by_id])
    reviewed_by = relationship('User', foreign_keys=[reviewed_by_id])


class TreatmentAction(Base):
    __tablename__ = 'treatment_actions'

    id = Column(Integer, primary_key=True, index=True)
    treatment_id = Column(Integer, ForeignKey('risk_treatments.id'), nullable=False)
    title = Column(String(140), nullable=False)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    start_date = Column(DateTime, default=_utcnow)
    due_date = Column(DateTime, nullable=True)
    status = Column(String(30), nullable=False, default='Planned')
    result = Column(Text, nullable=True)
    expected_result = Column(Text, nullable=True)
    resources_required = Column(Text, nullable=True)

    treatment = relationship('RiskTreatment', back_populates='actions')
    owner = relationship('User', back_populates='treatment_actions')


class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    risk_id = Column(Integer, ForeignKey('risks.id'), nullable=True)
    action = Column(String(120), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    user = relationship('User', back_populates='audit_logs')
    risk = relationship('Risk', back_populates='audit_logs')
