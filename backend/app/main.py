from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import (
    ROLE_PERMISSIONS,
    can_access_department,
    create_access_token,
    get_current_user,
    hash_password,
    has_permission,
    require_permission,
    verify_password,
)
from app.database import Base, SessionLocal, engine, get_db
from app.models import (
    Activity,
    AuditLog,
    Department,
    Resource,
    Risk,
    RiskAssessment,
    RiskTreatment,
    Role,
    TreatmentAction,
    User,
)
from app.schema_upgrade import upgrade_schema
from app.schemas import (
    RiskAssessmentCreate,
    RiskCreate,
    RiskTreatmentCreate,
    TreatmentActionCreate,
    TreatmentActionUpdate,
    TreatmentDecision,
    TreatmentStatusUpdate,
    UserCreate,
    UserUpdate,
)

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    Base.metadata.create_all(bind=engine)
    upgrade_schema()
    with SessionLocal() as db:
        _ensure_seed_data(db)
    yield


app = FastAPI(title='SMCA Risk Management Platform', version='1.1.0', lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('FRONTEND_ORIGINS', 'http://localhost:5173').split(','),
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _risk_level(score: int) -> str:
    if score <= 4:
        return 'Low'
    if score <= 9:
        return 'Moderate'
    if score <= 16:
        return 'High'
    return 'Critical'


def _audit(
    db: Session,
    user: User,
    action: str,
    details: str,
    risk_id: int | None = None,
) -> None:
    db.add(AuditLog(user_id=user.id, risk_id=risk_id, action=action, details=details))


def _ensure_seed_data(db: Session) -> None:
    def get_or_create_role(name: str, description: str) -> Role:
        role = db.query(Role).filter(Role.name == name).first()
        if role:
            return role
        role = Role(name=name, description=description)
        db.add(role)
        db.commit()
        db.refresh(role)
        return role

    def get_or_create_department(name: str, description: str) -> Department:
        department = db.query(Department).filter(Department.name == name).first()
        if department:
            return department
        department = Department(name=name, description=description)
        db.add(department)
        db.commit()
        db.refresh(department)
        return department

    def get_or_create_activity(name: str, description: str, department_id: int) -> Activity:
        activity = db.query(Activity).filter(
            Activity.name == name,
            Activity.department_id == department_id,
        ).first()
        if activity:
            return activity
        activity = Activity(name=name, description=description, department_id=department_id)
        db.add(activity)
        db.commit()
        db.refresh(activity)
        return activity

    admin_role = get_or_create_role('Administrator', 'Full platform access')
    get_or_create_role('SMCA Manager', 'Global risk governance')
    risk_manager_role = get_or_create_role('Risk Manager', 'Risk analysis and planning')
    get_or_create_role('Department Manager', 'Department-level risk ownership')
    get_or_create_role('Auditor', 'Read-only validation access')

    it_department = get_or_create_department('IT', 'Infrastructure and application operations')
    finance_department = get_or_create_department('Finance', 'Financial systems and controls')
    hr_department = get_or_create_department('HR', 'People and organisation management')

    app_activity = get_or_create_activity(
        'Application Hosting',
        'Production hosting of business applications',
        it_department.id,
    )
    payment_activity = get_or_create_activity(
        'Payment Processing',
        'Finance and payment service workflows',
        finance_department.id,
    )
    get_or_create_activity(
        'Employee Data Management',
        'HR records and support operations',
        hr_department.id,
    )

    if not db.query(Resource).filter(Resource.name == 'Production Server').first():
        db.add_all([
            Resource(
                name='Production Server',
                category='Infrastructure',
                description='Primary production workload',
                activity_id=app_activity.id,
            ),
            Resource(
                name='Database Cluster',
                category='Data',
                description='Business database and backups',
                activity_id=app_activity.id,
            ),
            Resource(
                name='Banking API Gateway',
                category='Application',
                description='Financial integration',
                activity_id=payment_activity.id,
            ),
        ])
        db.commit()

    admin = db.query(User).filter(User.username == 'admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@smca.local',
            full_name='System Administrator',
            password_hash=hash_password(os.getenv('DEMO_ADMIN_PASSWORD', 'admin123')),
            role_id=admin_role.id,
            department_id=it_department.id,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)

    risk_manager = db.query(User).filter(User.username == 'riskmanager').first()
    if not risk_manager:
        risk_manager = User(
            username='riskmanager',
            email='risk@smca.local',
            full_name='Risk Manager',
            password_hash=hash_password(os.getenv('DEMO_RISK_MANAGER_PASSWORD', 'admin123')),
            role_id=risk_manager_role.id,
            department_id=it_department.id,
            is_active=True,
        )
        db.add(risk_manager)
        db.commit()
        db.refresh(risk_manager)

    smca_manager_role = db.query(Role).filter(Role.name == 'SMCA Manager').first()
    if smca_manager_role is None:
        raise RuntimeError('SMCA Manager role is missing after role initialization')
    smca_manager = db.query(User).filter(User.username == 'smcamanager').first()
    if not smca_manager:
        smca_manager = User(
            username='smcamanager',
            email='smca.manager@smca.local',
            full_name='SMCA Manager',
            password_hash=hash_password(os.getenv('DEMO_SMCA_MANAGER_PASSWORD', 'admin123')),
            role_id=smca_manager_role.id,
            department_id=None,
            is_active=True,
        )
        db.add(smca_manager)
        db.commit()

    if not db.query(Risk).filter(Risk.code == 'RISK-001').first():
        server_risk = Risk(
            code='RISK-001',
            name='Production server outage',
            description='A production server failure could interrupt critical applications.',
            category='Technical',
            department_id=it_department.id,
            activity_id=app_activity.id,
            threat='Hardware failure',
            vulnerability='No redundancy',
            consequence='Service interruption and financial impact.',
            owner_id=risk_manager.id,
        )
        ransomware_risk = Risk(
            code='RISK-002',
            name='Ransomware attack',
            description='Malicious encryption of servers and data may disrupt operations.',
            category='Cybersecurity',
            department_id=it_department.id,
            activity_id=app_activity.id,
            threat='Ransomware',
            vulnerability='Legacy endpoint protection',
            consequence='Data loss and operational disruption.',
            owner_id=risk_manager.id,
        )
        payment_risk = Risk(
            code='RISK-003',
            name='Payment disruption',
            description='Payment services may fail during peak banking periods.',
            category='Operational',
            department_id=finance_department.id,
            activity_id=payment_activity.id,
            threat='Third-party outage',
            vulnerability='Single provider dependency',
            consequence='Delayed settlements and revenue loss.',
            owner_id=risk_manager.id,
        )
        db.add_all([server_risk, ransomware_risk, payment_risk])
        db.commit()
        db.add_all([
            RiskAssessment(
                risk_id=server_risk.id,
                probability=4,
                impact=5,
                score=20,
                level='Critical',
                assessment_type='Inherent',
                comments='High service impact',
            ),
            RiskAssessment(
                risk_id=ransomware_risk.id,
                probability=4,
                impact=5,
                score=20,
                level='Critical',
                assessment_type='Inherent',
                comments='High cyber risk',
            ),
            RiskAssessment(
                risk_id=payment_risk.id,
                probability=3,
                impact=4,
                score=12,
                level='High',
                assessment_type='Inherent',
                comments='Operational risk',
            ),
        ])
        db.commit()

        server_treatment = RiskTreatment(
            risk_id=server_risk.id,
            strategy='Reduce',
            treatment_plan='Deploy redundant servers and daily backup verification.',
            expected_result='Restore critical services within the agreed recovery time.',
            residual_risk='Moderate',
            status='In progress',
            created_by_id=admin.id,
        )
        ransomware_treatment = RiskTreatment(
            risk_id=ransomware_risk.id,
            strategy='Reduce',
            treatment_plan='Enable EDR, patching, and backup restore drills.',
            expected_result='Contain malware and restore clean systems from tested backups.',
            residual_risk='High',
            status='Proposed',
            created_by_id=risk_manager.id,
        )
        db.add_all([server_treatment, ransomware_treatment])
        db.commit()
        db.add_all([
            TreatmentAction(
                treatment_id=server_treatment.id,
                title='Set up load balancer',
                owner_id=risk_manager.id,
                status='In progress',
                expected_result='Traffic fails over to a healthy server.',
            ),
            TreatmentAction(
                treatment_id=ransomware_treatment.id,
                title='Patch endpoints',
                owner_id=risk_manager.id,
                status='Planned',
                expected_result='All supported endpoints run approved security updates.',
            ),
            AuditLog(
                user_id=admin.id,
                risk_id=server_risk.id,
                action='demo_seeded',
                details='Initial SMCA demonstration data created',
            ),
        ])
        db.commit()


def _get_risk(db: Session, risk_id: int, user: User) -> Risk:
    risk = db.query(Risk).filter(Risk.id == risk_id).first()
    if risk is None or not can_access_department(user, risk.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Risk not found')
    return risk


def _get_treatment(db: Session, treatment_id: int, user: User) -> RiskTreatment:
    treatment = db.query(RiskTreatment).filter(RiskTreatment.id == treatment_id).first()
    if treatment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Treatment plan not found')
    if not can_access_department(user, treatment.risk.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Treatment plan not found')
    return treatment


def _serialize_assessment(assessment: RiskAssessment | None) -> dict | None:
    if assessment is None:
        return None
    return {
        'probability': assessment.probability,
        'impact': assessment.impact,
        'score': assessment.score,
        'level': assessment.level,
        'type': assessment.assessment_type,
        'assessment_date': assessment.assessment_date.isoformat() if assessment.assessment_date else None,
        'comments': assessment.comments,
    }


def _serialize_risk(risk: Risk) -> dict:
    assessments = sorted(
        risk.assessments,
        key=lambda item: (item.assessment_date or datetime.min, item.id),
    )
    inherent = next((item for item in reversed(assessments) if item.assessment_type == 'Inherent'), None)
    residual = next((item for item in reversed(assessments) if item.assessment_type == 'Residual'), None)
    latest = assessments[-1] if assessments else None
    return {
        'id': risk.id,
        'code': risk.code,
        'name': risk.name,
        'category': risk.category,
        'description': risk.description,
        'department_id': risk.department_id,
        'department': risk.department.name if risk.department else '',
        'activity_id': risk.activity_id,
        'activity': risk.activity.name if risk.activity else '',
        'owner_id': risk.owner_id,
        'owner': risk.owner.full_name if risk.owner else 'Unassigned',
        'probability': latest.probability if latest else 0,
        'impact': latest.impact if latest else 0,
        'score': latest.score if latest else 0,
        'level': latest.level if latest else 'Unassessed',
        'inherent_assessment': _serialize_assessment(inherent),
        'residual_assessment': _serialize_assessment(residual),
        'threat': risk.threat,
        'vulnerability': risk.vulnerability,
        'consequence': risk.consequence,
        'created_at': risk.created_at.isoformat() if risk.created_at else None,
        'treatment_count': len(risk.treatments),
    }


def _serialize_action(action: TreatmentAction) -> dict:
    return {
        'id': action.id,
        'title': action.title,
        'owner_id': action.owner_id,
        'owner': action.owner.full_name if action.owner else 'Unassigned',
        'start_date': action.start_date.isoformat() if action.start_date else None,
        'due_date': action.due_date.isoformat() if action.due_date else None,
        'status': action.status,
        'result': action.result,
        'expected_result': action.expected_result,
        'resources_required': action.resources_required,
        'overdue': bool(
            action.due_date
            and action.due_date < _utcnow()
            and action.status != 'Completed'
        ),
    }


def _serialize_treatment(treatment: RiskTreatment) -> dict:
    return {
        'id': treatment.id,
        'risk_id': treatment.risk_id,
        'risk_code': treatment.risk.code,
        'risk_name': treatment.risk.name,
        'strategy': treatment.strategy,
        'treatment_plan': treatment.treatment_plan,
        'expected_result': treatment.expected_result,
        'resources_required': treatment.resources_required,
        'residual_risk': treatment.residual_risk,
        'residual_probability': treatment.residual_probability,
        'residual_impact': treatment.residual_impact,
        'residual_score': (
            treatment.residual_probability * treatment.residual_impact
            if treatment.residual_probability is not None and treatment.residual_impact is not None
            else None
        ),
        'status': treatment.status,
        'start_date': treatment.start_date.isoformat() if treatment.start_date else None,
        'due_date': treatment.due_date.isoformat() if treatment.due_date else None,
        'created_by': treatment.created_by.full_name if treatment.created_by else 'System',
        'reviewed_by': treatment.reviewed_by.full_name if treatment.reviewed_by else None,
        'review_comment': treatment.review_comment,
        'updated_at': treatment.updated_at.isoformat() if treatment.updated_at else None,
        'actions': [_serialize_action(action) for action in treatment.actions],
    }


def _treatment_owner(user: User, treatment: RiskTreatment) -> bool:
    return (
        user.role.name in {'Administrator', 'SMCA Manager', 'Risk Manager'}
        or treatment.created_by_id == user.id
        or treatment.risk.owner_id == user.id
    )


@app.get('/api/health')
def health_check(db: Session = Depends(get_db)) -> dict:
    db.execute(text('SELECT 1'))
    return {'status': 'ok', 'database': 'connected'}


@app.post('/api/auth/login')
def login(payload: dict = Body(...), db: Session = Depends(get_db)) -> dict:
    username = payload.get('username')
    password = payload.get('password')
    if not isinstance(username, str) or not isinstance(password, str) or not username or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Username and password are required')
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    token = create_access_token(user.username)
    return {
        'access_token': token,
        'token_type': 'bearer',
        'user': {
            'id': user.id,
            'username': user.username,
            'full_name': user.full_name,
            'email': user.email,
            'role': user.role.name if user.role else 'Unknown',
        },
    }


@app.get('/api/me')
def get_me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        'id': current_user.id,
        'username': current_user.username,
        'email': current_user.email,
        'full_name': current_user.full_name,
        'role': current_user.role.name if current_user.role else 'Unknown',
        'department_id': current_user.department_id,
        'department': current_user.department.name if current_user.department else None,
        'permissions': sorted(ROLE_PERMISSIONS.get(current_user.role.name, ())) if current_user.role else [],
    }


@app.get('/api/dashboard/summary')
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> dict:
    risks_query = db.query(Risk)
    if current_user.role.name == 'Department Manager':
        risks_query = risks_query.filter(Risk.department_id == current_user.department_id)
    risks = risks_query.all()
    assessments = {
        risk.id: sorted(
            risk.assessments,
            key=lambda item: (item.assessment_date or datetime.min, item.id),
        )[-1]
        for risk in risks
        if risk.assessments
    }
    counts = {level: 0 for level in ('Critical', 'High', 'Moderate', 'Low')}
    for assessment in assessments.values():
        counts[assessment.level] = counts.get(assessment.level, 0) + 1

    category_breakdown: dict[str, int] = {}
    for risk in risks:
        category_breakdown[risk.category] = category_breakdown.get(risk.category, 0) + 1

    treatment_ids = [
        treatment.id
        for risk in risks
        for treatment in risk.treatments
    ]
    treatments = db.query(RiskTreatment).filter(RiskTreatment.id.in_(treatment_ids)).all() if treatment_ids else []
    actions = [action for treatment in treatments for action in treatment.actions]
    now = _utcnow()
    overdue_actions = sum(
        bool(action.due_date and action.due_date < now and action.status != 'Completed')
        for action in actions
    )
    completed_treatments = sum(treatment.status == 'Completed' for treatment in treatments)

    recent_risks = sorted(
        risks,
        key=lambda item: (item.created_at or datetime.min, item.id),
        reverse=True,
    )[:6]
    return {
        'total_risks': len(risks),
        'critical': counts['Critical'],
        'high': counts['High'],
        'moderate': counts['Moderate'],
        'low': counts['Low'],
        'breakdown': category_breakdown,
        'recent_risks': [
            {
                'code': risk.code,
                'name': risk.name,
                'category': risk.category,
                'level': assessments[risk.id].level if risk.id in assessments else 'Unassessed',
                'owner': risk.owner.full_name if risk.owner else 'Unassigned',
            }
            for risk in recent_risks
        ],
        'treatments_in_progress': sum(treatment.status == 'In progress' for treatment in treatments),
        'treatments_completed': completed_treatments,
        'treatments_overdue': sum(
            bool(
                treatment.due_date
                and treatment.due_date < now
                and treatment.status not in {'Completed', 'Cancelled', 'Rejected'}
            )
            for treatment in treatments
        ),
        'actions_overdue': overdue_actions,
        'treatment_completion_rate': round(
            completed_treatments * 100 / len(treatments),
            1,
        ) if treatments else 0,
    }


@app.get('/api/roles')
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission('users:manage')),
) -> list[dict]:
    roles = db.query(Role).order_by(Role.id).all()
    return [
        {
            'id': role.id,
            'name': role.name,
            'description': role.description,
            'permissions': sorted(ROLE_PERMISSIONS.get(role.name, ())),
        }
        for role in roles
    ]


