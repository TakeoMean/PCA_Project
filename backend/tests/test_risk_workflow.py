from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, main, schema_upgrade
from app.models import Base


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    test_engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = test_session()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(database, 'engine', test_engine)
    monkeypatch.setattr(database, 'SessionLocal', test_session)
    monkeypatch.setattr(main, 'engine', test_engine)
    monkeypatch.setattr(main, 'SessionLocal', test_session)
    monkeypatch.setattr(schema_upgrade, 'engine', test_engine)
    main.app.dependency_overrides[database.get_db] = override_get_db

    with TestClient(main.app) as test_client:
        yield test_client

    main.app.dependency_overrides.clear()
    test_engine.dispose()


def login(client: TestClient, username: str = 'admin', password: str = 'admin123') -> dict[str, str]:
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


def test_treatment_requires_review_actions_and_residual_assessment(client: TestClient) -> None:
    headers = login(client)
    risk = client.post(
        '/api/risks',
        headers=headers,
        json={
            'code': 'TEST-001',
            'name': 'Test outage',
            'description': 'A test risk for the treatment workflow.',
            'category': 'Technical',
            'department_id': 1,
            'probability': 4,
            'impact': 5,
        },
    )
    assert risk.status_code == 201
    risk_id = risk.json()['id']

    risk_manager_headers = login(client, 'riskmanager')
    proposed = client.post(
        f'/api/risks/{risk_id}/treatments',
        headers=risk_manager_headers,
        json={
            'strategy': 'Reduce',
            'treatment_plan': 'Deploy a redundant service and test the failover.',
            'expected_result': 'Restore service within the recovery target.',
            'due_date': '2030-01-02T00:00:00Z',
        },
    )
    assert proposed.status_code == 201
    treatment_id = proposed.json()['id']
    assert proposed.json()['status'] == 'Proposed'

    self_review = client.post(
        f'/api/risk-treatments/{treatment_id}/decision',
        headers=risk_manager_headers,
        json={'decision': 'approve', 'comment': 'I approve my own proposal.'},
    )
    assert self_review.status_code == 403

    action_before_approval = client.post(
        f'/api/risk-treatments/{treatment_id}/actions',
        headers=headers,
        json={'title': 'Configure the redundant service'},
    )
    assert action_before_approval.status_code == 409

    approved = client.post(
        f'/api/risk-treatments/{treatment_id}/decision',
        headers=headers,
        json={'decision': 'approve', 'comment': 'Approved for implementation.'},
    )
    assert approved.status_code == 200
    assert approved.json()['status'] == 'Approved'

    started = client.patch(
        f'/api/risk-treatments/{treatment_id}/status',
        headers=headers,
        json={'status': 'In progress'},
    )
    assert started.status_code == 200
    no_actions_completion = client.patch(
        f'/api/risk-treatments/{treatment_id}/status',
        headers=headers,
        json={'status': 'Completed', 'residual_probability': 2, 'residual_impact': 3},
    )
    assert no_actions_completion.status_code == 409

    action_owner_created = client.post(
        '/api/users',
        headers=headers,
        json={
            'username': 'assigned-action-owner',
            'email': 'action.owner@example.test',
            'full_name': 'Assigned Action Owner',
            'password': 'action-owner-password',
            'role': 'Auditor',
        },
    )
    assert action_owner_created.status_code == 201
    action_owner_headers = login(client, 'assigned-action-owner', 'action-owner-password')
    action = client.post(
        f'/api/risk-treatments/{treatment_id}/actions',
        headers=headers,
        json={
            'title': 'Configure the redundant service',
            'owner_id': action_owner_created.json()['id'],
            'due_date': '2030-01-03T00:00:00Z',
        },
    )
    assert action.status_code == 201
    premature_completion = client.patch(
        f'/api/risk-treatments/{treatment_id}/status',
        headers=headers,
        json={'status': 'Completed', 'residual_probability': 2, 'residual_impact': 3},
    )
    assert premature_completion.status_code == 409

    action_completed = client.patch(
        f"/api/treatment-actions/{action.json()['id']}",
        headers=action_owner_headers,
        json={'status': 'In progress'},
    )
    assert action_completed.status_code == 200
    missing_result = client.patch(
        f"/api/treatment-actions/{action.json()['id']}",
        headers=action_owner_headers,
        json={'status': 'Completed'},
    )
    assert missing_result.status_code == 422
    action_completed = client.patch(
        f"/api/treatment-actions/{action.json()['id']}",
        headers=action_owner_headers,
        json={'status': 'Completed', 'result': 'Failover test passed.'},
    )
    assert action_completed.status_code == 200

    completed = client.patch(
        f'/api/risk-treatments/{treatment_id}/status',
        headers=headers,
        json={'status': 'Completed', 'residual_probability': 2, 'residual_impact': 3},
    )
    assert completed.status_code == 200
    assert completed.json()['residual_score'] == 6
    assert completed.json()['residual_risk'] == 'Moderate'

    risk_after_treatment = next(
        item for item in client.get('/api/risks', headers=headers).json()
        if item['id'] == risk_id
    )
    assert risk_after_treatment['residual_assessment']['score'] == 6
    assert risk_after_treatment['level'] == 'Moderate'


