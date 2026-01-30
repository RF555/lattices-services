"""Integration tests for Tags API."""

import pytest
from uuid import uuid4

from httpx import AsyncClient


class TestTagsAPI:
    """Integration tests for Tag CRUD."""

    @pytest.mark.asyncio
    async def test_create_tag(self, authenticated_client: AsyncClient):
        """Test POST /api/v1/tags."""
        response = await authenticated_client.post(
            "/api/v1/tags",
            json={"name": "work", "color_hex": "#3B82F6"},
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "work"
        assert data["color_hex"] == "#3B82F6"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_tag_default_color(self, authenticated_client: AsyncClient):
        """Test creating tag with default color."""
        response = await authenticated_client.post(
            "/api/v1/tags",
            json={"name": "default-color-tag"},
        )

        assert response.status_code == 201
        assert response.json()["data"]["color_hex"] == "#3B82F6"

    @pytest.mark.asyncio
    async def test_create_duplicate_tag(self, authenticated_client: AsyncClient):
        """Test creating tag with duplicate name returns 409."""
        await authenticated_client.post(
            "/api/v1/tags", json={"name": "duplicate-test"}
        )
        response = await authenticated_client.post(
            "/api/v1/tags", json={"name": "duplicate-test"}
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "DUPLICATE_TAG"

    @pytest.mark.asyncio
    async def test_list_tags(self, authenticated_client: AsyncClient):
        """Test GET /api/v1/tags."""
        await authenticated_client.post("/api/v1/tags", json={"name": "list-tag-1"})
        await authenticated_client.post("/api/v1/tags", json={"name": "list-tag-2"})

        response = await authenticated_client.get("/api/v1/tags")

        assert response.status_code == 200
        assert len(response.json()["data"]) >= 2

    @pytest.mark.asyncio
    async def test_update_tag_name(self, authenticated_client: AsyncClient):
        """Test PATCH /api/v1/tags/{id}."""
        create = await authenticated_client.post(
            "/api/v1/tags", json={"name": "old-name"}
        )
        tag_id = create.json()["data"]["id"]

        response = await authenticated_client.patch(
            f"/api/v1/tags/{tag_id}",
            json={"name": "new-name"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "new-name"

    @pytest.mark.asyncio
    async def test_update_tag_color(self, authenticated_client: AsyncClient):
        """Test updating tag color."""
        create = await authenticated_client.post(
            "/api/v1/tags", json={"name": "color-update"}
        )
        tag_id = create.json()["data"]["id"]

        response = await authenticated_client.patch(
            f"/api/v1/tags/{tag_id}",
            json={"color_hex": "#FF0000"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["color_hex"] == "#FF0000"

    @pytest.mark.asyncio
    async def test_delete_tag(self, authenticated_client: AsyncClient):
        """Test DELETE /api/v1/tags/{id}."""
        create = await authenticated_client.post(
            "/api/v1/tags", json={"name": "to-delete-tag"}
        )
        tag_id = create.json()["data"]["id"]

        response = await authenticated_client.delete(f"/api/v1/tags/{tag_id}")
        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_nonexistent_tag(self, authenticated_client: AsyncClient):
        """Test deleting non-existent tag."""
        response = await authenticated_client.delete(f"/api/v1/tags/{uuid4()}")
        assert response.status_code == 404


class TestTodoTagsAPI:
    """Integration tests for Todo-Tag relationships."""

    @pytest.mark.asyncio
    async def test_attach_tag_to_todo(self, authenticated_client: AsyncClient):
        """Test POST /api/v1/todos/{id}/tags."""
        # Create tag and todo
        tag = await authenticated_client.post(
            "/api/v1/tags", json={"name": "attach-test"}
        )
        tag_id = tag.json()["data"]["id"]

        todo = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Tag Attach Test"}
        )
        todo_id = todo.json()["data"]["id"]

        # Attach
        response = await authenticated_client.post(
            f"/api/v1/todos/{todo_id}/tags",
            json={"tag_id": tag_id},
        )

        assert response.status_code == 201
        assert response.json()["tag_id"] == tag_id
        assert response.json()["todo_id"] == todo_id

    @pytest.mark.asyncio
    async def test_get_todo_tags(self, authenticated_client: AsyncClient):
        """Test GET /api/v1/todos/{id}/tags."""
        # Create tag and todo
        tag = await authenticated_client.post(
            "/api/v1/tags", json={"name": "get-todo-tags-test"}
        )
        tag_id = tag.json()["data"]["id"]

        todo = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Get Tags Test"}
        )
        todo_id = todo.json()["data"]["id"]

        # Attach
        await authenticated_client.post(
            f"/api/v1/todos/{todo_id}/tags",
            json={"tag_id": tag_id},
        )

        # Get tags for todo
        response = await authenticated_client.get(f"/api/v1/todos/{todo_id}/tags")

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1
        assert response.json()["data"][0]["name"] == "get-todo-tags-test"

    @pytest.mark.asyncio
    async def test_detach_tag_from_todo(self, authenticated_client: AsyncClient):
        """Test DELETE /api/v1/todos/{id}/tags/{tag_id}."""
        # Create and attach
        tag = await authenticated_client.post(
            "/api/v1/tags", json={"name": "detach-test"}
        )
        tag_id = tag.json()["data"]["id"]

        todo = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Detach Test"}
        )
        todo_id = todo.json()["data"]["id"]

        await authenticated_client.post(
            f"/api/v1/todos/{todo_id}/tags",
            json={"tag_id": tag_id},
        )

        # Detach
        response = await authenticated_client.delete(
            f"/api/v1/todos/{todo_id}/tags/{tag_id}"
        )
        assert response.status_code == 204

        # Verify detached
        tags = await authenticated_client.get(f"/api/v1/todos/{todo_id}/tags")
        assert len(tags.json()["data"]) == 0

    @pytest.mark.asyncio
    async def test_todo_includes_tags(self, authenticated_client: AsyncClient):
        """Test that todo list includes tags."""
        # Create tag and todo
        tag = await authenticated_client.post(
            "/api/v1/tags", json={"name": "included-tag"}
        )
        tag_id = tag.json()["data"]["id"]

        todo = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Includes Tags Test"}
        )
        todo_id = todo.json()["data"]["id"]

        # Attach
        await authenticated_client.post(
            f"/api/v1/todos/{todo_id}/tags",
            json={"tag_id": tag_id},
        )

        # Get todo - should include tags
        response = await authenticated_client.get(f"/api/v1/todos/{todo_id}")
        data = response.json()["data"]
        assert len(data["tags"]) == 1
        assert data["tags"][0]["name"] == "included-tag"

    @pytest.mark.asyncio
    async def test_filter_todos_by_tag(self, authenticated_client: AsyncClient):
        """Test filtering todos by tag_id query parameter."""
        # Create tag
        tag = await authenticated_client.post(
            "/api/v1/tags", json={"name": "filter-tag"}
        )
        tag_id = tag.json()["data"]["id"]

        # Create 2 todos, tag only one
        tagged = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Tagged Task"}
        )
        tagged_id = tagged.json()["data"]["id"]

        await authenticated_client.post(
            "/api/v1/todos", json={"title": "Untagged Task"}
        )

        await authenticated_client.post(
            f"/api/v1/todos/{tagged_id}/tags",
            json={"tag_id": tag_id},
        )

        # Filter
        response = await authenticated_client.get(f"/api/v1/todos?tag_id={tag_id}")
        data = response.json()["data"]

        # Only the tagged task should appear
        tagged_titles = [t["title"] for t in data]
        assert "Tagged Task" in tagged_titles
        # Untagged should not be in filtered results
        assert all(len(t["tags"]) > 0 for t in data)
