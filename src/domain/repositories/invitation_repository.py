"""Invitation repository protocol."""

from typing import List, Optional, Protocol
from uuid import UUID

from domain.entities.invitation import Invitation, InvitationStatus


class IInvitationRepository(Protocol):
    """Repository interface for Invitation entities."""

    async def create(self, invitation: Invitation) -> Invitation:
        """Create a new invitation."""
        ...

    async def get_by_token_hash(self, token_hash: str) -> Optional[Invitation]:
        """Get an invitation by its hashed token."""
        ...

    async def get_for_workspace(self, workspace_id: UUID) -> List[Invitation]:
        """Get all invitations for a workspace."""
        ...

    async def get_for_email(self, email: str) -> List[Invitation]:
        """Get all invitations for an email address."""
        ...

    async def get_pending_for_email(self, email: str) -> List[Invitation]:
        """Get all pending (non-expired) invitations for an email address."""
        ...

    async def get_pending_for_workspace_email(
        self, workspace_id: UUID, email: str
    ) -> Optional[Invitation]:
        """Get a pending invitation for a specific workspace and email."""
        ...

    async def update_status(
        self, id: UUID, status: InvitationStatus
    ) -> Invitation:
        """Update the status of an invitation."""
        ...

    async def delete(self, id: UUID) -> bool:
        """Delete an invitation."""
        ...

    async def expire_old_invitations(self) -> int:
        """Mark all expired pending invitations. Returns count of updated rows."""
        ...
