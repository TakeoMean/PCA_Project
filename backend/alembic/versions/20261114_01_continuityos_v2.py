"""ContinuityOS v2 SMCA governance baseline.

Revision ID: 20261114_01
Revises:
Create Date: 2026-11-14
"""

from alembic import op
import sqlalchemy as sa

from app.models import Base
from app.schema_upgrade import _ADDITIVE_COLUMNS


revision = '20261114_01'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name, columns in _ADDITIVE_COLUMNS.items():
        if table_name not in existing_tables:
            continue
        existing_columns = {column['name'] for column in inspector.get_columns(table_name)}
        for column_name, column_type in columns.items():
            if column_name not in existing_columns:
                op.execute(sa.text(
                    f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}'
                ))


def downgrade() -> None:
    # This baseline intentionally keeps business-continuity records intact.
    pass

