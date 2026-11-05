"""Add datasets and evaluation metric snapshots.

Revision ID: 0002_datasets
Revises: 0001_initial
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_datasets"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "evaluation_datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_datasets")),
    )
    op.create_index(
        op.f("ix_evaluation_datasets_name"), "evaluation_datasets", ["name"], unique=False
    )
    op.create_table(
        "dataset_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("input_data", json_type(), nullable=False),
        sa.Column("expected_output", sa.Text(), nullable=True),
        sa.Column("expected_json", sa.Boolean(), nullable=False),
        sa.Column("reference_keywords", json_type(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["evaluation_datasets.id"],
            name=op.f("fk_dataset_cases_dataset_id_evaluation_datasets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_cases")),
        sa.UniqueConstraint("dataset_id", "position", name="uq_dataset_cases_dataset_id_position"),
    )
    op.create_index(op.f("ix_dataset_cases_dataset_id"), "dataset_cases", ["dataset_id"], unique=False)

    op.add_column("evaluation_runs", sa.Column("dataset_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_evaluation_runs_dataset_id_evaluation_datasets"),
        "evaluation_runs",
        "evaluation_datasets",
        ["dataset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_evaluation_runs_dataset_id"), "evaluation_runs", ["dataset_id"], unique=False)

    op.add_column("evaluation_cases", sa.Column("dataset_case_id", sa.Uuid(), nullable=True))
    op.add_column(
        "evaluation_cases",
        sa.Column("expected_json", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("evaluation_cases", sa.Column("reference_keywords", json_type(), nullable=True))
    op.add_column("evaluation_cases", sa.Column("metrics", json_type(), nullable=True))
    op.create_foreign_key(
        op.f("fk_evaluation_cases_dataset_case_id_dataset_cases"),
        "evaluation_cases",
        "dataset_cases",
        ["dataset_case_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_evaluation_cases_dataset_case_id"),
        "evaluation_cases",
        ["dataset_case_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluation_cases_dataset_case_id"), table_name="evaluation_cases")
    op.drop_constraint(
        op.f("fk_evaluation_cases_dataset_case_id_dataset_cases"),
        "evaluation_cases",
        type_="foreignkey",
    )
    op.drop_column("evaluation_cases", "metrics")
    op.drop_column("evaluation_cases", "reference_keywords")
    op.drop_column("evaluation_cases", "expected_json")
    op.drop_column("evaluation_cases", "dataset_case_id")
    op.drop_index(op.f("ix_evaluation_runs_dataset_id"), table_name="evaluation_runs")
    op.drop_constraint(
        op.f("fk_evaluation_runs_dataset_id_evaluation_datasets"),
        "evaluation_runs",
        type_="foreignkey",
    )
    op.drop_column("evaluation_runs", "dataset_id")
    op.drop_index(op.f("ix_dataset_cases_dataset_id"), table_name="dataset_cases")
    op.drop_table("dataset_cases")
    op.drop_index(op.f("ix_evaluation_datasets_name"), table_name="evaluation_datasets")
    op.drop_table("evaluation_datasets")