@app.get('/api/departments')
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    departments = db.query(Department).order_by(Department.name).all()
    if current_user.role.name == 'Department Manager':
        departments = [department for department in departments if department.id == current_user.department_id]
    return [
        {
            'id': department.id,
            'name': department.name,
            'description': department.description,
            'activity_count': len(department.activities),
        }
        for department in departments
    ]


@app.post('/api/departments', status_code=status.HTTP_201_CREATED)
def create_department(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('departments:write')),
) -> dict:
    name = payload.get('name')
    if not isinstance(name, str) or not name.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Department name is required')
    if db.query(Department).filter(Department.name == name.strip()).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Department already exists')
    department = Department(name=name.strip(), description=payload.get('description'))
    db.add(department)
    db.flush()
    _audit(db, current_user, 'department_created', f'Department {department.name} created')
    db.commit()
    return {'id': department.id, 'name': department.name}


@app.get('/api/activities')
def list_activities(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    activities = db.query(Activity).join(Department).order_by(Activity.name).all()
    return [
        {
            'id': activity.id,
            'name': activity.name,
            'description': activity.description,
            'department_id': activity.department_id,
            'department_name': activity.department.name,
        }
        for activity in activities
        if can_access_department(current_user, activity.department_id)
    ]


@app.post('/api/activities', status_code=status.HTTP_201_CREATED)
def create_activity(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('departments:write')),
) -> dict:
    name = payload.get('name')
    department_id = payload.get('department_id')
    department = db.query(Department).filter(Department.id == department_id).first()
    if not isinstance(name, str) or not name.strip() or department is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Valid name and department_id are required')
    activity = Activity(
        name=name.strip(),
        description=payload.get('description'),
        department_id=department.id,
    )
    db.add(activity)
    db.flush()
    _audit(db, current_user, 'activity_created', f'Activity {activity.name} created')
    db.commit()
    return {'id': activity.id, 'name': activity.name, 'department_id': activity.department_id}


