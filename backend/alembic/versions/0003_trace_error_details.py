"""Add operation names and sanitized error details to traces.

Revision ID: 0003_trace_details
Revises: 0002_datasets
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_trace_details"
down_revision: Union[str, None] = "0002_datasets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "execution_traces",
        sa.Column(
            "operation_name",
            sa.String(length=200),
            server_default="evaluation.case",
            nullable=False,
        ),
    )
    op.add_column("execution_traces", sa.Column("error_details", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("execution_traces", "error_details")
    op.drop_column("execution_traces", "operation_name")
