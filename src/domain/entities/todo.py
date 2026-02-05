"""Todo domain entity."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class Todo:
    """Domain entity for a Todo/Task."""

    user_id: UUID
    title: str
    id: UUID = field(default_factory=uuid4)
    parent_id: UUID | None = None
    workspace_id: UUID | None = None
    description: str | None = None
    is_completed: bool = False
    position: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    def complete(self) -> None:
        """Mark the todo as completed."""
        self.is_completed = True
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

    def uncomplete(self) -> None:
        """Mark the todo as not completed."""
        self.is_completed = False
        self.completed_at = None
        self.updated_at = datetime.utcnow()

    def __post_init__(self) -> None:
        """Ensure updated_at is always at least as recent as created_at."""
        if self.updated_at < self.created_at:
            self.updated_at = self.created_at
