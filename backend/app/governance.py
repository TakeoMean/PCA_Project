from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import can_access_department, require_permission
from app.database import get_db
from app.models import (
    Activity,
    ActivityDependency,
    AuditLog,
    BusinessImpactAnalysis,
    Incident,
    Risk,
    RiskAttachment,
    RiskControl,
    RiskIndicator,
    RiskTreatment,
    ThreatScenario,
    TreatmentAction,
    User,
)
from app.schemas import (
    ActivityDependencyCreate,
    IncidentCreate,
    IncidentUpdate,
    RiskIndicatorCreate,
    RiskIndicatorUpdate,
    ThreatScenarioCreate,
)


router = APIRouter(prefix='/api', tags=['SMCA governance'])
MAX_ATTACHMENT_BYTES = int(os.getenv('MAX_ATTACHMENT_BYTES', str(10 * 1024 * 1024)))
ALLOWED_ATTACHMENT_EXTENSIONS = {
    '.pdf', '.png', '.jpg', '.jpeg', '.webp', '.txt', '.csv', '.xlsx', '.docx', '.pptx',
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _audit(db: Session, user: User, action: str, details: str, risk_id: int | None = None) -> None:
    db.add(AuditLog(user_id=user.id, risk_id=risk_id, action=action, details=details))


def _visible_risk(db: Session, risk_id: int, user: User) -> Risk:
    risk = db.query(Risk).filter(Risk.id == risk_id).first()
    if risk is None or not can_access_department(user, risk.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Risk not found')
    return risk


def _serialize_dependency(item: ActivityDependency) -> dict:
    return {
        'id': item.id,
        'source_activity_id': item.source_activity_id,
        'source_activity': item.source_activity.name,
        'source_department': item.source_activity.department.name if item.source_activity.department else '',
        'target_activity_id': item.target_activity_id,
        'target_activity': item.target_activity.name,
        'target_department': item.target_activity.department.name if item.target_activity.department else '',
        'dependency_type': item.dependency_type,
        'criticality': item.criticality,
        'description': item.description,
        'recovery_order': item.recovery_order,
    }


def _serialize_incident(item: Incident) -> dict:
    return {
        'id': item.id,
        'code': item.code,
        'title': item.title,
        'description': item.description,
        'severity': item.severity,
        'status': item.status,
        'occurred_at': item.occurred_at.isoformat() if item.occurred_at else None,
        'resolved_at': item.resolved_at.isoformat() if item.resolved_at else None,
        'department_id': item.department_id,
        'department': item.department.name if item.department else '',
        'risk_id': item.risk_id,
        'risk_code': item.risk.code if item.risk else None,
        'risk_name': item.risk.name if item.risk else None,
        'impact': item.impact,
        'lessons_learned': item.lessons_learned,
        'created_by': item.created_by.full_name if item.created_by else 'System',
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    }


def _indicator_status(item: RiskIndicator) -> str:
    if item.direction == 'Below is bad':
        if item.current_value <= item.critical_threshold:
            return 'Critical'
        if item.current_value <= item.warning_threshold:
            return 'Warning'
        return 'Normal'
    if item.current_value >= item.critical_threshold:
        return 'Critical'
    if item.current_value >= item.warning_threshold:
        return 'Warning'
    return 'Normal'


def _validate_indicator_thresholds(direction: str, warning: float, critical: float) -> None:
    if direction == 'Above is bad' and critical < warning:
        raise HTTPException(status_code=422, detail='Critical threshold must be greater than or equal to warning threshold')
    if direction == 'Below is bad' and critical > warning:
        raise HTTPException(status_code=422, detail='Critical threshold must be lower than or equal to warning threshold')


def _serialize_indicator(item: RiskIndicator) -> dict:
    return {
        'id': item.id,
        'risk_id': item.risk_id,
        'risk_code': item.risk.code,
        'risk_name': item.risk.name,
        'name': item.name,
        'unit': item.unit,
        'direction': item.direction,
        'warning_threshold': item.warning_threshold,
        'critical_threshold': item.critical_threshold,
        'current_value': item.current_value,
        'frequency': item.frequency,
        'owner_id': item.owner_id,
        'owner': item.owner.full_name if item.owner else 'Unassigned',
        'status': _indicator_status(item),
        'last_updated_at': item.last_updated_at.isoformat() if item.last_updated_at else None,
    }


def _storage_root() -> Path:
    configured = os.getenv('STORAGE_DIR')
    root = Path(configured) if configured else Path(__file__).resolve().parent.parent / 'storage'
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


@router.get('/activity-dependencies')
def list_dependencies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    items = db.query(ActivityDependency).order_by(ActivityDependency.criticality.desc()).all()
    return [
        _serialize_dependency(item)
        for item in items
        if can_access_department(current_user, item.source_activity.department_id)
        or can_access_department(current_user, item.target_activity.department_id)
    ]


@router.post('/activity-dependencies', status_code=status.HTTP_201_CREATED)
def create_dependency(
    payload: ActivityDependencyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('bia:manage')),
) -> dict:
    if payload.source_activity_id == payload.target_activity_id:
        raise HTTPException(status_code=422, detail='An activity cannot depend on itself')
    source = db.query(Activity).filter(Activity.id == payload.source_activity_id).first()
    target = db.query(Activity).filter(Activity.id == payload.target_activity_id).first()
    if source is None or target is None:
        raise HTTPException(status_code=422, detail='Both activities must exist')
    if not can_access_department(current_user, source.department_id) or not can_access_department(current_user, target.department_id):
        raise HTTPException(status_code=403, detail='Dependency is outside your department scope')
    duplicate = db.query(ActivityDependency).filter(
        ActivityDependency.source_activity_id == source.id,
        ActivityDependency.target_activity_id == target.id,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail='This dependency already exists')
    item = ActivityDependency(**payload.model_dump())
    db.add(item)
    db.flush()
    _audit(db, current_user, 'activity_dependency_created', f'{source.name} depends on {target.name}')
    db.commit()
    db.refresh(item)
    return _serialize_dependency(item)


@router.delete('/activity-dependencies/{dependency_id}')
def delete_dependency(
    dependency_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('bia:manage')),
) -> dict:
    item = db.query(ActivityDependency).filter(ActivityDependency.id == dependency_id).first()
    if item is None or not can_access_department(current_user, item.source_activity.department_id):
        raise HTTPException(status_code=404, detail='Dependency not found')
    details = f'{item.source_activity.name} no longer depends on {item.target_activity.name}'
    db.delete(item)
    _audit(db, current_user, 'activity_dependency_deleted', details)
    db.commit()
    return {'deleted': True}


