"""add_group_tables

Revision ID: e1eb0d70d0ac
Revises: 53cf28d4c70f
Create Date: 2026-02-02 19:13:40.958699

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1eb0d70d0ac'
down_revision: Union[str, Sequence[str], None] = '53cf28d4c70f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create groups and group_members tables."""
    op.create_table('groups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_groups_workspace_id', 'groups', ['workspace_id'], unique=False)

    op.create_table('group_members',
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='member'),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'member')", name='ck_group_members_role'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('group_id', 'user_id'),
    )
    op.create_index('ix_group_members_user_id', 'group_members', ['user_id'], unique=False)

    # Enable RLS on new tables
    op.execute("ALTER TABLE groups ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE group_members ENABLE ROW LEVEL SECURITY;")

    # RLS policies for groups
    op.execute("""
        CREATE POLICY groups_select ON groups
            FOR SELECT USING (
                workspace_id IN (SELECT get_user_workspace_ids((SELECT auth.uid())))
            );
    """)
    op.execute("""
        CREATE POLICY groups_insert ON groups
            FOR INSERT WITH CHECK (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin')
                )
            );
    """)
    op.execute("""
        CREATE POLICY groups_delete ON groups
            FOR DELETE USING (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin')
                )
            );
    """)

    # RLS policies for group_members
    op.execute("""
        CREATE POLICY group_members_select ON group_members
            FOR SELECT USING (
                group_id IN (
                    SELECT id FROM groups
                    WHERE workspace_id IN (
                        SELECT get_user_workspace_ids((SELECT auth.uid()))
                    )
                )
            );
    """)


def downgrade() -> None:
    """Drop group tables and RLS policies."""
    # Drop policies
    op.execute("DROP POLICY IF EXISTS group_members_select ON group_members;")
    op.execute("DROP POLICY IF EXISTS groups_delete ON groups;")
    op.execute("DROP POLICY IF EXISTS groups_insert ON groups;")
    op.execute("DROP POLICY IF EXISTS groups_select ON groups;")

    op.drop_index('ix_group_members_user_id', table_name='group_members')
    op.drop_table('group_members')
    op.drop_index('ix_groups_workspace_id', table_name='groups')
    op.drop_table('groups')
