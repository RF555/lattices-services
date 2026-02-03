"""add_notification_tables

Revision ID: a3f8c2d91b4e
Revises: e1eb0d70d0ac
Create Date: 2026-02-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f8c2d91b4e'
down_revision: Union[str, Sequence[str], None] = 'e1eb0d70d0ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create notification tables, indexes, RLS policies, and seed data."""

    # --- notification_types (lookup/seed table) ---
    op.create_table('notification_types',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('default_channels', sa.JSON(), nullable=True,
                  server_default='["in_app"]'),
        sa.Column('is_mandatory', sa.Boolean(), nullable=False,
                  server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # --- notifications (core event table) ---
    op.create_table('notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('type_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['type_id'], ['notification_types.id']),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_id'], ['profiles.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_notifications_workspace_created',
                    'notifications', ['workspace_id', sa.text('created_at DESC')])
    op.create_index('idx_notifications_entity',
                    'notifications', ['entity_type', 'entity_id'])
    op.create_index('idx_notifications_expires',
                    'notifications', ['expires_at'],
                    postgresql_where=sa.text('expires_at IS NOT NULL'))
    op.create_index('idx_notifications_dedup',
                    'notifications',
                    ['entity_type', 'entity_id', 'actor_id',
                     sa.text('created_at DESC')])

    # --- notification_recipients (per-user delivery) ---
    op.create_table('notification_recipients',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('notification_id', sa.UUID(), nullable=False),
        sa.Column('recipient_id', sa.UUID(), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False,
                  server_default='false'),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False,
                  server_default='false'),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recipient_id'], ['profiles.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('notification_id', 'recipient_id'),
    )
    # Partial indexes for performance
    op.create_index('idx_recipients_user_unread',
                    'notification_recipients',
                    ['recipient_id', sa.text('notification_id DESC')],
                    postgresql_where=sa.text(
                        'is_read = FALSE AND is_deleted = FALSE'))
    op.create_index('idx_recipients_user_feed',
                    'notification_recipients',
                    ['recipient_id', sa.text('notification_id DESC')],
                    postgresql_where=sa.text('is_deleted = FALSE'))

    # --- notification_preferences (user settings) ---
    op.create_table('notification_preferences',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('workspace_id', sa.UUID(), nullable=True),
        sa.Column('notification_type', sa.String(length=50), nullable=True),
        sa.Column('channel', sa.String(length=20), nullable=False,
                  server_default='in_app'),
        sa.Column('enabled', sa.Boolean(), nullable=False,
                  server_default='true'),
        sa.ForeignKeyConstraint(['user_id'], ['profiles.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'],
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'workspace_id', 'notification_type',
                            'channel'),
    )
    op.create_index('idx_prefs_user', 'notification_preferences', ['user_id'])

    # --- Enable RLS on all notification tables ---
    op.execute(
        "ALTER TABLE notification_types ENABLE ROW LEVEL SECURITY;"
    )
    op.execute(
        "ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;"
    )
    op.execute(
        "ALTER TABLE notification_recipients ENABLE ROW LEVEL SECURITY;"
    )
    op.execute(
        "ALTER TABLE notification_preferences ENABLE ROW LEVEL SECURITY;"
    )

    # --- RLS Policies ---

    # notification_types: readable by all authenticated users
    op.execute("""
        CREATE POLICY types_select ON notification_types
            FOR SELECT USING ((SELECT auth.uid()) IS NOT NULL);
    """)

    # notifications: workspace members can read; authenticated users can insert
    op.execute("""
        CREATE POLICY notifications_select ON notifications
            FOR SELECT USING (
                workspace_id IN (SELECT get_user_workspace_ids((SELECT auth.uid())))
            );
    """)
    op.execute("""
        CREATE POLICY notifications_insert ON notifications
            FOR INSERT WITH CHECK ((SELECT auth.uid()) IS NOT NULL);
    """)

    # notification_recipients: users see/update only their own
    op.execute("""
        CREATE POLICY recipients_select ON notification_recipients
            FOR SELECT USING (recipient_id = (SELECT auth.uid()));
    """)
    op.execute("""
        CREATE POLICY recipients_update ON notification_recipients
            FOR UPDATE USING (recipient_id = (SELECT auth.uid()));
    """)

    # notification_preferences: users manage only their own
    op.execute("""
        CREATE POLICY prefs_all ON notification_preferences
            FOR ALL USING (user_id = (SELECT auth.uid()));
    """)

    # --- Seed notification_types ---
    op.execute("""
        INSERT INTO notification_types (id, name, description, template, is_mandatory)
        VALUES
            (gen_random_uuid(), 'task.completed',
             'Triggered when a task is marked as completed',
             '{actor_name} completed "{entity_title}"',
             false),
            (gen_random_uuid(), 'task.updated',
             'Triggered when a task is updated',
             '{actor_name} updated "{entity_title}"',
             false),
            (gen_random_uuid(), 'task.created',
             'Triggered when a new task is created',
             '{actor_name} created "{entity_title}"',
             false),
            (gen_random_uuid(), 'task.deleted',
             'Triggered when a task is deleted',
             '{actor_name} deleted "{entity_title}"',
             false),
            (gen_random_uuid(), 'member.added',
             'Triggered when a user is added to a workspace',
             '{actor_name} added you to workspace "{workspace_name}"',
             true),
            (gen_random_uuid(), 'member.removed',
             'Triggered when a user is removed from a workspace',
             'You were removed from workspace "{workspace_name}"',
             true),
            (gen_random_uuid(), 'member.role_changed',
             'Triggered when a user''s workspace role is changed',
             'Your role in "{workspace_name}" was changed to {new_role}',
             true),
            (gen_random_uuid(), 'invitation.received',
             'Triggered when a user receives a workspace invitation',
             '{actor_name} invited you to join "{workspace_name}"',
             true),
            (gen_random_uuid(), 'invitation.accepted',
             'Triggered when an invitation is accepted',
             '{actor_name} accepted your invitation to "{workspace_name}"',
             false),
            (gen_random_uuid(), 'group.member_added',
             'Triggered when a user is added to a group',
             '{actor_name} added you to group "{group_name}"',
             false);
    """)

    # Note: For notification cleanup, use pg_cron in Supabase Dashboard:
    # SELECT cron.schedule('cleanup-expired-notifications', '0 3 * * 0',
    #     $$DELETE FROM notifications WHERE expires_at IS NOT NULL AND expires_at < NOW()$$
    # );