@app.get('/api/resources')
def list_resources(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    return [
        {
            'id': resource.id,
            'name': resource.name,
            'category': resource.category,
            'description': resource.description,
            'activity_id': resource.activity_id,
        }
        for resource in db.query(Resource).join(Activity).all()
        if can_access_department(current_user, resource.activity.department_id)
    ]


@app.get('/api/risks')
def list_risks(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    risks = db.query(Risk).order_by(Risk.created_at.desc()).all()
    return [
        _serialize_risk(risk)
        for risk in risks
        if can_access_department(current_user, risk.department_id)
    ]


@app.post('/api/risks', status_code=status.HTTP_201_CREATED)
def create_risk(
    payload: RiskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:create')),
) -> dict:
    if not can_access_department(current_user, payload.department_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You can only create risks in your department')
    if db.query(Risk).filter(Risk.code == payload.code).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Risk code already exists')
    if not db.query(Department).filter(Department.id == payload.department_id).first():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Department does not exist')
    if payload.activity_id is not None:
        activity = db.query(Activity).filter(Activity.id == payload.activity_id).first()
        if activity is None or activity.department_id != payload.department_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Activity must belong to the selected department')
    owner_id = payload.owner_id if payload.owner_id is not None else current_user.id
    owner = db.query(User).filter(User.id == owner_id, User.is_active.is_(True)).first()
    if owner is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Risk owner does not exist or is inactive')

    risk = Risk(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        department_id=payload.department_id,
        activity_id=payload.activity_id,
        threat=payload.threat,
        vulnerability=payload.vulnerability,
        consequence=payload.consequence,
        owner_id=owner.id,
    )
    db.add(risk)
    db.flush()
    score = payload.probability * payload.impact
    assessment = RiskAssessment(
        risk_id=risk.id,
        probability=payload.probability,
        impact=payload.impact,
        score=score,
        level=_risk_level(score),
        assessment_type='Inherent',
        comments='Initial assessment',
    )
    db.add(assessment)
    _audit(db, current_user, 'risk_created', f'Risk {risk.code} created', risk.id)
    db.commit()
    return {'id': risk.id, 'code': risk.code, 'score': score, 'level': assessment.level}


@app.post('/api/risks/{risk_id}/assessments', status_code=status.HTTP_201_CREATED)
def create_assessment(
    risk_id: int,
    payload: RiskAssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:assess')),
) -> dict:
    risk = _get_risk(db, risk_id, current_user)
    score = payload.probability * payload.impact
    assessment = RiskAssessment(
        risk_id=risk.id,
        probability=payload.probability,
        impact=payload.impact,
        score=score,
        level=_risk_level(score),
        assessment_type='Inherent',
        comments=payload.comments,
    )
    db.add(assessment)
    _audit(db, current_user, 'risk_reassessed', f'Inherent risk reassessed: {score}/25', risk.id)
    db.commit()
    db.refresh(assessment)
    return _serialize_assessment(assessment)


@app.get('/api/risk-matrix')
def risk_matrix(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    risks = db.query(Risk).all()
    counts: dict[str, int] = {}
    for risk in risks:
        if not can_access_department(current_user, risk.department_id):
            continue
        latest = sorted(
            risk.assessments,
            key=lambda item: (item.assessment_date or datetime.min, item.id),
        )
        level = latest[-1].level if latest else 'Unassessed'
        counts[level] = counts.get(level, 0) + 1
    return [
        {'level': level, 'count': counts.get(level, 0)}
        for level in ('Low', 'Moderate', 'High', 'Critical', 'Unassessed')
    ]


@app.get('/api/risk-treatments')
def list_treatments(
    status_filter: str | None = Query(default=None, alias='status'),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    treatments = db.query(RiskTreatment).join(Risk).order_by(RiskTreatment.updated_at.desc()).all()
    if status_filter:
        treatments = [treatment for treatment in treatments if treatment.status == status_filter]
    return [
        _serialize_treatment(treatment)
        for treatment in treatments
        if can_access_department(current_user, treatment.risk.department_id)
    ]


@app.get('/api/risks/{risk_id}/treatments')
def list_risk_treatments(
    risk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    risk = _get_risk(db, risk_id, current_user)
    return [_serialize_treatment(treatment) for treatment in risk.treatments]


@app.post('/api/risks/{risk_id}/treatments', status_code=status.HTTP_201_CREATED)
def create_treatment(
    risk_id: int,
    payload: RiskTreatmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('treatments:manage')),
) -> dict:
    risk = _get_risk(db, risk_id, current_user)
    if current_user.role.name == 'Department Manager' and risk.owner_id not in {None, current_user.id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You may only propose treatment for risks you own')
    start_date = _normalize_datetime(payload.start_date) or _utcnow()
    due_date = _normalize_datetime(payload.due_date)
    if due_date and due_date < start_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Due date must be on or after the start date')
    treatment = RiskTreatment(
        risk_id=risk.id,
        strategy=payload.strategy,
        treatment_plan=payload.treatment_plan,
        expected_result=payload.expected_result,
        resources_required=payload.resources_required,
        residual_risk='Unassessed',
        status='Proposed',
        start_date=start_date,
        due_date=due_date,
        created_by_id=current_user.id,
    )
    db.add(treatment)
    db.flush()
    _audit(db, current_user, 'treatment_proposed', f'{payload.strategy} plan proposed', risk.id)
    db.commit()
    db.refresh(treatment)
    return _serialize_treatment(treatment)


@app.post('/api/risk-treatments', status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_treatment_legacy(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('treatments:manage')),
) -> dict:
    try:
        validated = RiskTreatmentCreate.model_validate(payload)
        risk_id = int(payload['risk_id'])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Invalid treatment request') from exc
    return create_treatment(risk_id, validated, db, current_user)


@app.post('/api/risk-treatments/{treatment_id}/decision')
def review_treatment(
    treatment_id: int,
    payload: TreatmentDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('treatments:approve')),
) -> dict:
    treatment = _get_treatment(db, treatment_id, current_user)
    if treatment.status != 'Proposed':
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Only proposed treatment plans can be reviewed')
    if treatment.created_by_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You cannot review your own treatment proposal')
    treatment.status = 'Approved' if payload.decision == 'approve' else 'Rejected'
    treatment.reviewed_by_id = current_user.id
    treatment.review_comment = payload.comment
    treatment.updated_at = _utcnow()
    _audit(
        db,
        current_user,
        'treatment_approved' if payload.decision == 'approve' else 'treatment_rejected',
        payload.comment,
        treatment.risk_id,
    )
    db.commit()
    db.refresh(treatment)
    return _serialize_treatment(treatment)


@app.patch('/api/risk-treatments/{treatment_id}/status')
def update_treatment_status(
    treatment_id: int,
    payload: TreatmentStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('treatments:manage')),
) -> dict:
    treatment = _get_treatment(db, treatment_id, current_user)
    if not _treatment_owner(current_user, treatment):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only the plan owner or risk manager can update this plan')

    transitions = {
        'Proposed': {'Cancelled'},
        'Approved': {'In progress', 'Cancelled'},
        'In progress': {'Completed', 'Cancelled'},
    }
    if payload.status not in transitions.get(treatment.status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Cannot move a {treatment.status} plan to {payload.status}',
        )

    if payload.status == 'Completed':
        if payload.residual_probability is None or payload.residual_impact is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail='Residual probability and impact are required to complete a plan',
            )
        if not treatment.actions or any(action.status != 'Completed' for action in treatment.actions):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail='Add and complete all treatment actions before completing the plan',
            )
        residual_score = payload.residual_probability * payload.residual_impact
        treatment.residual_probability = payload.residual_probability
        treatment.residual_impact = payload.residual_impact
        treatment.residual_risk = _risk_level(residual_score)
        db.add(RiskAssessment(
            risk_id=treatment.risk_id,
            probability=payload.residual_probability,
            impact=payload.residual_impact,
            score=residual_score,
            level=treatment.residual_risk,
            assessment_type='Residual',
            comments=f'Residual assessment after treatment #{treatment.id}',
        ))

    treatment.status = payload.status
    treatment.updated_at = _utcnow()
    _audit(
        db,
        current_user,
        'treatment_status_changed',
        f'Treatment plan status changed to {payload.status}',
        treatment.risk_id,
    )
    db.commit()
    db.refresh(treatment)
    return _serialize_treatment(treatment)


@app.post('/api/risk-treatments/{treatment_id}/actions', status_code=status.HTTP_201_CREATED)
def create_action(
    treatment_id: int,
    payload: TreatmentActionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('treatments:manage')),
) -> dict:
    treatment = _get_treatment(db, treatment_id, current_user)
    if not _treatment_owner(current_user, treatment):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Only the plan owner or risk manager can add actions')
    if treatment.status not in {'Approved', 'In progress'}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Actions can only be added to approved or active plans')
    if payload.owner_id is not None:
        owner = db.query(User).filter(User.id == payload.owner_id, User.is_active.is_(True)).first()
        if owner is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Action owner does not exist or is inactive')
        if owner.department_id != treatment.risk.department_id and owner.role.name == 'Department Manager':
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Action owner must belong to the risk department')
    start_date = _normalize_datetime(payload.start_date) or _utcnow()
    due_date = _normalize_datetime(payload.due_date)
    if due_date and due_date < start_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Due date must be on or after the start date')
    action = TreatmentAction(
        treatment_id=treatment.id,
        title=payload.title,
        owner_id=payload.owner_id,
        start_date=start_date,
        due_date=due_date,
        status='Planned',
        expected_result=payload.expected_result,
        resources_required=payload.resources_required,
    )
    db.add(action)
    treatment.updated_at = _utcnow()
    _audit(db, current_user, 'treatment_action_created', f'Action added: {action.title}', treatment.risk_id)
    db.commit()
    db.refresh(action)
    return _serialize_action(action)


@app.patch('/api/treatment-actions/{action_id}')
def update_action(
    action_id: int,
    payload: TreatmentActionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    action = db.query(TreatmentAction).filter(TreatmentAction.id == action_id).first()
    if action is None or not can_access_department(current_user, action.treatment.risk.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Treatment action not found')
    treatment = action.treatment
    if not has_permission(current_user, 'treatments:manage') and action.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You are not responsible for this action')
    if not _treatment_owner(current_user, treatment) and action.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='You are not responsible for this action')
    changes = payload.model_dump(exclude_unset=True)
    next_status = changes.get('status', action.status)
    allowed_statuses = {
        'Planned': {'In progress', 'Blocked'},
        'In progress': {'Blocked', 'Completed'},
        'Blocked': {'In progress'},
        'Completed': set(),
    }
    if next_status != action.status and next_status not in allowed_statuses[action.status]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Cannot move an action from {action.status} to {next_status}',
        )
    if 'owner_id' in changes and changes['owner_id'] is not None:
        owner = db.query(User).filter(User.id == changes['owner_id'], User.is_active.is_(True)).first()
        if owner is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Action owner does not exist or is inactive')
    for field in ('start_date', 'due_date'):
        if field in changes:
            changes[field] = _normalize_datetime(changes[field])
    for field, value in changes.items():
        setattr(action, field, value)
    if action.start_date and action.due_date and action.due_date < action.start_date:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Due date must be on or after the start date')
    if next_status == 'Completed' and not (action.result and action.result.strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Record the action result before completing it',
        )
    treatment.updated_at = _utcnow()
    _audit(db, current_user, 'treatment_action_updated', f'Action {action.id} updated to {action.status}', treatment.risk_id)
    db.commit()
    db.refresh(action)
    return _serialize_action(action)


@app.post('/api/treatment-actions', status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_action_legacy(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('treatments:manage')),
) -> dict:
    try:
        treatment_id = int(payload['treatment_id'])
        validated = TreatmentActionCreate.model_validate(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Invalid action request') from exc
    return create_action(treatment_id, validated, db, current_user)


@app.get('/api/users')
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission('users:manage')),
) -> list[dict]:
    users = db.query(User).order_by(User.full_name).all()
    return [
        {
            'id': user.id,
            'username': user.username,
            'full_name': user.full_name,
            'email': user.email,
            'role': user.role.name if user.role else 'Unknown',
            'department_id': user.department_id,
            'department': user.department.name if user.department else 'Unassigned',
            'is_active': user.is_active,
        }
        for user in users
    ]


