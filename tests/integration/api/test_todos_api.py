"""Integration tests for Todos API."""

import pytest
from uuid import uuid4

from httpx import AsyncClient


class TestTodosAPI:
    """Integration tests for Todos API."""

    @pytest.mark.asyncio
    async def test_create_todo(self, authenticated_client: AsyncClient):
        """Test POST /api/v1/todos."""
        response = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "New Task", "description": "Test description"},
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["title"] == "New Task"
        assert data["description"] == "Test description"
        assert data["is_completed"] is False
        assert data["parent_id"] is None
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_todo_minimal(self, authenticated_client: AsyncClient):
        """Test creating todo with only required fields."""
        response = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "Minimal Task"},
        )

        assert response.status_code == 201
        assert response.json()["data"]["title"] == "Minimal Task"

    @pytest.mark.asyncio
    async def test_create_todo_with_parent(self, authenticated_client: AsyncClient):
        """Test creating nested todo."""
        # Create parent
        parent = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "Parent Task"},
        )
        parent_id = parent.json()["data"]["id"]

        # Create child
        response = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "Child Task", "parent_id": parent_id},
        )

        assert response.status_code == 201
        assert response.json()["data"]["parent_id"] == parent_id

    @pytest.mark.asyncio
    async def test_create_todo_validation_error(self, authenticated_client: AsyncClient):
        """Test validation error on invalid input."""
        response = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": ""},  # Empty title
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_todos(self, authenticated_client: AsyncClient):
        """Test GET /api/v1/todos."""
        # Create some todos
        await authenticated_client.post("/api/v1/todos", json={"title": "List Task 1"})
        await authenticated_client.post("/api/v1/todos", json={"title": "List Task 2"})

        response = await authenticated_client.get("/api/v1/todos")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) >= 2
        assert "meta" in data
        assert "total" in data["meta"]

    @pytest.mark.asyncio
    async def test_get_todo(self, authenticated_client: AsyncClient):
        """Test GET /api/v1/todos/{id}."""
        # Create todo
        create = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "Get Test Task"},
        )
        todo_id = create.json()["data"]["id"]

        response = await authenticated_client.get(f"/api/v1/todos/{todo_id}")

        assert response.status_code == 200
        assert response.json()["data"]["id"] == todo_id

    @pytest.mark.asyncio
    async def test_get_todo_not_found(self, authenticated_client: AsyncClient):
        """Test 404 for non-existent todo."""
        response = await authenticated_client.get(f"/api/v1/todos/{uuid4()}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_todo_title(self, authenticated_client: AsyncClient):
        """Test PATCH /api/v1/todos/{id} - update title."""
        # Create todo
        create = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "Original Title"},
        )
        todo_id = create.json()["data"]["id"]

        response = await authenticated_client.patch(
            f"/api/v1/todos/{todo_id}",
            json={"title": "Updated Title"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_todo_complete(self, authenticated_client: AsyncClient):
        """Test completing a todo."""
        # Create todo
        create = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "To Complete"},
        )
        todo_id = create.json()["data"]["id"]

        response = await authenticated_client.patch(
            f"/api/v1/todos/{todo_id}",
            json={"is_completed": True},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["is_completed"] is True
        assert data["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_todo_uncomplete(self, authenticated_client: AsyncClient):
        """Test uncompleting a todo."""
        # Create and complete todo
        create = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "Completed Task"},
        )
        todo_id = create.json()["data"]["id"]
        await authenticated_client.patch(
            f"/api/v1/todos/{todo_id}", json={"is_completed": True}
        )

        # Uncomplete
        response = await authenticated_client.patch(
            f"/api/v1/todos/{todo_id}",
            json={"is_completed": False},
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["is_completed"] is False
        assert data["completed_at"] is None

    @pytest.mark.asyncio
    async def test_delete_todo(self, authenticated_client: AsyncClient):
        """Test DELETE /api/v1/todos/{id}."""
        # Create todo
        create = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "To Delete"},
        )
        todo_id = create.json()["data"]["id"]

        response = await authenticated_client.delete(f"/api/v1/todos/{todo_id}")

        assert response.status_code == 204

        # Verify deleted
        get = await authenticated_client.get(f"/api/v1/todos/{todo_id}")
        assert get.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_todo_not_found(self, authenticated_client: AsyncClient):
        """Test 404 when deleting non-existent todo."""
        response = await authenticated_client.delete(f"/api/v1/todos/{uuid4()}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_todo_cascade(self, authenticated_client: AsyncClient):
        """Test cascade delete removes children."""
        # Create hierarchy
        parent = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Cascade Parent"}
        )
        parent_id = parent.json()["data"]["id"]

        child = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "Cascade Child", "parent_id": parent_id},
        )
        child_id = child.json()["data"]["id"]

        # Delete parent
        await authenticated_client.delete(f"/api/v1/todos/{parent_id}")

        # Child should also be deleted
        assert (
            await authenticated_client.get(f"/api/v1/todos/{parent_id}")
        ).status_code == 404
        assert (
            await authenticated_client.get(f"/api/v1/todos/{child_id}")
        ).status_code == 404


