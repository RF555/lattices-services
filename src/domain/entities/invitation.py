"""Invitation domain entity."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4


class InvitationStatus(StrEnum):
    """Status of a workspace invitation."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


# Default invitation expiry: 7 days
INVITATION_EXPIRY_DAYS = 7


@dataclass
class Invitation:
    """Domain entity for a workspace invitation."""

    workspace_id: UUID
    email: str
    role: str
    token_hash: str
    invited_by: UUID
    id: UUID = field(default_factory=uuid4)
    status: InvitationStatus = InvitationStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(
        default_factory=lambda: datetime.utcnow() + timedelta(days=INVITATION_EXPIRY_DAYS)
    )
    accepted_at: datetime | None = None

    @property
    def is_expired(self) -> bool:
        """Check if the invitation has expired."""
        return datetime.utcnow() > self.expires_at

    @property
    def is_pending(self) -> bool:
        """Check if the invitation is still pending and not expired."""
        return self.status == InvitationStatus.PENDING and not self.is_expired

    def accept(self) -> None:
        """Mark the invitation as accepted."""
        self.status = InvitationStatus.ACCEPTED
        self.accepted_at = datetime.utcnow()

    def revoke(self) -> None:
        """Mark the invitation as revoked."""
        self.status = InvitationStatus.REVOKED
