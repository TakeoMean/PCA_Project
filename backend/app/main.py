from __future__ import annotations

import csv
import io
import os
import re
from collections import defaultdict, deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from alembic import command
from alembic.config import Config
from fastapi import Body, Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openpyxl import load_workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    APP_ENV,
    AUTH_COOKIE_NAME,
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
    Incident,
    Resource,
    Risk,
    RiskAssessment,
    RiskControl,
    RiskIndicator,
    RiskTreatment,
    Role,
    TreatmentAction,
    ThreatScenario,
    User,
)
from app.schemas import (
    LoginRequest,
    PasswordChange,
    PasswordReset,
    RiskAssessmentCreate,
    RiskCreate,
    RiskUpdate,
    RiskTreatmentCreate,
    TreatmentActionCreate,
    TreatmentActionUpdate,
    TreatmentDecision,
    TreatmentStatusUpdate,
    UserCreate,
    UserUpdate,
)
from app.smca import router as smca_router
from app.governance import router as governance_router

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    alembic_config = Config(str(Path(__file__).resolve().parent.parent / 'alembic.ini'))
    command.upgrade(alembic_config, 'head')
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
app.include_router(smca_router)
app.include_router(governance_router)

MAX_IMPORT_BYTES = 5 * 1024 * 1024
LOGIN_WINDOW_SECONDS = 5 * 60
LOGIN_MAX_FAILURES = 8
_login_attempts: dict[str, deque[datetime]] = defaultdict(deque)
_login_attempts_lock = Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _login_key(request: Request, username: str) -> str:
    host = request.client.host if request.client else 'unknown'
    return f'{host}:{username.strip().lower()}'


def _login_is_limited(key: str) -> bool:
    cutoff = _utcnow().timestamp() - LOGIN_WINDOW_SECONDS
    with _login_attempts_lock:
        attempts = _login_attempts[key]
        while attempts and attempts[0].timestamp() < cutoff:
            attempts.popleft()
        return len(attempts) >= LOGIN_MAX_FAILURES


def _record_login_failure(key: str) -> None:
    with _login_attempts_lock:
        _login_attempts[key].append(_utcnow())


def _clear_login_failures(key: str) -> None:
    with _login_attempts_lock:
        _login_attempts.pop(key, None)


def _cookie_secure() -> bool:
    configured = os.getenv('COOKIE_SECURE')
    if configured is not None:
        return configured.strip().lower() in {'1', 'true', 'yes', 'on'}
    return APP_ENV == 'production'


def _risk_level(score: int) -> str:
    if score <= 4:
        return 'Low'
    if score <= 9:
        return 'Moderate'
    if score <= 16:
        return 'High'
    return 'Critical'


def _normalize_column_name(value: str | None) -> str:
    if value is None:
        return ''
    return re.sub(r'[^a-z0-9]+', ' ', value.strip().lower()).strip().replace(' ', '_')


def _normalize_import_value(value: object) -> str:
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _read_risk_import_rows(file_bytes: bytes, filename: str) -> list[dict[str, str]]:
    name = (filename or '').lower()
    if name.endswith('.csv'):
        text_stream = io.StringIO(file_bytes.decode('utf-8-sig'))
        return [dict(row) for row in csv.DictReader(text_stream)]
    if name.endswith('.xlsx'):
        workbook = load_workbook(filename=io.BytesIO(file_bytes), read_only=True, data_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [_normalize_import_value(value) for value in rows[0]]
        normalized_headers = [_normalize_column_name(value) for value in headers]
        data_rows: list[dict[str, str]] = []
        for row in rows[1:]:
            if not any(_normalize_import_value(value) for value in row):
                continue
            item = {}
            for index, value in enumerate(row):
                key = normalized_headers[index] if index < len(normalized_headers) else f'column_{index + 1}'
                item[key] = _normalize_import_value(value)
            data_rows.append(item)
        return data_rows
    raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail='Only CSV and XLSX files are supported')


