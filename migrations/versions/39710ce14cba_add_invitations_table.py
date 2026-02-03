"""add_invitations_table

Revision ID: 39710ce14cba
Revises: bc8a2f402d9d
Create Date: 2026-02-02 18:43:07.585767

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39710ce14cba'
down_revision: Union[str, Sequence[str], None] = 'bc8a2f402d9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create invitations table."""
    op.create_table('invitations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False, server_default='member'),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('invited_by', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('accepted_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("role IN ('admin', 'member', 'viewer')", name='ck_invitations_role'),
        sa.CheckConstraint("status IN ('pending', 'accepted', 'expired', 'revoked')", name='ck_invitations_status'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    # Index for looking up invitations by workspace + email
    op.create_index('ix_invitations_workspace_email', 'invitations', ['workspace_id', 'email'], unique=False)
    # Index for looking up user's pending invitations
    op.create_index('ix_invitations_email_status', 'invitations', ['email', 'status'], unique=False)


def downgrade() -> None:
    """Drop invitations table."""
    op.drop_index('ix_invitations_email_status', table_name='invitations')
    op.drop_index('ix_invitations_workspace_email', table_name='invitations')
    op.drop_table('invitations')
