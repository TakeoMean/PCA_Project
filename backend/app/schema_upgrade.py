from sqlalchemy import inspect, text

from app.database import engine


_ADDITIVE_COLUMNS = {
    'risk_treatments': {
        'created_by_id': 'INTEGER',
        'reviewed_by_id': 'INTEGER',
        'review_comment': 'TEXT',
        'expected_result': 'TEXT',
        'resources_required': 'TEXT',
        'residual_probability': 'INTEGER',
        'residual_impact': 'INTEGER',
        'updated_at': 'TIMESTAMP',
    },
    'risk_assessments': {
        'assessment_type': "VARCHAR(30) NOT NULL DEFAULT 'Inherent'",
    },
    'treatment_actions': {
        'expected_result': 'TEXT',
        'resources_required': 'TEXT',
    },
    'risks': {
        'source': 'VARCHAR(160)',
        'causes': 'TEXT',
        'existing_measures': 'TEXT',
        'review_date': 'TIMESTAMP',
        'identified_by_id': 'INTEGER',
        'status': "VARCHAR(30) NOT NULL DEFAULT 'Draft'",
        'acceptance_justification': 'TEXT',
        'updated_at': 'TIMESTAMP',
    },
    'users': {
        'must_change_password': 'BOOLEAN NOT NULL DEFAULT FALSE',
    },
    'smca_scopes': {
        'acceptance_threshold': 'INTEGER NOT NULL DEFAULT 9',
    },
    'risk_controls': {
        'next_test_date': 'TIMESTAMP',
    },
}


def upgrade_schema() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table_name, columns in _ADDITIVE_COLUMNS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column['name'] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing_columns:
                    connection.execute(text(
                        f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}'
                    ))