@router.get('/threat-library')
def list_threats(
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    query = db.query(ThreatScenario).order_by(ThreatScenario.category, ThreatScenario.name)
    if category:
        query = query.filter(ThreatScenario.category == category)
    return [
        {
            'id': item.id,
            'name': item.name,
            'category': item.category,
            'description': item.description,
            'common_causes': item.common_causes,
            'common_vulnerabilities': item.common_vulnerabilities,
            'default_probability': item.default_probability,
        }
        for item in query.all()
    ]


@router.post('/threat-library', status_code=status.HTTP_201_CREATED)
def create_threat(
    payload: ThreatScenarioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('departments:write')),
) -> dict:
    if db.query(ThreatScenario).filter(ThreatScenario.name == payload.name).first():
        raise HTTPException(status_code=409, detail='Threat scenario already exists')
    item = ThreatScenario(**payload.model_dump())
    db.add(item)
    db.flush()
    _audit(db, current_user, 'threat_scenario_created', f'Threat scenario created: {item.name}')
    db.commit()
    return {'id': item.id, 'name': item.name}


@router.get('/incidents')
def list_incidents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    items = db.query(Incident).order_by(Incident.occurred_at.desc(), Incident.id.desc()).all()
    return [_serialize_incident(item) for item in items if can_access_department(current_user, item.department_id)]