def _find_optional_user(db: Session, value: str | None, fallback: User) -> User | None:
    if value is None or not value.strip():
        return fallback
    candidate = value.strip()
    for field in ('username', 'full_name', 'email'):
        user = db.query(User).filter(getattr(User, field) == candidate).first()
        if user:
            return user
    for field in ('username', 'full_name', 'email'):
        user = db.query(User).filter(getattr(User, field).ilike(candidate)).first()
        if user:
            return user
    return None


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

    threat_catalogue = [
        ('Power or utility outage', 'Environmental', 'Loss of electricity, cooling, water or telecommunications.', 'External utility failure; local equipment fault', 'Single feed; untested backup power', 3),
        ('Cyberattack or ransomware', 'Cybersecurity', 'Malicious compromise causing loss of availability or data.', 'Phishing; exposed service; vulnerable software', 'Weak segmentation; untested restore; obsolete protection', 4),
        ('Critical supplier failure', 'Supplier', 'Failure or prolonged unavailability of an essential third party.', 'Supplier outage; insolvency; geopolitical disruption', 'Single supplier; weak SLA; no exit plan', 3),
        ('IT infrastructure failure', 'Technical', 'Failure of servers, storage, network or cloud services.', 'Hardware fault; capacity saturation; change failure', 'No redundancy; weak monitoring; configuration drift', 3),
        ('Loss of key personnel', 'Human', 'Unavailability of people holding critical knowledge or authority.', 'Illness; strike; resignation; access disruption', 'No deputy; undocumented procedures; skill concentration', 2),
        ('Site inaccessibility', 'Environmental', 'A critical site cannot be occupied or reached.', 'Fire; flood; civil disturbance; transport disruption', 'Single site; no remote-work capability; weak evacuation plan', 2),
        ('Data corruption or loss', 'Technical', 'Critical information becomes unavailable, incorrect or unrecoverable.', 'Human error; software defect; malicious deletion', 'Untested backups; excessive privileges; no versioning', 3),
    ]
    for name, category, description, causes, vulnerabilities, probability in threat_catalogue:
        if not db.query(ThreatScenario).filter(ThreatScenario.name == name).first():
            db.add(ThreatScenario(
                name=name,
                category=category,
                description=description,
                common_causes=causes,
                common_vulnerabilities=vulnerabilities,
                default_probability=probability,
            ))
    db.commit()

    seed_demo_default = 'false' if APP_ENV == 'production' else 'true'
    seed_demo = os.getenv('SEED_DEMO_DATA', seed_demo_default).strip().lower() in {'1', 'true', 'yes', 'on'}
    if not seed_demo:
        bootstrap_username = os.getenv('BOOTSTRAP_ADMIN_USERNAME', '').strip()
        bootstrap_password = os.getenv('BOOTSTRAP_ADMIN_PASSWORD', '')
        bootstrap_email = os.getenv('BOOTSTRAP_ADMIN_EMAIL', '').strip()
        if bootstrap_username and bootstrap_password and bootstrap_email:
            if not db.query(User).filter(User.username == bootstrap_username).first():
                db.add(User(
                    username=bootstrap_username,
                    email=bootstrap_email,
                    full_name=os.getenv('BOOTSTRAP_ADMIN_FULL_NAME', 'ContinuityOS Administrator').strip(),
                    password_hash=hash_password(bootstrap_password),
                    role_id=admin_role.id,
                    department_id=None,
                    is_active=True,
                    must_change_password=True,
                ))
                db.commit()
        elif APP_ENV == 'production' and db.query(User).count() == 0:
            raise RuntimeError('Production requires BOOTSTRAP_ADMIN_USERNAME, BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD')
        return

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
            must_change_password=False,
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
            must_change_password=False,
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
            must_change_password=False,
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
        'id': assessment.id,
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
        'current_assessment_type': latest.assessment_type if latest else None,
        'inherent_assessment': _serialize_assessment(inherent),
        'residual_assessment': _serialize_assessment(residual),
        'assessment_history': [_serialize_assessment(item) for item in reversed(assessments)],
        'threat': risk.threat,
        'vulnerability': risk.vulnerability,
        'consequence': risk.consequence,
        'source': risk.source,
        'causes': risk.causes,
        'existing_measures': risk.existing_measures,
        'review_date': risk.review_date.isoformat() if risk.review_date else None,
        'review_overdue': bool(risk.review_date and risk.review_date < _utcnow() and risk.status not in {'Closed', 'Archived'}),
        'status': risk.status,
        'acceptance_justification': risk.acceptance_justification,
        'identified_by': risk.identified_by.full_name if risk.identified_by else 'System',
        'created_at': risk.created_at.isoformat() if risk.created_at else None,
        'updated_at': risk.updated_at.isoformat() if risk.updated_at else None,
        'treatment_count': len(risk.treatments),
        'control_count': len(risk.controls),
        'indicator_count': len(risk.indicators),
        'incident_count': len(risk.incidents),
        'attachment_count': len(risk.attachments),
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
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    rate_key = _login_key(request, payload.username)
    if _login_is_limited(rate_key):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail='Too many failed sign-in attempts. Try again later.')
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        _record_login_failure(rate_key)
        db.add(AuditLog(
            user_id=user.id if user else None,
            action='login_failed',
            details=f'Failed sign-in for username {payload.username[:80]}',
        ))
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid credentials')
    _clear_login_failures(rate_key)
    token = create_access_token(user.username)
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=_cookie_secure(),
        samesite='lax',
        path='/',
    )
    _audit(db, user, 'login_succeeded', 'User signed in')
    db.commit()
    return {
        'access_token': token,
        'token_type': 'bearer',
        'user': {
            'id': user.id,
            'username': user.username,
            'full_name': user.full_name,
            'email': user.email,
            'role': user.role.name if user.role else 'Unknown',
            'must_change_password': user.must_change_password,
        },
    }


