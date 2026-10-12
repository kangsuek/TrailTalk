import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def make_settings(tmp_path):
    def _make(**overrides) -> Settings:
        values = {
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
            "web_dist_dir": tmp_path / "no-dist",
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return _make


@pytest.fixture
def app(make_settings):
    return create_app(make_settings())


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