@router.post('/incidents', status_code=status.HTTP_201_CREATED)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('incidents:manage')),
) -> dict:
    if db.query(Incident).filter(Incident.code == payload.code).first():
        raise HTTPException(status_code=409, detail='Incident code already exists')
    if not can_access_department(current_user, payload.department_id):
        raise HTTPException(status_code=403, detail='Incident is outside your department scope')
    if payload.risk_id is not None:
        risk = _visible_risk(db, payload.risk_id, current_user)
        if risk.department_id != payload.department_id:
            raise HTTPException(status_code=422, detail='Incident and risk must belong to the same department')
    values = payload.model_dump()
    values['occurred_at'] = _normalize_datetime(values['occurred_at'])
    item = Incident(created_by_id=current_user.id, **values)
    if item.status in {'Resolved', 'Closed'}:
        item.resolved_at = _utcnow()
    db.add(item)
    db.flush()
    _audit(db, current_user, 'incident_created', f'Incident {item.code} recorded', item.risk_id)
    db.commit()
    db.refresh(item)
    return _serialize_incident(item)


@router.patch('/incidents/{incident_id}')
def update_incident(
    incident_id: int,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('incidents:manage')),
) -> dict:
    item = db.query(Incident).filter(Incident.id == incident_id).first()
    if item is None or not can_access_department(current_user, item.department_id):
        raise HTTPException(status_code=404, detail='Incident not found')
    updates = payload.model_dump(exclude_unset=True)
    if updates.get('risk_id') is not None:
        risk = _visible_risk(db, updates['risk_id'], current_user)
        if risk.department_id != item.department_id:
            raise HTTPException(status_code=422, detail='Incident and risk must belong to the same department')
    for date_field in ('occurred_at', 'resolved_at'):
        if date_field in updates:
            updates[date_field] = _normalize_datetime(updates[date_field])
    for field, value in updates.items():
        setattr(item, field, value)
    if item.status in {'Resolved', 'Closed'} and item.resolved_at is None:
        item.resolved_at = _utcnow()
    if item.status in {'Open', 'Investigating'} and 'resolved_at' not in updates:
        item.resolved_at = None
    item.updated_at = _utcnow()
    _audit(db, current_user, 'incident_updated', f'Incident {item.code} updated', item.risk_id)
    db.commit()
    db.refresh(item)
    return _serialize_incident(item)


@router.get('/risk-indicators')
def list_indicators(
    risk_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    query = db.query(RiskIndicator).join(Risk).order_by(RiskIndicator.last_updated_at.desc())
    if risk_id is not None:
        query = query.filter(RiskIndicator.risk_id == risk_id)
    return [
        _serialize_indicator(item)
        for item in query.all()
        if can_access_department(current_user, item.risk.department_id)
    ]


@router.post('/risks/{risk_id}/indicators', status_code=status.HTTP_201_CREATED)
def create_indicator(
    risk_id: int,
    payload: RiskIndicatorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('indicators:manage')),
) -> dict:
    risk = _visible_risk(db, risk_id, current_user)
    _validate_indicator_thresholds(payload.direction, payload.warning_threshold, payload.critical_threshold)
    if payload.owner_id is not None:
        owner = db.query(User).filter(User.id == payload.owner_id, User.is_active.is_(True)).first()
        if owner is None:
            raise HTTPException(status_code=422, detail='Indicator owner does not exist or is inactive')
        if owner.department_id is not None and not can_access_department(current_user, owner.department_id):
            raise HTTPException(status_code=422, detail='Indicator owner is outside your department scope')
    item = RiskIndicator(risk_id=risk.id, **payload.model_dump())
    db.add(item)
    db.flush()
    _audit(db, current_user, 'risk_indicator_created', f'Indicator added: {item.name}', risk.id)
    db.commit()
    db.refresh(item)
    return _serialize_indicator(item)


