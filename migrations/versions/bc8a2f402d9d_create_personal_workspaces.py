"""create_personal_workspaces

Revision ID: bc8a2f402d9d
Revises: f3367ee49136
Create Date: 2026-02-02 18:06:17.931121

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "bc8a2f402d9d"
down_revision: str | Sequence[str] | None = "f3367ee49136"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create personal workspaces for all existing users and migrate their data."""
    conn = op.get_bind()

    # For each profile, create a personal workspace, add as owner, and migrate data
    conn.execute(
        text("""
        WITH new_workspaces AS (
            INSERT INTO workspaces (id, name, slug, description, created_by, settings, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                'Personal',
                'personal-' || LEFT(CAST(id AS text), 8),
                'Personal workspace',
                id,
                '{}',
                NOW(),
                NOW()
            FROM profiles
            RETURNING id, created_by
        ),
        new_members AS (
            INSERT INTO workspace_members (workspace_id, user_id, role, joined_at)
            SELECT id, created_by, 'owner', NOW()
            FROM new_workspaces
        ),
        update_todos AS (
            UPDATE todos
            SET workspace_id = nw.id
            FROM new_workspaces nw
            WHERE todos.user_id = nw.created_by
        )
        UPDATE tags
        SET workspace_id = nw.id
        FROM new_workspaces nw
        WHERE tags.user_id = nw.created_by
    """)
    )

    # Now make workspace_id NOT NULL on both tables
    op.alter_column("todos", "workspace_id", nullable=False)
    op.alter_column("tags", "workspace_id", nullable=False)


def downgrade() -> None:
    """Revert workspace_id to nullable and remove personal workspaces."""
    # Make workspace_id nullable again
    op.alter_column("todos", "workspace_id", nullable=True)
    op.alter_column("tags", "workspace_id", nullable=True)

    conn = op.get_bind()

    # Set workspace_id to NULL on all todos and tags
    conn.execute(text("UPDATE todos SET workspace_id = NULL"))
    conn.execute(text("UPDATE tags SET workspace_id = NULL"))

    # Delete all personal workspaces (cascade will remove members)
    conn.execute(text("DELETE FROM workspaces WHERE name = 'Personal' AND slug LIKE 'personal-%'"))
