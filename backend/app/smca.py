from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import can_access_department, get_current_user, require_permission
from app.database import get_db
from app.models import (
    Activity,
    AuditLog,
    BusinessImpactAnalysis,
    Resource,
    Risk,
    RiskControl,
    SmcaScope,
    User,
)
from app.schemas import (
    BusinessImpactCreate,
    RiskControlCreate,
    RiskControlUpdate,
    SmcaScopeUpdate,
)


router = APIRouter(prefix='/api', tags=['SMCA context'])


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _audit(
    db: Session,
    user: User,
    action: str,
    details: str,
    risk_id: int | None = None,
) -> None:
    db.add(AuditLog(user_id=user.id, risk_id=risk_id, action=action, details=details))


def _serialize_scope(scope: SmcaScope | None) -> dict | None:
    if scope is None:
        return None
    return {
        'id': scope.id,
        'name': scope.name,
        'description': scope.description,
        'objectives': scope.objectives,
        'exclusions': scope.exclusions,
        'stakeholders': scope.stakeholders,
        'status': scope.status,
        'review_date': scope.review_date.isoformat() if scope.review_date else None,
        'acceptance_threshold': scope.acceptance_threshold,
        'updated_at': scope.updated_at.isoformat() if scope.updated_at else None,
    }


def _serialize_bia(assessment: BusinessImpactAnalysis, assessment_count: int = 1) -> dict:
    activity = assessment.activity
    return {
        'id': assessment.id,
        'activity_id': assessment.activity_id,
        'activity': activity.name,
        'department_id': activity.department_id,
        'department': activity.department.name if activity.department else '',
        'financial_impact': assessment.financial_impact,
        'operational_impact': assessment.operational_impact,
        'legal_impact': assessment.legal_impact,
        'reputational_impact': assessment.reputational_impact,
        'criticality': assessment.criticality,
        'rto_hours': assessment.rto_hours,
        'rpo_hours': assessment.rpo_hours,
        'mtpd_hours': assessment.mtpd_hours,
        'dependencies': assessment.dependencies,
        'recovery_requirements': assessment.recovery_requirements,
        'comments': assessment.comments,
        'assessed_by': assessment.assessed_by.full_name if assessment.assessed_by else 'System',
        'assessed_at': assessment.assessed_at.isoformat() if assessment.assessed_at else None,
        'assessment_count': assessment_count,
    }


def _serialize_control(control: RiskControl) -> dict:
    return {
        'id': control.id,
        'risk_id': control.risk_id,
        'risk_code': control.risk.code,
        'risk_name': control.risk.name,
        'department_id': control.risk.department_id,
        'name': control.name,
        'description': control.description,
        'control_type': control.control_type,
        'owner_id': control.owner_id,
        'owner': control.owner.full_name if control.owner else 'Unassigned',
        'effectiveness': control.effectiveness,
        'status': control.status,
        'evidence_reference': control.evidence_reference,
        'last_tested_at': control.last_tested_at.isoformat() if control.last_tested_at else None,
        'next_test_date': control.next_test_date.isoformat() if control.next_test_date else None,
        'updated_at': control.updated_at.isoformat() if control.updated_at else None,
    }


@router.get('/smca/scope')
def get_scope(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission('risks:read')),
) -> dict | None:
    return _serialize_scope(db.query(SmcaScope).order_by(SmcaScope.id).first())


@router.put('/smca/scope')
def update_scope(
    payload: SmcaScopeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('departments:write')),
) -> dict:
    scope = db.query(SmcaScope).order_by(SmcaScope.id).first()
    if scope is None:
        scope = SmcaScope(name=payload.name, description=payload.description)
        db.add(scope)
    for field, value in payload.model_dump().items():
        if field == 'review_date':
            value = _normalize_datetime(value)
        setattr(scope, field, value)
    scope.updated_at = _utcnow()
    _audit(db, current_user, 'smca_scope_updated', f'SMCA scope updated: {scope.name}')
    db.commit()
    db.refresh(scope)
    return _serialize_scope(scope)