class TestChildCounts:
    """Tests for child_count and completed_child_count fields."""

    @pytest.mark.asyncio
    async def test_leaf_todo_has_zero_counts(self, authenticated_client: AsyncClient):
        """Newly created todo (leaf) has both child counts at 0."""
        response = await authenticated_client.post(
            "/api/v1/todos",
            json={"title": "Leaf Task"},
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["child_count"] == 0
        assert data["completed_child_count"] == 0

    @pytest.mark.asyncio
    async def test_parent_shows_child_count(self, authenticated_client: AsyncClient):
        """Parent with 2 children shows child_count=2, completed_child_count=0."""
        parent = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Parent"}
        )
        parent_id = parent.json()["data"]["id"]

        await authenticated_client.post(
            "/api/v1/todos", json={"title": "Child 1", "parent_id": parent_id}
        )
        await authenticated_client.post(
            "/api/v1/todos", json={"title": "Child 2", "parent_id": parent_id}
        )

        response = await authenticated_client.get(f"/api/v1/todos/{parent_id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["child_count"] == 2
        assert data["completed_child_count"] == 0

    @pytest.mark.asyncio
    async def test_completed_child_count(self, authenticated_client: AsyncClient):
        """Completing 1 of 2 children shows completed_child_count=1."""
        parent = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Parent"}
        )
        parent_id = parent.json()["data"]["id"]

        child1 = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Child 1", "parent_id": parent_id}
        )
        child1_id = child1.json()["data"]["id"]

        await authenticated_client.post(
            "/api/v1/todos", json={"title": "Child 2", "parent_id": parent_id}
        )

        # Complete one child
        await authenticated_client.patch(
            f"/api/v1/todos/{child1_id}", json={"is_completed": True}
        )

        response = await authenticated_client.get(f"/api/v1/todos/{parent_id}")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["child_count"] == 2
        assert data["completed_child_count"] == 1

    @pytest.mark.asyncio
    async def test_child_counts_in_list(self, authenticated_client: AsyncClient):
        """List endpoint includes correct counts for parent and child."""
        parent = await authenticated_client.post(
            "/api/v1/todos", json={"title": "List Parent"}
        )
        parent_id = parent.json()["data"]["id"]

        child = await authenticated_client.post(
            "/api/v1/todos", json={"title": "List Child", "parent_id": parent_id}
        )
        child_id = child.json()["data"]["id"]

        response = await authenticated_client.get("/api/v1/todos")

        assert response.status_code == 200
        todos = {t["id"]: t for t in response.json()["data"]}

        assert todos[parent_id]["child_count"] == 1
        assert todos[parent_id]["completed_child_count"] == 0
        assert todos[child_id]["child_count"] == 0
        assert todos[child_id]["completed_child_count"] == 0

    @pytest.mark.asyncio
    async def test_child_counts_after_update(self, authenticated_client: AsyncClient):
        """Update endpoint returns fresh child counts."""
        parent = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Update Parent"}
        )
        parent_id = parent.json()["data"]["id"]

        child = await authenticated_client.post(
            "/api/v1/todos", json={"title": "Update Child", "parent_id": parent_id}
        )
        child_id = child.json()["data"]["id"]

        # Complete the child
        await authenticated_client.patch(
            f"/api/v1/todos/{child_id}", json={"is_completed": True}
        )

        # Update the parent (e.g. rename) and check counts are fresh
        response = await authenticated_client.patch(
            f"/api/v1/todos/{parent_id}", json={"title": "Updated Parent"}
        )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["child_count"] == 1
        assert data["completed_child_count"] == 1
