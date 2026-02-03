"""add_workspace_tables

Revision ID: f3367ee49136
Revises: 6e522fa7b7a8
Create Date: 2026-02-02 18:06:01.200110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3367ee49136'
down_revision: Union[str, Sequence[str], None] = '6e522fa7b7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create workspace and workspace_members tables, add workspace_id to todos and tags."""
    # Create workspaces table
    op.create_table('workspaces',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('settings', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )

    # Create workspace_members table with composite PK
    op.create_table('workspace_members',
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='member'),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.Column('invited_by', sa.UUID(), nullable=True),
        sa.CheckConstraint("role IN ('owner', 'admin', 'member', 'viewer')", name='ck_workspace_members_role'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['profiles.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('workspace_id', 'user_id'),
    )
    op.create_index('ix_workspace_members_user_id', 'workspace_members', ['user_id'], unique=False)
    op.create_index(
        'ix_workspace_members_user_workspace_role',
        'workspace_members',
        ['user_id', 'workspace_id', 'role'],
        unique=False,
    )

    # Add workspace_id to todos (nullable initially for data migration)
    op.add_column('todos', sa.Column('workspace_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_todos_workspace_id',
        'todos', 'workspaces',
        ['workspace_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_index('ix_todos_workspace_id', 'todos', ['workspace_id'], unique=False)

    # Add workspace_id to tags (nullable initially for data migration)
    op.add_column('tags', sa.Column('workspace_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_tags_workspace_id',
        'tags', 'workspaces',
        ['workspace_id'], ['id'],
        ondelete='CASCADE',
    )
    op.create_index('ix_tags_workspace_id', 'tags', ['workspace_id'], unique=False)


def downgrade() -> None:
    """Remove workspace tables and workspace_id columns."""
    # Remove workspace_id from tags
    op.drop_index('ix_tags_workspace_id', table_name='tags')
    op.drop_constraint('fk_tags_workspace_id', 'tags', type_='foreignkey')
    op.drop_column('tags', 'workspace_id')

    # Remove workspace_id from todos
    op.drop_index('ix_todos_workspace_id', table_name='todos')
    op.drop_constraint('fk_todos_workspace_id', 'todos', type_='foreignkey')
    op.drop_column('todos', 'workspace_id')

    # Drop workspace_members
    op.drop_index('ix_workspace_members_user_workspace_role', table_name='workspace_members')
    op.drop_index('ix_workspace_members_user_id', table_name='workspace_members')
    op.drop_table('workspace_members')

    # Drop workspaces
    op.drop_table('workspaces')