@router.get('/bia')
def list_bia(
    include_history: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    assessments = db.query(BusinessImpactAnalysis).order_by(
        BusinessImpactAnalysis.assessed_at.desc(),
        BusinessImpactAnalysis.id.desc(),
    ).all()
    visible = [
        item for item in assessments
        if can_access_department(current_user, item.activity.department_id)
    ]
    counts: dict[int, int] = {}
    for item in visible:
        counts[item.activity_id] = counts.get(item.activity_id, 0) + 1
    if include_history:
        return [_serialize_bia(item, counts[item.activity_id]) for item in visible]
    latest: dict[int, BusinessImpactAnalysis] = {}
    for item in visible:
        latest.setdefault(item.activity_id, item)
    return [_serialize_bia(item, counts[item.activity_id]) for item in latest.values()]


@router.post('/activities/{activity_id}/bia', status_code=status.HTTP_201_CREATED)
def create_bia(
    activity_id: int,
    payload: BusinessImpactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('bia:manage')),
) -> dict:
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if activity is None or not can_access_department(current_user, activity.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Activity not found')
    if payload.rto_hours > payload.mtpd_hours:
        raise HTTPException(status_code=422, detail='RTO must be less than or equal to MTPD')
    if payload.rpo_hours > payload.mtpd_hours:
        raise HTTPException(status_code=422, detail='RPO must be less than or equal to MTPD')
    impacts = (
        payload.financial_impact,
        payload.operational_impact,
        payload.legal_impact,
        payload.reputational_impact,
    )
    assessment = BusinessImpactAnalysis(
        activity_id=activity.id,
        assessed_by_id=current_user.id,
        criticality=max(impacts),
        **payload.model_dump(),
    )
    db.add(assessment)
    db.flush()
    _audit(db, current_user, 'bia_assessed', f'BIA completed for {activity.name}')
    db.commit()
    db.refresh(assessment)
    return _serialize_bia(assessment)


@router.get('/risk-controls')
def list_controls(
    risk_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    query = db.query(RiskControl).join(Risk).order_by(RiskControl.updated_at.desc())
    if risk_id is not None:
        query = query.filter(RiskControl.risk_id == risk_id)
    return [
        _serialize_control(control)
        for control in query.all()
        if can_access_department(current_user, control.risk.department_id)
    ]


@router.post('/risks/{risk_id}/controls', status_code=status.HTTP_201_CREATED)
def create_control(
    risk_id: int,
    payload: RiskControlCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('controls:manage')),
) -> dict:
    risk = db.query(Risk).filter(Risk.id == risk_id).first()
    if risk is None or not can_access_department(current_user, risk.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Risk not found')
    owner = None
    if payload.owner_id is not None:
        owner = db.query(User).filter(User.id == payload.owner_id, User.is_active.is_(True)).first()
        if owner is None:
            raise HTTPException(status_code=422, detail='Control owner does not exist or is inactive')
        if owner.department_id is not None and not can_access_department(current_user, owner.department_id):
            raise HTTPException(status_code=422, detail='Control owner is outside your department scope')
    values = payload.model_dump()
    values['last_tested_at'] = _normalize_datetime(values['last_tested_at'])
    values['next_test_date'] = _normalize_datetime(values['next_test_date'])
    control = RiskControl(risk_id=risk.id, **values)
    db.add(control)
    db.flush()
    _audit(db, current_user, 'risk_control_created', f'Control added: {control.name}', risk.id)
    db.commit()
    db.refresh(control)
    return _serialize_control(control)


@router.patch('/risk-controls/{control_id}')
def update_control(
    control_id: int,
    payload: RiskControlUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('controls:manage')),
) -> dict:
    control = db.query(RiskControl).filter(RiskControl.id == control_id).first()
    if control is None or not can_access_department(current_user, control.risk.department_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Risk control not found')
    updates = payload.model_dump(exclude_unset=True)
    if updates.get('owner_id') is not None:
        owner = db.query(User).filter(User.id == updates['owner_id'], User.is_active.is_(True)).first()
        if owner is None:
            raise HTTPException(status_code=422, detail='Control owner does not exist or is inactive')
        if owner.department_id is not None and not can_access_department(current_user, owner.department_id):
            raise HTTPException(status_code=422, detail='Control owner is outside your department scope')
    for date_field in ('last_tested_at', 'next_test_date'):
        if date_field in updates:
            updates[date_field] = _normalize_datetime(updates[date_field])
    for field, value in updates.items():
        setattr(control, field, value)
    control.updated_at = _utcnow()
    _audit(db, current_user, 'risk_control_updated', f'Control updated: {control.name}', control.risk_id)
    db.commit()
    db.refresh(control)
    return _serialize_control(control)


@router.post('/resources', status_code=status.HTTP_201_CREATED)
def create_resource(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('departments:write')),
) -> dict:
    name = payload.get('name')
    category = payload.get('category')
    activity_id = payload.get('activity_id')
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not isinstance(name, str) or not name.strip() or not isinstance(category, str) or not category.strip() or activity is None:
        raise HTTPException(status_code=422, detail='Valid name, category and activity_id are required')
    if not can_access_department(current_user, activity.department_id):
        raise HTTPException(status_code=403, detail='You cannot add resources to this department')
    resource = Resource(
        name=name.strip(),
        category=category.strip(),
        description=payload.get('description'),
        activity_id=activity.id,
    )
    db.add(resource)
    db.flush()
    _audit(db, current_user, 'resource_created', f'Resource created: {resource.name}')
    db.commit()
    return {
        'id': resource.id,
        'name': resource.name,
        'category': resource.category,
        'activity_id': resource.activity_id,
    }


@router.get('/cartography')
def cartography(
    department_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission('risks:read')),
) -> list[dict]:
    risks = db.query(Risk).order_by(Risk.code).all()
    result = []
    for risk in risks:
        if not can_access_department(current_user, risk.department_id):
            continue
        if department_id is not None and risk.department_id != department_id:
            continue
        if category and risk.category != category:
            continue
        assessments = sorted(
            risk.assessments,
            key=lambda item: (item.assessment_date or datetime.min, item.id),
        )
        inherent = next((item for item in reversed(assessments) if item.assessment_type == 'Inherent'), None)
        residual = next((item for item in reversed(assessments) if item.assessment_type == 'Residual'), None)
        current = assessments[-1] if assessments else None
        result.append({
            'id': risk.id,
            'code': risk.code,
            'name': risk.name,
            'category': risk.category,
            'department_id': risk.department_id,
            'department': risk.department.name if risk.department else '',
            'activity': risk.activity.name if risk.activity else '',
            'owner': risk.owner.full_name if risk.owner else 'Unassigned',
            'status': risk.status,
            'review_date': risk.review_date.isoformat() if risk.review_date else None,
            'probability': current.probability if current else None,
            'impact': current.impact if current else None,
            'score': current.score if current else None,
            'level': current.level if current else 'Unassessed',
            'assessment_type': current.assessment_type if current else None,
            'inherent': {
                'probability': inherent.probability,
                'impact': inherent.impact,
                'score': inherent.score,
                'level': inherent.level,
            } if inherent else None,
            'residual': {
                'probability': residual.probability,
                'impact': residual.impact,
                'score': residual.score,
                'level': residual.level,
            } if residual else None,
        })
    return result