@router.patch('/risk-indicators/{indicator_id}')
def update_indicator(
    indicator_id: int,
    payload: RiskIndicatorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('indicators:manage')),
) -> dict:
    item = db.query(RiskIndicator).filter(RiskIndicator.id == indicator_id).first()
    if item is None or not can_access_department(current_user, item.risk.department_id):
        raise HTTPException(status_code=404, detail='Risk indicator not found')
    updates = payload.model_dump(exclude_unset=True)
    direction = updates.get('direction', item.direction)
    warning = updates.get('warning_threshold', item.warning_threshold)
    critical = updates.get('critical_threshold', item.critical_threshold)
    _validate_indicator_thresholds(direction, warning, critical)
    if updates.get('owner_id') is not None:
        owner = db.query(User).filter(User.id == updates['owner_id'], User.is_active.is_(True)).first()
        if owner is None:
            raise HTTPException(status_code=422, detail='Indicator owner does not exist or is inactive')
    for field, value in updates.items():
        setattr(item, field, value)
    item.last_updated_at = _utcnow()
    _audit(db, current_user, 'risk_indicator_updated', f'Indicator updated: {item.name}', item.risk_id)
    db.commit()
    db.refresh(item)
    return _serialize_indicator(item)


@router.delete('/risk-indicators/{indicator_id}')
def delete_indicator(
    indicator_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('indicators:manage')),
) -> dict:
    item = db.query(RiskIndicator).filter(RiskIndicator.id == indicator_id).first()
    if item is None or not can_access_department(current_user, item.risk.department_id):
        raise HTTPException(status_code=404, detail='Risk indicator not found')
    risk_id = item.risk_id
    name = item.name
    db.delete(item)
    _audit(db, current_user, 'risk_indicator_deleted', f'Indicator deleted: {name}', risk_id)
    db.commit()
    return {'deleted': True}


@router.get('/risks/{risk_id}/attachments')
def list_attachments(
    risk_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    risk = _visible_risk(db, risk_id, current_user)
    return [
        {
            'id': item.id,
            'original_name': item.original_name,
            'content_type': item.content_type,
            'size_bytes': item.size_bytes,
            'description': item.description,
            'uploaded_by': item.uploaded_by.full_name if item.uploaded_by else 'System',
            'created_at': item.created_at.isoformat() if item.created_at else None,
        }
        for item in sorted(risk.attachments, key=lambda entry: entry.created_at or datetime.min, reverse=True)
    ]


@router.post('/risks/{risk_id}/attachments', status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    risk_id: int,
    file: UploadFile = File(...),
    description: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:create')),
) -> dict:
    risk = _visible_risk(db, risk_id, current_user)
    original_name = Path(file.filename or '').name
    extension = Path(original_name).suffix.lower()
    if not original_name or extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise HTTPException(status_code=415, detail='Unsupported attachment type')
    content = await file.read(MAX_ATTACHMENT_BYTES + 1)
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail='Attachment is too large')
    storage_name = f'{uuid4().hex}{extension}'
    destination = (_storage_root() / storage_name).resolve()
    if destination.parent != _storage_root():
        raise HTTPException(status_code=400, detail='Invalid attachment path')
    destination.write_bytes(content)
    item = RiskAttachment(
        risk_id=risk.id,
        uploaded_by_id=current_user.id,
        original_name=original_name,
        storage_name=storage_name,
        content_type=file.content_type,
        size_bytes=len(content),
        description=description.strip() if description else None,
    )
    db.add(item)
    db.flush()
    _audit(db, current_user, 'risk_attachment_uploaded', f'Attachment uploaded: {original_name}', risk.id)
    db.commit()
    return {'id': item.id, 'original_name': item.original_name, 'size_bytes': item.size_bytes}