def test_department_manager_is_scoped_and_cannot_approve(client: TestClient) -> None:
    admin_headers = login(client)
    create_user = client.post(
        '/api/users',
        headers=admin_headers,
        json={
            'username': 'finance-manager',
            'email': 'finance.manager@example.test',
            'full_name': 'Finance Manager',
            'password': 'test-password-123',
            'role': 'Department Manager',
            'department_id': 2,
        },
    )
    assert create_user.status_code == 201

    manager_headers = login(client, 'finance-manager', 'test-password-123')
    visible_risks = client.get('/api/risks', headers=manager_headers)
    assert visible_risks.status_code == 200
    assert visible_risks.json()
    assert all(risk['department_id'] == 2 for risk in visible_risks.json())

    denied_risk = client.post(
        '/api/risks',
        headers=manager_headers,
        json={
            'code': 'OUT-OF-SCOPE',
            'name': 'Out-of-scope risk',
            'description': 'This risk is outside the assigned department.',
            'category': 'Operational',
            'department_id': 1,
        },
    )
    assert denied_risk.status_code == 403

    owned_risk = client.post(
        '/api/risks',
        headers=manager_headers,
        json={
            'code': 'FIN-OWNED',
            'name': 'Finance-owned risk',
            'description': 'A test risk owned by the finance manager.',
            'category': 'Operational',
            'department_id': 2,
        },
    )
    assert owned_risk.status_code == 201
    proposed = client.post(
        f"/api/risks/{owned_risk.json()['id']}/treatments",
        headers=manager_headers,
        json={'strategy': 'Reduce', 'treatment_plan': 'Add a tested secondary provider.'},
    )
    assert proposed.status_code == 201
    self_review = client.post(
        f"/api/risk-treatments/{proposed.json()['id']}/decision",
        headers=admin_headers,
        json={'decision': 'approve', 'comment': 'This is not my proposal.'},
    )
    assert self_review.status_code == 200
    denied_review = client.post(
        f"/api/risk-treatments/{proposed.json()['id']}/decision",
        headers=manager_headers,
        json={'decision': 'approve', 'comment': 'This role cannot approve.'},
    )
    assert denied_review.status_code == 403


def test_auditor_is_read_only(client: TestClient) -> None:
    admin_headers = login(client)
    created = client.post(
        '/api/users',
        headers=admin_headers,
        json={
            'username': 'internal-auditor',
            'email': 'auditor@example.test',
            'full_name': 'Internal Auditor',
            'password': 'test-password-456',
            'role': 'Auditor',
        },
    )
    assert created.status_code == 201
    auditor_headers = login(client, 'internal-auditor', 'test-password-456')

    assert client.get('/api/risks', headers=auditor_headers).status_code == 200
    assert client.get('/api/audit-logs', headers=auditor_headers).status_code == 200
    denied = client.post(
        '/api/risks',
        headers=auditor_headers,
        json={
            'code': 'READ-ONLY',
            'name': 'Read-only test',
            'description': 'The auditor cannot create risks.',
            'category': 'Technical',
            'department_id': 1,
        },
    )
    assert denied.status_code == 403


def test_additive_schema_upgrade_adds_new_workflow_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    old_engine = create_engine('sqlite://')
    with old_engine.begin() as connection:
        connection.execute(text('CREATE TABLE risk_treatments (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE risk_assessments (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE treatment_actions (id INTEGER PRIMARY KEY)'))

    monkeypatch.setattr(schema_upgrade, 'engine', old_engine)
    schema_upgrade.upgrade_schema()

    inspector = inspect(old_engine)
    treatment_columns = {column['name'] for column in inspector.get_columns('risk_treatments')}
    assessment_columns = {column['name'] for column in inspector.get_columns('risk_assessments')}
    action_columns = {column['name'] for column in inspector.get_columns('treatment_actions')}
    assert {'created_by_id', 'reviewed_by_id', 'residual_probability', 'expected_result'} <= treatment_columns
    assert 'assessment_type' in assessment_columns
    assert {'expected_result', 'resources_required'} <= action_columns
    old_engine.dispose()