@app.get('/api/user-directory')
def user_directory(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    users = db.query(User).filter(User.is_active.is_(True)).order_by(User.full_name).all()
    return [
        {'id': user.id, 'full_name': user.full_name, 'department_id': user.department_id}
        for user in users
        if user.department_id is None or can_access_department(current_user, user.department_id)
    ]


@app.post('/api/users', status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('users:manage')),
) -> dict:
    if db.query(User).filter((User.username == payload.username) | (User.email == payload.email)).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username or email is already in use')
    role = db.query(Role).filter(Role.name == payload.role).first()
    if role is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Role is not configured')
    if payload.department_id is not None and not db.query(Department).filter(Department.id == payload.department_id).first():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Department does not exist')
    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role_id=role.id,
        department_id=payload.department_id,
        is_active=True,
    )
    db.add(user)
    db.flush()
    _audit(db, current_user, 'user_created', f'User {user.username} created with role {role.name}')
    db.commit()
    return {'id': user.id, 'username': user.username, 'role': role.name}


@app.patch('/api/users/{user_id}')
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('users:manage')),
) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='User not found')
    updates = payload.model_dump(exclude_unset=True)
    if user.id == current_user.id and updates.get('is_active') is False:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='You cannot deactivate your own account')
    if 'email' in updates and db.query(User).filter(User.email == updates['email'], User.id != user_id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Email is already in use')
    if 'role' in updates:
        role = db.query(Role).filter(Role.name == updates.pop('role')).first()
        if role is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Role is not configured')
        user.role_id = role.id
    if updates.get('department_id') is not None:
        department = db.query(Department).filter(Department.id == updates['department_id']).first()
        if department is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Department does not exist')
    for field, value in updates.items():
        setattr(user, field, value)
    _audit(db, current_user, 'user_updated', f'User {user.username} updated')
    db.commit()
    return {'id': user.id, 'username': user.username, 'is_active': user.is_active}


@app.get('/api/audit-logs')
def list_audit_logs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('audit:read')),
) -> list[dict]:
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()
    return [
        {
            'id': record.id,
            'action': record.action,
            'details': record.details,
            'created_at': record.created_at.isoformat() if record.created_at else None,
            'user': record.user.full_name if record.user else 'System',
            'risk_code': record.risk.code if record.risk else None,
        }
        for record in logs
        if record.risk is None or can_access_department(current_user, record.risk.department_id)
    ]


