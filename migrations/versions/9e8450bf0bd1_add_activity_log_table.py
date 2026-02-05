"""add_activity_log_table

Revision ID: 9e8450bf0bd1
Revises: 39710ce14cba
Create Date: 2026-02-02 19:02:04.240452

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e8450bf0bd1"
down_revision: str | Sequence[str] | None = "39710ce14cba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create activity_log table with indexes."""
    op.create_table(
        "activity_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # Index for workspace activity feed (newest first)
    op.create_index(
        "ix_activity_log_workspace_created",
        "activity_log",
        ["workspace_id", sa.text("created_at DESC")],
        unique=False,
    )
    # Index for entity-specific history
    op.create_index(
        "ix_activity_log_entity",
        "activity_log",
        ["entity_type", "entity_id", sa.text("created_at DESC")],
        unique=False,
    )
    # Index for user activity
    op.create_index(
        "ix_activity_log_actor",
        "activity_log",
        ["actor_id", sa.text("created_at DESC")],
        unique=False,
    )


def downgrade() -> None:
    """Drop activity_log table."""
    op.drop_index("ix_activity_log_actor", table_name="activity_log")
    op.drop_index("ix_activity_log_entity", table_name="activity_log")
    op.drop_index("ix_activity_log_workspace_created", table_name="activity_log")
    op.drop_table("activity_log")
