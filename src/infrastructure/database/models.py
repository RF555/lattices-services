"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class ProfileModel(Base):
    """User profile model (synced from Supabase)."""

    __tablename__ = "profiles"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    todos: Mapped[list["TodoModel"]] = relationship(
        "TodoModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list["TagModel"]] = relationship(
        "TagModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    workspace_memberships: Mapped[list["WorkspaceMemberModel"]] = relationship(
        "WorkspaceMemberModel",
        back_populates="user",
        foreign_keys="WorkspaceMemberModel.user_id",
    )
    created_workspaces: Mapped[list["WorkspaceModel"]] = relationship(
        "WorkspaceModel",
        back_populates="creator",
        foreign_keys="WorkspaceModel.created_by",
    )


class WorkspaceModel(Base):
    """Workspace model."""

    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    creator: Mapped["ProfileModel"] = relationship(
        "ProfileModel",
        back_populates="created_workspaces",
        foreign_keys=[created_by],
    )
    members: Mapped[list["WorkspaceMemberModel"]] = relationship(
        "WorkspaceMemberModel",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    todos: Mapped[list["TodoModel"]] = relationship(
        "TodoModel",
        back_populates="workspace",
        foreign_keys="TodoModel.workspace_id",
    )
    tags: Mapped[list["TagModel"]] = relationship(
        "TagModel",
        back_populates="workspace",
        foreign_keys="TagModel.workspace_id",
    )


class WorkspaceMemberModel(Base):
    """Workspace membership model (composite PK on workspace_id + user_id)."""

    __tablename__ = "workspace_members"

    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint("role IN ('owner', 'admin', 'member', 'viewer')"),
        nullable=False,
        default="member",
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    invited_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL"),
    )

    # Relationships
    workspace: Mapped["WorkspaceModel"] = relationship(
        "WorkspaceModel",
        back_populates="members",
    )
    user: Mapped["ProfileModel"] = relationship(
        "ProfileModel",
        back_populates="workspace_memberships",
        foreign_keys=[user_id],
    )
    inviter: Mapped[Optional["ProfileModel"]] = relationship(
        "ProfileModel",
        foreign_keys=[invited_by],
    )


class TodoModel(Base):
    """Todo/Task model."""

    __tablename__ = "todos"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("todos.id", ondelete="CASCADE"),
        index=True,
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    user: Mapped["ProfileModel"] = relationship("ProfileModel", back_populates="todos")
    workspace: Mapped[Optional["WorkspaceModel"]] = relationship(
        "WorkspaceModel",
        back_populates="todos",
        foreign_keys=[workspace_id],
    )
    parent: Mapped[Optional["TodoModel"]] = relationship(
        "TodoModel",
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[list["TodoModel"]] = relationship(
        "TodoModel",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    tags: Mapped[list["TagModel"]] = relationship(
        "TagModel",
        secondary="todo_tags",
        back_populates="todos",
    )


class TagModel(Base):
    """Tag model."""

    __tablename__ = "tags"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), default="#3B82F6")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["ProfileModel"] = relationship("ProfileModel", back_populates="tags")
    workspace: Mapped[Optional["WorkspaceModel"]] = relationship(
        "WorkspaceModel",
        back_populates="tags",
        foreign_keys=[workspace_id],
    )
    todos: Mapped[list["TodoModel"]] = relationship(
        "TodoModel",
        secondary="todo_tags",
        back_populates="tags",
    )


class TodoTagModel(Base):
    """Association table for Todo-Tag many-to-many relationship."""

    __tablename__ = "todo_tags"

    todo_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("todos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InvitationModel(Base):
    """Workspace invitation model."""

    __tablename__ = "invitations"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "role IN ('admin', 'member', 'viewer')",
            name="ck_invitations_role",
        ),
        nullable=False,
        default="member",
    )
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    invited_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'expired', 'revoked')",
            name="ck_invitations_status",
        ),
        nullable=False,
        default="pending",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    workspace: Mapped["WorkspaceModel"] = relationship("WorkspaceModel")
    inviter: Mapped["ProfileModel"] = relationship("ProfileModel")


class ActivityLogModel(Base):
    """Activity log model for tracking workspace events."""

    __tablename__ = "activity_log"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    workspace: Mapped["WorkspaceModel"] = relationship("WorkspaceModel")
    actor: Mapped["ProfileModel"] = relationship("ProfileModel")


class GroupModel(Base):
    """Workspace group model."""

    __tablename__ = "groups"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    workspace: Mapped["WorkspaceModel"] = relationship("WorkspaceModel")
    creator: Mapped["ProfileModel"] = relationship("ProfileModel")
    members: Mapped[list["GroupMemberModel"]] = relationship(
        "GroupMemberModel",
        back_populates="group",
        cascade="all, delete-orphan",
    )


class GroupMemberModel(Base):
    """Group membership model (composite PK on group_id + user_id)."""

    __tablename__ = "group_members"

    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        CheckConstraint(
            "role IN ('admin', 'member')",
            name="ck_group_members_role",
        ),
        nullable=False,
        default="member",
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    group: Mapped["GroupModel"] = relationship(
        "GroupModel",
        back_populates="members",
    )
    user: Mapped["ProfileModel"] = relationship("ProfileModel")


class NotificationTypeModel(Base):
    """Notification type lookup model."""

    __tablename__ = "notification_types"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    default_channels: Mapped[dict[str, Any]] = mapped_column(JSONB, default=lambda: ["in_app"])
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NotificationModel(Base):
    """Notification event model."""

    __tablename__ = "notifications"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    type_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("notification_types.id"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    notification_type: Mapped["NotificationTypeModel"] = relationship("NotificationTypeModel")
    workspace: Mapped["WorkspaceModel"] = relationship("WorkspaceModel")
    actor: Mapped["ProfileModel"] = relationship("ProfileModel")


class NotificationRecipientModel(Base):
    """Per-user notification delivery model."""

    __tablename__ = "notification_recipients"
    __table_args__ = (UniqueConstraint("notification_id", "recipient_id"),)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    notification_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    notification: Mapped["NotificationModel"] = relationship("NotificationModel")
    recipient: Mapped["ProfileModel"] = relationship("ProfileModel")


class NotificationPreferenceModel(Base):
    """User notification preference model."""

    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("user_id", "workspace_id", "notification_type", "channel"),)

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
    )
    notification_type: Mapped[str | None] = mapped_column(String(50))
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="in_app")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