@app.get('/api/reports/export')
def export_report(
    format: str = Query(default='pdf', pattern='^(pdf|excel)$'),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('reports:read')),
) -> FileResponse:
    risks = [
        risk
        for risk in db.query(Risk).order_by(Risk.code).all()
        if can_access_department(current_user, risk.department_id)
    ]
    report_dir = Path(__file__).resolve().parent.parent / 'reports'
    report_dir.mkdir(exist_ok=True)

    if format == 'pdf':
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

        output_path = report_dir / 'smca-risk-report.pdf'
        document = SimpleDocTemplate(str(output_path), pagesize=landscape(letter))
        rows = [['Code', 'Risk', 'Department', 'Category', 'Score', 'Level']]
        for risk in risks:
            assessment = max(risk.assessments, key=lambda item: item.id, default=None)
            rows.append([
                risk.code,
                risk.name,
                risk.department.name if risk.department else '',
                risk.category,
                str(assessment.score) if assessment else '—',
                assessment.level if assessment else 'Unassessed',
            ])
        table = Table(rows, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16324f')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#d6dee8')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f2f6fa')]),
            ('PADDING', (0, 0), (-1, -1), 7),
        ]))
        document.build([table])
        return FileResponse(path=str(output_path), media_type='application/pdf', filename='smca-risk-report.pdf')

    import openpyxl

    output_path = report_dir / 'smca-risk-report.xlsx'
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = 'Risk Register'
    sheet.append(['Code', 'Risk', 'Department', 'Activity', 'Category', 'Score', 'Level', 'Owner'])
    for risk in risks:
        assessment = max(risk.assessments, key=lambda item: item.id, default=None)
        sheet.append([
            risk.code,
            risk.name,
            risk.department.name if risk.department else '',
            risk.activity.name if risk.activity else '',
            risk.category,
            assessment.score if assessment else None,
            assessment.level if assessment else 'Unassessed',
            risk.owner.full_name if risk.owner else 'Unassigned',
        ])
    workbook.save(output_path)
    return FileResponse(
        path=str(output_path),
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename='smca-risk-report.xlsx',
    )
