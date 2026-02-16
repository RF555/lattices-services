"""Tests for health check endpoints."""

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        """Test that health endpoint returns 200 OK."""
        response = await client.get("/health")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_correct_structure(self, client: AsyncClient) -> None:
        """Test that health endpoint returns expected structure."""
        response = await client.get("/health")
        data = response.json()

        assert "status" in data
        assert "version" in data
        assert "timestamp" in data
        assert "environment" in data

    @pytest.mark.asyncio
    async def test_health_status_is_healthy(self, client: AsyncClient) -> None:
        """Test that health status is 'healthy'."""
        response = await client.get("/health")
        data = response.json()

        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_version_format(self, client: AsyncClient) -> None:
        """Test that version has expected format."""
        response = await client.get("/health")
        data = response.json()

        # Check version follows semver pattern
        assert data["version"] == "1.0.0"
