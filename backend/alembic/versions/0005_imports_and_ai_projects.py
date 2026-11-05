"""Add dataset import metadata and authorized AI projects.

Revision ID: 0005_imports_and_projects
Revises: 0004_benchmark_groups
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_imports_and_projects"
down_revision: Union[str, None] = "0004_benchmark_groups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def json_type() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.add_column("evaluation_datasets", sa.Column("source_file_name", sa.String(255), nullable=True))
    op.add_column(
        "evaluation_datasets",
        sa.Column("import_status", sa.String(20), server_default="manual", nullable=False),
    )
    op.add_column("evaluation_datasets", sa.Column("import_sha256", sa.String(64), nullable=True))
    op.add_column("evaluation_datasets", sa.Column("import_key", sa.String(100), nullable=True))
    op.add_column("evaluation_datasets", sa.Column("validation_errors", json_type(), nullable=True))
    op.create_unique_constraint(
        "uq_evaluation_datasets_import_sha256", "evaluation_datasets", ["import_sha256"]
    )
    op.create_unique_constraint(
        "uq_evaluation_datasets_import_key", "evaluation_datasets", ["import_key"]
    )
    op.add_column("dataset_cases", sa.Column("metadata", json_type(), nullable=True))

    op.create_table(
        "ai_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=False),
        sa.Column("http_method", sa.String(10), nullable=False),
        sa.Column("request_template", json_type(), nullable=False),
        sa.Column("response_path", sa.String(500), nullable=False),
        sa.Column("auth_env_var", sa.String(200), nullable=True),
        sa.Column("auth_header", sa.String(100), nullable=False),
        sa.Column("auth_scheme", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_projects")),
    )
    op.add_column("evaluation_runs", sa.Column("project_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_evaluation_runs_project_id_ai_projects"),
        "evaluation_runs",
        "ai_projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_evaluation_runs_project_id"), "evaluation_runs", ["project_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_evaluation_runs_project_id"), table_name="evaluation_runs")
    op.drop_constraint(
        op.f("fk_evaluation_runs_project_id_ai_projects"),
        "evaluation_runs",
        type_="foreignkey",
    )
    op.drop_column("evaluation_runs", "project_id")
    op.drop_table("ai_projects")
    op.drop_column("dataset_cases", "metadata")
    op.drop_constraint(
        "uq_evaluation_datasets_import_key", "evaluation_datasets", type_="unique"
    )
    op.drop_constraint(
        "uq_evaluation_datasets_import_sha256", "evaluation_datasets", type_="unique"
    )
    op.drop_column("evaluation_datasets", "validation_errors")
    op.drop_column("evaluation_datasets", "import_key")
    op.drop_column("evaluation_datasets", "import_sha256")
    op.drop_column("evaluation_datasets", "import_status")
    op.drop_column("evaluation_datasets", "source_file_name")
