from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    must_change_password = Column(Boolean, default=False, nullable=False)
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=False)
    department_id = Column(Integer, ForeignKey('departments.id'), nullable=True)

    role = relationship('Role', back_populates='users')
    department = relationship('Department', back_populates='users')
    audit_logs = relationship('AuditLog', back_populates='user')
    treatment_actions = relationship('TreatmentAction', back_populates='owner')
    identified_risks = relationship('Risk', foreign_keys='Risk.identified_by_id', back_populates='identified_by')
    owned_controls = relationship('RiskControl', foreign_keys='RiskControl.owner_id', back_populates='owner')
    bia_assessments = relationship('BusinessImpactAnalysis', back_populates='assessed_by')
    owned_indicators = relationship('RiskIndicator', foreign_keys='RiskIndicator.owner_id', back_populates='owner')
    uploaded_attachments = relationship('RiskAttachment', back_populates='uploaded_by')
    created_incidents = relationship('Incident', back_populates='created_by')


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
    business_impact_assessments = relationship(
        'BusinessImpactAnalysis',
        back_populates='activity',
        cascade='all, delete-orphan',
    )
    outgoing_dependencies = relationship(
        'ActivityDependency',
        foreign_keys='ActivityDependency.source_activity_id',
        back_populates='source_activity',
        cascade='all, delete-orphan',
    )
    incoming_dependencies = relationship(
        'ActivityDependency',
        foreign_keys='ActivityDependency.target_activity_id',
        back_populates='target_activity',
        cascade='all, delete-orphan',
    )


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
    source = Column(String(160), nullable=True)
    causes = Column(Text, nullable=True)
    existing_measures = Column(Text, nullable=True)
    review_date = Column(DateTime, nullable=True)
    status = Column(String(30), nullable=False, default='Draft')
    acceptance_justification = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    identified_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    department = relationship('Department', back_populates='risks')
    activity = relationship('Activity', back_populates='risks')
    owner = relationship('User', foreign_keys=[owner_id])
    identified_by = relationship('User', foreign_keys=[identified_by_id], back_populates='identified_risks')
    assessments = relationship('RiskAssessment', back_populates='risk', cascade='all, delete-orphan')
    treatments = relationship('RiskTreatment', back_populates='risk', cascade='all, delete-orphan')
    controls = relationship('RiskControl', back_populates='risk', cascade='all, delete-orphan')
    indicators = relationship('RiskIndicator', back_populates='risk', cascade='all, delete-orphan')
    incidents = relationship('Incident', back_populates='risk')
    attachments = relationship('RiskAttachment', back_populates='risk', cascade='all, delete-orphan')
    audit_logs = relationship('AuditLog', back_populates='risk')


class SmcaScope(Base):
    __tablename__ = 'smca_scopes'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=False)
    objectives = Column(Text, nullable=True)
    exclusions = Column(Text, nullable=True)
    stakeholders = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default='Draft')
    review_date = Column(DateTime, nullable=True)
    acceptance_threshold = Column(Integer, nullable=False, default=9)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class BusinessImpactAnalysis(Base):
    __tablename__ = 'business_impact_analyses'

    id = Column(Integer, primary_key=True, index=True)
    activity_id = Column(Integer, ForeignKey('activities.id'), nullable=False)
    assessed_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    financial_impact = Column(Integer, nullable=False)
    operational_impact = Column(Integer, nullable=False)
    legal_impact = Column(Integer, nullable=False)
    reputational_impact = Column(Integer, nullable=False)
    criticality = Column(Integer, nullable=False)
    rto_hours = Column(Integer, nullable=False)
    rpo_hours = Column(Integer, nullable=False)
    mtpd_hours = Column(Integer, nullable=False)
    dependencies = Column(Text, nullable=True)
    recovery_requirements = Column(Text, nullable=True)
    comments = Column(Text, nullable=True)
    assessed_at = Column(DateTime, default=_utcnow)

    activity = relationship('Activity', back_populates='business_impact_assessments')
    assessed_by = relationship('User', back_populates='bia_assessments')