@router.get('/risk-attachments/{attachment_id}/download')
def download_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> FileResponse:
    item = db.query(RiskAttachment).filter(RiskAttachment.id == attachment_id).first()
    if item is None or not can_access_department(current_user, item.risk.department_id):
        raise HTTPException(status_code=404, detail='Attachment not found')
    path = (_storage_root() / item.storage_name).resolve()
    if path.parent != _storage_root() or not path.is_file():
        raise HTTPException(status_code=404, detail='Attachment file not found')
    return FileResponse(path, media_type=item.content_type or 'application/octet-stream', filename=item.original_name)


@router.delete('/risk-attachments/{attachment_id}')
def delete_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:create')),
) -> dict:
    item = db.query(RiskAttachment).filter(RiskAttachment.id == attachment_id).first()
    if item is None or not can_access_department(current_user, item.risk.department_id):
        raise HTTPException(status_code=404, detail='Attachment not found')
    path = (_storage_root() / item.storage_name).resolve()
    risk_id = item.risk_id
    original_name = item.original_name
    db.delete(item)
    _audit(db, current_user, 'risk_attachment_deleted', f'Attachment deleted: {original_name}', risk_id)
    db.commit()
    if path.parent == _storage_root() and path.is_file():
        path.unlink()
    return {'deleted': True}


@router.get('/alerts')
def list_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    now = _utcnow()
    upcoming = now + timedelta(days=30)
    alerts: list[dict] = []

    risks = [risk for risk in db.query(Risk).all() if can_access_department(current_user, risk.department_id)]
    for risk in risks:
        if risk.review_date and risk.status not in {'Closed', 'Archived'} and risk.review_date <= upcoming:
            overdue = risk.review_date < now
            alerts.append({
                'type': 'risk_review',
                'severity': 'Critical' if overdue else 'Warning',
                'title': f'Revue du risque {risk.code}',
                'detail': 'La revue du risque est en retard.' if overdue else 'La revue du risque est prévue dans les 30 jours.',
                'due_at': risk.review_date.isoformat(),
                'risk_id': risk.id,
            })
        for treatment in risk.treatments:
            if treatment.due_date and treatment.status not in {'Completed', 'Cancelled', 'Rejected'} and treatment.due_date < now:
                alerts.append({
                    'type': 'treatment_overdue',
                    'severity': 'Critical',
                    'title': f'Plan en retard pour {risk.code}',
                    'detail': treatment.treatment_plan,
                    'due_at': treatment.due_date.isoformat(),
                    'risk_id': risk.id,
                })
            for action in treatment.actions:
                if action.due_date and action.status != 'Completed' and action.due_date < now:
                    alerts.append({
                        'type': 'action_overdue',
                        'severity': 'Warning',
                        'title': action.title,
                        'detail': f'L’action liée à {risk.code} est en retard.',
                        'due_at': action.due_date.isoformat(),
                        'risk_id': risk.id,
                    })
        for control in risk.controls:
            if control.next_test_date and control.status != 'Inactive' and control.next_test_date <= upcoming:
                overdue = control.next_test_date < now
                alerts.append({
                    'type': 'control_test',
                    'severity': 'Critical' if overdue else 'Warning',
                    'title': f'Tester le contrôle : {control.name}',
                    'detail': f'Le contrôle lié à {risk.code} doit être testé.',
                    'due_at': control.next_test_date.isoformat(),
                    'risk_id': risk.id,
                })

    latest_bia_activity_ids = {
        item.activity_id for item in db.query(BusinessImpactAnalysis).all()
        if can_access_department(current_user, item.activity.department_id)
    }
    for activity in db.query(Activity).all():
        if can_access_department(current_user, activity.department_id) and activity.id not in latest_bia_activity_ids:
            alerts.append({
                'type': 'bia_missing',
                'severity': 'Information',
                'title': f'BIA requise : {activity.name}',
                'detail': 'Cette activité ne possède pas encore d’analyse d’impact.',
                'due_at': None,
                'risk_id': None,
            })

    severity_order = {'Critical': 0, 'Warning': 1, 'Information': 2}
    return sorted(alerts, key=lambda item: (severity_order.get(item['severity'], 9), item['due_at'] or '9999'))
