"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class ProfileModel(Base):
    """User profile model (synced from Supabase)."""

    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # Relationships
    todos: Mapped[List["TodoModel"]] = relationship(
        "TodoModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    tags: Mapped[List["TagModel"]] = relationship(
        "TagModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    workspace_memberships: Mapped[List["WorkspaceMemberModel"]] = relationship(
        "WorkspaceMemberModel",
        back_populates="user",
        foreign_keys="WorkspaceMemberModel.user_id",
    )
    created_workspaces: Mapped[List["WorkspaceModel"]] = relationship(
        "WorkspaceModel",
        back_populates="creator",
        foreign_keys="WorkspaceModel.created_by",
    )


class WorkspaceModel(Base):
    """Workspace model."""

    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    settings: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict)
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
    members: Mapped[List["WorkspaceMemberModel"]] = relationship(
        "WorkspaceMemberModel",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    todos: Mapped[List["TodoModel"]] = relationship(
        "TodoModel",
        back_populates="workspace",
        foreign_keys="TodoModel.workspace_id",
    )
    tags: Mapped[List["TagModel"]] = relationship(
        "TagModel",
        back_populates="workspace",
        foreign_keys="TagModel.workspace_id",
    )


class WorkspaceMemberModel(Base):
    """Workspace membership model (composite PK on workspace_id + user_id)."""

    __tablename__ = "workspace_members"

    workspace_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
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
    invited_by: Mapped[Optional[str]] = mapped_column(
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

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("todos.id", ondelete="CASCADE"),
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

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
    children: Mapped[List["TodoModel"]] = relationship(
        "TodoModel",
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    tags: Mapped[List["TagModel"]] = relationship(
        "TagModel",
        secondary="todo_tags",
        back_populates="todos",
    )


class TagModel(Base):
    """Tag model."""

    __tablename__ = "tags"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    user_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[Optional[str]] = mapped_column(
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
    todos: Mapped[List["TodoModel"]] = relationship(
        "TodoModel",
        secondary="todo_tags",
        back_populates="tags",
    )


class TodoTagModel(Base):
    """Association table for Todo-Tag many-to-many relationship."""

    __tablename__ = "todo_tags"

    todo_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("todos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InvitationModel(Base):
    """Workspace invitation model."""

    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workspace_id: Mapped[str] = mapped_column(
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
    invited_by: Mapped[str] = mapped_column(
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
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    workspace: Mapped["WorkspaceModel"] = relationship("WorkspaceModel")
    inviter: Mapped["ProfileModel"] = relationship("ProfileModel")


class ActivityLogModel(Base):
    """Activity log model for tracking workspace events."""

    __tablename__ = "activity_log"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workspace_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    changes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSONB
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relationships
    workspace: Mapped["WorkspaceModel"] = relationship("WorkspaceModel")
    actor: Mapped["ProfileModel"] = relationship("ProfileModel")


class GroupModel(Base):
    """Workspace group model."""

    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    workspace_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    workspace: Mapped["WorkspaceModel"] = relationship("WorkspaceModel")
    creator: Mapped["ProfileModel"] = relationship("ProfileModel")
    members: Mapped[List["GroupMemberModel"]] = relationship(
        "GroupMemberModel",
        back_populates="group",
        cascade="all, delete-orphan",
    )


class GroupMemberModel(Base):
    """Group membership model (composite PK on group_id + user_id)."""

    __tablename__ = "group_members"

    group_id: Mapped[str] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(
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
