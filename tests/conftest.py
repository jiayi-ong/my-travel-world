"""
Shared pytest fixtures for all test modules.

Fixtures:
    seeded_world: A fully generated WorldState with seed=42 (shared across tests).
    test_client: FastAPI TestClient with a loaded world.
    session_service: A fresh SessionService instance.
"""
import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import tempfile

@pytest.fixture(scope="session")
def tmp_worlds_root():
    """Temporary directory for test world files. Cleaned up after test session."""
    # TODO: yield Path(tempfile.mkdtemp(prefix="tw_test_"))
    pass

@pytest.fixture(scope="session")
def seeded_world(tmp_worlds_root):
    """
    Generate a deterministic test world with seed=42.
    Generated once per test session (slow fixture).
    """
    # TODO: from travel_world.manager.world_manager import WorldManager
    # TODO: wm = WorldManager(tmp_worlds_root)
    # TODO: world_state = wm.create_world(seed=42)
    # TODO: yield world_state
    pass

@pytest.fixture
def test_client(tmp_worlds_root, seeded_world):
    """FastAPI TestClient with the test world pre-loaded."""
    # TODO: from travel_world.api.app import create_app
    # TODO: app = create_app(worlds_root=str(tmp_worlds_root))
    # TODO: with TestClient(app) as client:
    #           # Load the world via the API
    #           client.post(f"/world/{seeded_world.world_id}/load")
    #           yield client
    pass

@pytest.fixture
def session_service():
    """Fresh in-memory SessionService for unit tests."""
    # TODO: from travel_world.services.session_service import SessionService
    # TODO: return SessionService()
    pass
