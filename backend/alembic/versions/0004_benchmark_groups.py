"""Persist cross-provider benchmark groups.

Revision ID: 0004_benchmark_groups
Revises: 0003_trace_details
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_benchmark_groups"
down_revision: Union[str, None] = "0003_trace_details"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "benchmarks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "completed",
                "partial",
                "failed",
                name="benchmarkstatus",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "providers",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["evaluation_datasets.id"],
            name=op.f("fk_benchmarks_dataset_id_evaluation_datasets"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_benchmarks")),
    )
    op.create_index(
        op.f("ix_benchmarks_dataset_id"), "benchmarks", ["dataset_id"], unique=False
    )
    op.add_column(
        "evaluation_runs",
        sa.Column("benchmark_id", sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_evaluation_runs_benchmark_id_benchmarks"),
        "evaluation_runs",
        "benchmarks",
        ["benchmark_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_evaluation_runs_benchmark_id"),
        "evaluation_runs",
        ["benchmark_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluation_runs_benchmark_id"), table_name="evaluation_runs")
    op.drop_constraint(
        op.f("fk_evaluation_runs_benchmark_id_benchmarks"),
        "evaluation_runs",
        type_="foreignkey",
    )
    op.drop_column("evaluation_runs", "benchmark_id")
    op.drop_index(op.f("ix_benchmarks_dataset_id"), table_name="benchmarks")
    op.drop_table("benchmarks")