@app.post('/api/auth/logout')
def logout(response: Response) -> dict:
    response.delete_cookie(key=AUTH_COOKIE_NAME, path='/', secure=_cookie_secure(), samesite='lax')
    return {'logged_out': True}


@app.post('/api/auth/change-password')
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=422, detail='Current password is incorrect')
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=422, detail='New password must be different')
    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    _audit(db, current_user, 'password_changed', 'User changed their password')
    db.commit()
    return {'changed': True}


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
        'must_change_password': current_user.must_change_password,
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
    review_due = sum(
        bool(risk.review_date and risk.review_date < now and risk.status not in {'Closed', 'Archived'})
        for risk in risks
    )
    control_tests_due = sum(
        bool(control.next_test_date and control.next_test_date < now and control.status != 'Inactive')
        for risk in risks
        for control in risk.controls
    )
    critical_indicators = sum(
        bool(
            (indicator.direction == 'Above is bad' and indicator.current_value >= indicator.critical_threshold)
            or (indicator.direction == 'Below is bad' and indicator.current_value <= indicator.critical_threshold)
        )
        for risk in risks
        for indicator in risk.indicators
    )
    visible_department_ids = {risk.department_id for risk in risks}
    if current_user.role.name != 'Department Manager':
        visible_department_ids = {department.id for department in db.query(Department).all()}
    open_incidents = db.query(Incident).filter(
        Incident.department_id.in_(visible_department_ids),
        Incident.status.in_(['Open', 'Investigating']),
    ).count() if visible_department_ids else 0

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
        'risk_reviews_due': review_due,
        'control_tests_due': control_tests_due,
        'critical_indicators': critical_indicators,
        'open_incidents': open_incidents,
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
            'activity': resource.activity.name if resource.activity else '',
            'department_id': resource.activity.department_id if resource.activity else None,
            'department': resource.activity.department.name if resource.activity and resource.activity.department else '',
        }
        for resource in db.query(Resource).join(Activity).all()
        if can_access_department(current_user, resource.activity.department_id)
    ]