@router.get('/methodology')
def methodology(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    scope = db.query(SmcaScope).order_by(SmcaScope.id).first()
    return {
        'formula': 'Probability × Impact',
        'acceptance_threshold': scope.acceptance_threshold if scope else 9,
        'probability_scale': [
            {'score': 1, 'label': 'Rare', 'description': 'Événement exceptionnel avec très peu d’occurrences observées.'},
            {'score': 2, 'label': 'Peu probable', 'description': 'Peut survenir, mais n’est pas attendu dans les conditions normales.'},
            {'score': 3, 'label': 'Possible', 'description': 'S’est déjà produit ou peut raisonnablement se produire.'},
            {'score': 4, 'label': 'Probable', 'description': 'Devrait se produire dans plusieurs circonstances.'},
            {'score': 5, 'label': 'Presque certain', 'description': 'Attendu fréquemment ou déjà récurrent.'},
        ],
        'impact_scale': [
            {'score': 1, 'label': 'Négligeable', 'description': 'Perturbation minimale gérée par les opérations courantes.'},
            {'score': 2, 'label': 'Mineur', 'description': 'Perturbation limitée avec une reprise rapide.'},
            {'score': 3, 'label': 'Modéré', 'description': 'Impact notable sur les opérations ou les parties intéressées.'},
            {'score': 4, 'label': 'Majeur', 'description': 'Interruption sérieuse, perte financière ou exposition réglementaire.'},
            {'score': 5, 'label': 'Sévère', 'description': 'Menace les objectifs critiques, la sécurité ou la survie de l’organisation.'},
        ],
        'levels': [
            {'name': 'Low', 'min': 1, 'max': 4, 'response': 'Accepter et surveiller.'},
            {'name': 'Moderate', 'min': 5, 'max': 9, 'response': 'Surveiller et améliorer les contrôles de manière proportionnée.'},
            {'name': 'High', 'min': 10, 'max': 16, 'response': 'Plan de traitement et supervision managériale requis.'},
            {'name': 'Critical', 'min': 17, 'max': 25, 'response': 'Action immédiate et validation de la direction requises.'},
        ],
        'workflow': [
            'Établir le contexte du SMCA et les activités critiques.',
            'Identifier les menaces, vulnérabilités, causes et conséquences.',
            'Évaluer la probabilité et l’impact inhérents.',
            'Documenter et tester les contrôles existants.',
            'Sélectionner, approuver et exécuter un plan de traitement.',
            'Évaluer le risque résiduel et programmer la prochaine revue.',
        ],
    }
