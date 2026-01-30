"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
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
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), default="#3B82F6")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["ProfileModel"] = relationship("ProfileModel", back_populates="tags")
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