@app.get('/api/risks')
def list_risks(
    query: str | None = Query(default=None, max_length=160),
    level: str | None = Query(default=None),
    category: str | None = Query(default=None),
    department_id: int | None = Query(default=None),
    risk_status: str | None = Query(default=None, alias='status'),
    limit: int = Query(default=500, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    risks = db.query(Risk).order_by(Risk.created_at.desc()).all()
    rows = [
        _serialize_risk(risk)
        for risk in risks
        if can_access_department(current_user, risk.department_id)
    ]
    if query:
        term = query.strip().lower()
        rows = [row for row in rows if term in f"{row['code']} {row['name']} {row['description']} {row['department']}".lower()]
    if level:
        rows = [row for row in rows if row['level'] == level]
    if category:
        rows = [row for row in rows if row['category'] == category]
    if department_id is not None:
        rows = [row for row in rows if row['department_id'] == department_id]
    if risk_status:
        rows = [row for row in rows if row['status'] == risk_status]
    return rows[offset:offset + limit]


@app.get('/api/risks/{risk_id}')
def get_risk(
    risk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> dict:
    return _serialize_risk(_get_risk(db, risk_id, current_user))


@app.post('/api/risks/import', status_code=status.HTTP_201_CREATED)
async def import_risks(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:create')),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='A spreadsheet file is required')

    file_bytes = await file.read()
    if len(file_bytes) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail='Import files are limited to 5 MB')
    rows = _read_risk_import_rows(file_bytes, file.filename)
    if not rows:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='The uploaded file does not contain any rows to import')

    created_ids: list[int] = []
    errors: list[str] = []

    for row_number, row in enumerate(rows, start=2):
        normalized = { _normalize_column_name(key): _normalize_import_value(value) for key, value in row.items() }

        def pick(*keys: str) -> str:
            for key in keys:
                value = normalized.get(key)
                if value is not None and value != '':
                    return value
            return ''

        code = pick('code', 'risk_id', 'risk_code', 'risk_number', 'identifier')
        title = pick('name', 'risk_name', 'risk_title', 'title')
        department_name = pick('department', 'department_name', 'team')
        category = pick('category', 'risk_category')
        description = pick('description', 'risk_description', 'details', 'description_of_risk')
        probability = pick('probability', 'likelihood', 'probability_score', 'risk_probability')
        impact = pick('impact', 'impact_score', 'risk_impact')
        owner_name = pick('owner', 'owner_name', 'assigned_to', 'risk_owner')
        threat = pick('threat')
        vulnerability = pick('vulnerability')
        consequence = pick('consequence', 'potential_consequences', 'business_impact')
        activity_name = pick('activity', 'activity_name', 'process', 'critical_activity')
        source = pick('source', 'risk_source', 'origin')
        causes = pick('causes', 'root_causes', 'cause')
        existing_measures = pick('existing_measures', 'existing_controls', 'current_controls')

        if not code or not title or not department_name or not category or not description:
            errors.append(f'Row {row_number}: code, title, department, category, and description are required')
            continue

        department = db.query(Department).filter(Department.name.ilike(department_name)).first()
        if department is None:
            errors.append(f'Row {row_number}: department "{department_name}" was not found')
            continue
        if not can_access_department(current_user, department.id):
            errors.append(f'Row {row_number}: you cannot import risks into department "{department.name}"')
            continue

        try:
            probability_value = int(probability) if probability else 3
            impact_value = int(impact) if impact else 3
        except ValueError:
            errors.append(f'Row {row_number}: probability and impact must be numeric values between 1 and 5')
            continue

        if not 1 <= probability_value <= 5 or not 1 <= impact_value <= 5:
            errors.append(f'Row {row_number}: probability and impact must be between 1 and 5')
            continue

        if db.query(Risk).filter(Risk.code == code).first():
            errors.append(f'Row {row_number}: risk code "{code}" already exists')
            continue

        activity = None
        if activity_name:
            activity = db.query(Activity).filter(
                Activity.name.ilike(activity_name),
                Activity.department_id == department.id,
            ).first()
            if activity is None:
                errors.append(f'Row {row_number}: activity "{activity_name}" was not found for department "{department.name}"')
                continue

        owner = current_user
        if owner_name:
            owner = _find_optional_user(db, owner_name, current_user)
        if owner is None or not owner.is_active:
            errors.append(f'Row {row_number}: owner "{owner_name or current_user.full_name}" was not found or is inactive')
            continue
        if not can_access_department(current_user, owner.department_id or department.id):
            errors.append(f'Row {row_number}: selected owner is outside your accessible department scope')
            continue

        risk = Risk(
            code=code,
            name=title,
            description=description,
            category=category,
            department_id=department.id,
            activity_id=activity.id if activity else None,
            threat=threat or None,
            vulnerability=vulnerability or None,
            consequence=consequence or None,
            source=source or None,
            causes=causes or None,
            existing_measures=existing_measures or None,
            owner_id=owner.id,
            identified_by_id=current_user.id,
        )
        db.add(risk)
        db.flush()

        score = probability_value * impact_value
        assessment = RiskAssessment(
            risk_id=risk.id,
            probability=probability_value,
            impact=impact_value,
            score=score,
            level=_risk_level(score),
            assessment_type='Inherent',
            comments='Imported from spreadsheet',
        )
        db.add(assessment)
        _audit(db, current_user, 'risk_imported', f'Risk {risk.code} imported from spreadsheet', risk.id)
        created_ids.append(risk.id)

    db.commit()
    return {
        'created': len(created_ids),
        'total_rows': len(rows),
        'errors': errors,
        'created_ids': created_ids,
    }


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
    if owner.department_id is not None and not can_access_department(current_user, owner.department_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Risk owner is outside your department scope')

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
        source=payload.source,
        causes=payload.causes,
        existing_measures=payload.existing_measures,
        review_date=_normalize_datetime(payload.review_date),
        owner_id=owner.id,
        identified_by_id=current_user.id,
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


@app.patch('/api/risks/{risk_id}')
def update_risk(
    risk_id: int,
    payload: RiskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:create')),
) -> dict:
    risk = _get_risk(db, risk_id, current_user)
    updates = payload.model_dump(exclude_unset=True)
    target_department_id = updates.get('department_id', risk.department_id)
    if not can_access_department(current_user, target_department_id):
        raise HTTPException(status_code=403, detail='Risk is outside your department scope')
    if 'department_id' in updates and not db.query(Department).filter(Department.id == target_department_id).first():
        raise HTTPException(status_code=422, detail='Department does not exist')
    if 'code' in updates and db.query(Risk).filter(Risk.code == updates['code'], Risk.id != risk.id).first():
        raise HTTPException(status_code=409, detail='Risk code already exists')
    if 'activity_id' in updates and updates['activity_id'] is not None:
        activity = db.query(Activity).filter(Activity.id == updates['activity_id']).first()
        if activity is None or activity.department_id != target_department_id:
            raise HTTPException(status_code=422, detail='Activity must belong to the selected department')
    if 'owner_id' in updates and updates['owner_id'] is not None:
        owner = db.query(User).filter(User.id == updates['owner_id'], User.is_active.is_(True)).first()
        if owner is None:
            raise HTTPException(status_code=422, detail='Risk owner does not exist or is inactive')
        if owner.department_id is not None and not can_access_department(current_user, owner.department_id):
            raise HTTPException(status_code=422, detail='Risk owner is outside your department scope')
    if 'review_date' in updates:
        updates['review_date'] = _normalize_datetime(updates['review_date'])
    next_status = updates.get('status', risk.status)
    justification = updates.get('acceptance_justification', risk.acceptance_justification)
    if next_status == 'Accepted' and (not justification or len(justification.strip()) < 10):
        raise HTTPException(status_code=422, detail='Accepted risks require a justification of at least 10 characters')
    changed_fields = sorted(updates)
    for field, value in updates.items():
        setattr(risk, field, value)
    risk.updated_at = _utcnow()
    _audit(db, current_user, 'risk_updated', f"Risk {risk.code} updated: {', '.join(changed_fields)}", risk.id)
    db.commit()
    db.refresh(risk)
    return _serialize_risk(risk)


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
    if payload.decision == 'approve':
        treatment.risk.status = 'Under treatment'
        treatment.risk.updated_at = _utcnow()
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
        treatment.risk.status = 'Validated'
        treatment.risk.updated_at = _utcnow()

    if payload.status == 'In progress':
        treatment.risk.status = 'Under treatment'
        treatment.risk.updated_at = _utcnow()

    if payload.status == 'Cancelled':
        other_active = any(
            item.id != treatment.id and item.status in {'Approved', 'In progress'}
            for item in treatment.risk.treatments
        )
        if not other_active:
            treatment.risk.status = 'Validated'
            treatment.risk.updated_at = _utcnow()

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
            'must_change_password': user.must_change_password,
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
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    _audit(db, current_user, 'user_created', f'User {user.username} created with role {role.name}')
    db.commit()
    return {'id': user.id, 'username': user.username, 'role': role.name}


@app.post('/api/users/{user_id}/reset-password')
def reset_user_password(
    user_id: int,
    payload: PasswordReset,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('users:manage')),
) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail='User not found')
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = True
    _audit(db, current_user, 'user_password_reset', f'Password reset for {user.username}')
    db.commit()
    return {'id': user.id, 'must_change_password': True}


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
    risk_id: int | None = Query(default=None),
    action: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('audit:read')),
) -> list[dict]:
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if risk_id is not None:
        risk = _get_risk(db, risk_id, current_user)
        query = query.filter(AuditLog.risk_id == risk.id)
    if action:
        query = query.filter(AuditLog.action == action)
    logs = query.limit(limit).all()
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
) -> StreamingResponse:
    risks = [
        risk
        for risk in db.query(Risk).order_by(Risk.code).all()
        if can_access_department(current_user, risk.department_id)
    ]

    def spreadsheet_value(value: object) -> object:
        if isinstance(value, str) and value.startswith(('=', '+', '-', '@')):
            return f"'{value}"
        return value

    if format == 'pdf':
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

        output = io.BytesIO()
        document = SimpleDocTemplate(output, pagesize=landscape(letter))
        rows = [['Code', 'Risk', 'Department', 'Status', 'Inherent', 'Residual', 'Current', 'Level']]
        for risk in risks:
            assessments = sorted(risk.assessments, key=lambda item: (item.assessment_date or datetime.min, item.id))
            current = assessments[-1] if assessments else None
            inherent = next((item for item in reversed(assessments) if item.assessment_type == 'Inherent'), None)
            residual = next((item for item in reversed(assessments) if item.assessment_type == 'Residual'), None)
            rows.append([
                risk.code,
                risk.name,
                risk.department.name if risk.department else '',
                risk.status,
                str(inherent.score) if inherent else '—',
                str(residual.score) if residual else '—',
                str(current.score) if current else '—',
                current.level if current else 'Unassessed',
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
        output.seek(0)
        return StreamingResponse(
            output,
            media_type='application/pdf',
            headers={'Content-Disposition': 'attachment; filename="smca-risk-report.pdf"'},
        )

    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = 'Risk Register'
    sheet.append([
        'Code', 'Risk', 'Department', 'Activity', 'Category', 'Status', 'Owner',
        'Inherent score', 'Residual score', 'Current score', 'Level', 'Review date',
        'Controls', 'Treatments', 'Incidents', 'Indicators',
    ])
    for risk in risks:
        assessments = sorted(risk.assessments, key=lambda item: (item.assessment_date or datetime.min, item.id))
        current = assessments[-1] if assessments else None
        inherent = next((item for item in reversed(assessments) if item.assessment_type == 'Inherent'), None)
        residual = next((item for item in reversed(assessments) if item.assessment_type == 'Residual'), None)
        values = [
            risk.code, risk.name, risk.department.name if risk.department else '',
            risk.activity.name if risk.activity else '', risk.category, risk.status,
            risk.owner.full_name if risk.owner else 'Unassigned',
            inherent.score if inherent else None, residual.score if residual else None,
            current.score if current else None, current.level if current else 'Unassessed',
            risk.review_date.isoformat() if risk.review_date else None,
            len(risk.controls), len(risk.treatments), len(risk.incidents), len(risk.indicators),
        ]
        sheet.append([spreadsheet_value(value) for value in values])
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': 'attachment; filename="smca-risk-report.xlsx"'},
    )