def downgrade() -> None:
    """Drop notification tables and RLS policies."""
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS prefs_all ON notification_preferences;")
    op.execute(
        "DROP POLICY IF EXISTS recipients_update ON notification_recipients;"
    )
    op.execute(
        "DROP POLICY IF EXISTS recipients_select ON notification_recipients;"
    )
    op.execute(
        "DROP POLICY IF EXISTS notifications_insert ON notifications;"
    )
    op.execute(
        "DROP POLICY IF EXISTS notifications_select ON notifications;"
    )
    op.execute(
        "DROP POLICY IF EXISTS types_select ON notification_types;"
    )

    # Drop indexes and tables (in dependency order)
    op.drop_index('idx_prefs_user', table_name='notification_preferences')
    op.drop_table('notification_preferences')

    op.drop_index('idx_recipients_user_feed',
                  table_name='notification_recipients')
    op.drop_index('idx_recipients_user_unread',
                  table_name='notification_recipients')
    op.drop_table('notification_recipients')

    op.drop_index('idx_notifications_dedup', table_name='notifications')
    op.drop_index('idx_notifications_expires', table_name='notifications')
    op.drop_index('idx_notifications_entity', table_name='notifications')
    op.drop_index('idx_notifications_workspace_created',
                  table_name='notifications')
    op.drop_table('notifications')

    op.drop_table('notification_types')
