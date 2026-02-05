"""Tag domain entity."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4


@dataclass
class Tag:
    """Domain entity for a Tag."""

    user_id: UUID
    name: str
    id: UUID = field(default_factory=uuid4)
    workspace_id: Optional[UUID] = None
    color_hex: str = "#3B82F6"  # Default blue
    created_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Validate and normalize color hex."""
        # Ensure color starts with # and is uppercase
        if not self.color_hex.startswith("#"):
            self.color_hex = f"#{self.color_hex}"
        self.color_hex = self.color_hex.upper()


@dataclass(frozen=True, slots=True)
class TagWithCount:
    """Read-only value object: a Tag bundled with its usage count."""

    tag: Tag
    usage_count: int
