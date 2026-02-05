"""add_rls_policies

Revision ID: 53cf28d4c70f
Revises: 9e8450bf0bd1
Create Date: 2026-02-02 19:07:20.939715

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "53cf28d4c70f"
down_revision: str | Sequence[str] | None = "9e8450bf0bd1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add Row Level Security policies for workspace-scoped tables.

    Note: The FastAPI backend typically uses a service account that bypasses RLS.
    RLS serves as defense-in-depth alongside application-level permission checks
    in the service layer. It is primarily enforced for direct Supabase client
    connections (e.g., frontend realtime subscriptions).
    """
    # --- Helper function to avoid RLS recursion ---
    # A SECURITY DEFINER function that checks workspace membership
    # without triggering RLS on workspace_members itself.
    op.execute("""
        CREATE OR REPLACE FUNCTION get_user_workspace_ids(uid UUID)
        RETURNS SETOF UUID
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = public
        AS $$
            SELECT workspace_id FROM workspace_members WHERE user_id = uid;
        $$;
    """)

    # --- Enable RLS on tables ---
    for table in [
        "workspaces",
        "workspace_members",
        "todos",
        "tags",
        "invitations",
        "activity_log",
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")

    # --- Workspaces policies ---
    # SELECT: user is a member of the workspace
    op.execute("""
        CREATE POLICY workspace_select ON workspaces
            FOR SELECT USING (
                id IN (SELECT get_user_workspace_ids((SELECT auth.uid())))
            );
    """)
    # INSERT: any authenticated user can create a workspace
    op.execute("""
        CREATE POLICY workspace_insert ON workspaces
            FOR INSERT WITH CHECK (
                (SELECT auth.uid()) IS NOT NULL
            );
    """)
    # UPDATE: only owners and admins
    op.execute("""
        CREATE POLICY workspace_update ON workspaces
            FOR UPDATE USING (
                id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin')
                )
            );
    """)
    # DELETE: only owners
    op.execute("""
        CREATE POLICY workspace_delete ON workspaces
            FOR DELETE USING (
                id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role = 'owner'
                )
            );
    """)

    # --- Workspace Members policies ---
    # SELECT: co-members can see each other
    op.execute("""
        CREATE POLICY members_select ON workspace_members
            FOR SELECT USING (
                workspace_id IN (SELECT get_user_workspace_ids((SELECT auth.uid())))
            );
    """)
    # INSERT: admins+ can add members
    op.execute("""
        CREATE POLICY members_insert ON workspace_members
            FOR INSERT WITH CHECK (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin')
                )
            );
    """)
    # DELETE: admins+ can remove members
    op.execute("""
        CREATE POLICY members_delete ON workspace_members
            FOR DELETE USING (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin')
                )
                OR user_id = (SELECT auth.uid())
            );
    """)

    # --- Todos policies ---
    # SELECT: workspace members can view
    op.execute("""
        CREATE POLICY todos_select ON todos
            FOR SELECT USING (
                workspace_id IN (SELECT get_user_workspace_ids((SELECT auth.uid())))
            );
    """)
    # INSERT: members+ can create
    op.execute("""
        CREATE POLICY todos_insert ON todos
            FOR INSERT WITH CHECK (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin', 'member')
                )
            );
    """)
    # UPDATE: members+ can update
    op.execute("""
        CREATE POLICY todos_update ON todos
            FOR UPDATE USING (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin', 'member')
                )
            );
    """)
    # DELETE: members+ can delete
    op.execute("""
        CREATE POLICY todos_delete ON todos
            FOR DELETE USING (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin', 'member')
                )
            );
    """)

    # --- Tags policies ---
    # SELECT: workspace members can view
    op.execute("""
        CREATE POLICY tags_select ON tags
            FOR SELECT USING (
                workspace_id IN (SELECT get_user_workspace_ids((SELECT auth.uid())))
            );
    """)
    # INSERT: members+ can create
    op.execute("""
        CREATE POLICY tags_insert ON tags
            FOR INSERT WITH CHECK (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin', 'member')
                )
            );
    """)
    # UPDATE: members+ can update
    op.execute("""
        CREATE POLICY tags_update ON tags
            FOR UPDATE USING (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin', 'member')
                )
            );
    """)
    # DELETE: admins+ can delete tags
    op.execute("""
        CREATE POLICY tags_delete ON tags
            FOR DELETE USING (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin')
                )
            );
    """)

    # --- Invitations policies ---
    # SELECT: workspace members can view invitations
    op.execute("""
        CREATE POLICY invitations_select ON invitations
            FOR SELECT USING (
                workspace_id IN (SELECT get_user_workspace_ids((SELECT auth.uid())))
                OR email = (SELECT email FROM profiles WHERE id = (SELECT auth.uid()))
            );
    """)
    # INSERT: admins+ can create invitations
    op.execute("""
        CREATE POLICY invitations_insert ON invitations
            FOR INSERT WITH CHECK (
                workspace_id IN (
                    SELECT workspace_id FROM workspace_members
                    WHERE user_id = (SELECT auth.uid())
                    AND role IN ('owner', 'admin')
                )
            );
    """)

    # --- Activity Log policies ---
    # SELECT: workspace members can view activity
    op.execute("""
        CREATE POLICY activity_log_select ON activity_log
            FOR SELECT USING (
                workspace_id IN (SELECT get_user_workspace_ids((SELECT auth.uid())))
            );
    """)
    # INSERT: application-level only (via service account)
    op.execute("""
        CREATE POLICY activity_log_insert ON activity_log
            FOR INSERT WITH CHECK (
                (SELECT auth.uid()) IS NOT NULL
            );
    """)


def downgrade() -> None:
    """Drop all RLS policies and disable RLS."""
    # Drop policies
    policies = [
        ("activity_log_insert", "activity_log"),
        ("activity_log_select", "activity_log"),
        ("invitations_insert", "invitations"),
        ("invitations_select", "invitations"),
        ("tags_delete", "tags"),
        ("tags_update", "tags"),
        ("tags_insert", "tags"),
        ("tags_select", "tags"),
        ("todos_delete", "todos"),
        ("todos_update", "todos"),
        ("todos_insert", "todos"),
        ("todos_select", "todos"),
        ("members_delete", "workspace_members"),
        ("members_insert", "workspace_members"),
        ("members_select", "workspace_members"),
        ("workspace_delete", "workspaces"),
        ("workspace_update", "workspaces"),
        ("workspace_insert", "workspaces"),
        ("workspace_select", "workspaces"),
    ]
    for policy_name, table_name in policies:
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table_name};")

    # Disable RLS
    for table in [
        "activity_log",
        "invitations",
        "tags",
        "todos",
        "workspace_members",
        "workspaces",
    ]:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # Drop helper function
    op.execute("DROP FUNCTION IF EXISTS get_user_workspace_ids(UUID);")
