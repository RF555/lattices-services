"""Profile domain entity."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class Profile:
    """Domain entity for user profile (synced from Supabase)."""

    id: UUID = field(default_factory=uuid4)
    email: str = ""
    display_name: str | None = None
    avatar_url: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Ensure updated_at is always at least as recent as created_at."""
        if self.updated_at < self.created_at:
            self.updated_at = self.created_at