class RiskControl(Base):
    __tablename__ = 'risk_controls'

    id = Column(Integer, primary_key=True, index=True)
    risk_id = Column(Integer, ForeignKey('risks.id'), nullable=False)
    name = Column(String(160), nullable=False)
    description = Column(Text, nullable=False)
    control_type = Column(String(30), nullable=False)
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    effectiveness = Column(Integer, nullable=False, default=3)
    status = Column(String(30), nullable=False, default='Implemented')
    evidence_reference = Column(Text, nullable=True)
    last_tested_at = Column(DateTime, nullable=True)
    next_test_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    risk = relationship('Risk', back_populates='controls')
    owner = relationship('User', foreign_keys=[owner_id], back_populates='owned_controls')


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
    residual_risk = Column(String(30), nullable=False, default='Unassessed')
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


class ActivityDependency(Base):
    __tablename__ = 'activity_dependencies'
    __table_args__ = (
        UniqueConstraint('source_activity_id', 'target_activity_id', name='uq_activity_dependency'),
    )

    id = Column(Integer, primary_key=True, index=True)
    source_activity_id = Column(Integer, ForeignKey('activities.id'), nullable=False)
    target_activity_id = Column(Integer, ForeignKey('activities.id'), nullable=False)
    dependency_type = Column(String(50), nullable=False)
    criticality = Column(Integer, nullable=False, default=3)
    description = Column(Text, nullable=True)
    recovery_order = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    source_activity = relationship(
        'Activity',
        foreign_keys=[source_activity_id],
        back_populates='outgoing_dependencies',
    )
    target_activity = relationship(
        'Activity',
        foreign_keys=[target_activity_id],
        back_populates='incoming_dependencies',
    )


class ThreatScenario(Base):
    __tablename__ = 'threat_scenarios'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(160), unique=True, nullable=False)
    category = Column(String(80), nullable=False)
    description = Column(Text, nullable=False)
    common_causes = Column(Text, nullable=True)
    common_vulnerabilities = Column(Text, nullable=True)
    default_probability = Column(Integer, nullable=False, default=3)
    created_at = Column(DateTime, default=_utcnow)


class Incident(Base):
    __tablename__ = 'incidents'

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(40), unique=True, nullable=False)
    title = Column(String(180), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(30), nullable=False, default='Moderate')
    status = Column(String(30), nullable=False, default='Open')
    occurred_at = Column(DateTime, nullable=False, default=_utcnow)
    resolved_at = Column(DateTime, nullable=True)
    department_id = Column(Integer, ForeignKey('departments.id'), nullable=False)
    risk_id = Column(Integer, ForeignKey('risks.id'), nullable=True)
    impact = Column(Text, nullable=True)
    lessons_learned = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    department = relationship('Department')
    risk = relationship('Risk', back_populates='incidents')
    created_by = relationship('User', back_populates='created_incidents')


class RiskIndicator(Base):
    __tablename__ = 'risk_indicators'

    id = Column(Integer, primary_key=True, index=True)
    risk_id = Column(Integer, ForeignKey('risks.id'), nullable=False)
    name = Column(String(160), nullable=False)
    unit = Column(String(40), nullable=False)
    direction = Column(String(30), nullable=False, default='Above is bad')
    warning_threshold = Column(Float, nullable=False)
    critical_threshold = Column(Float, nullable=False)
    current_value = Column(Float, nullable=False)
    frequency = Column(String(50), nullable=False, default='Monthly')
    owner_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    last_updated_at = Column(DateTime, default=_utcnow)

    risk = relationship('Risk', back_populates='indicators')
    owner = relationship('User', foreign_keys=[owner_id], back_populates='owned_indicators')


class RiskAttachment(Base):
    __tablename__ = 'risk_attachments'

    id = Column(Integer, primary_key=True, index=True)
    risk_id = Column(Integer, ForeignKey('risks.id'), nullable=False)
    uploaded_by_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    original_name = Column(String(255), nullable=False)
    storage_name = Column(String(255), unique=True, nullable=False)
    content_type = Column(String(120), nullable=True)
    size_bytes = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    risk = relationship('Risk', back_populates='attachments')
    uploaded_by = relationship('User', back_populates='uploaded_attachments')
