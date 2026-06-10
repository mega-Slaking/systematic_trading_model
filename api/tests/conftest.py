"""Fixtures for the API test suite.

Importing ``api._bootstrap`` (transitively, via ``api.main``) puts the repo root
and ``src/`` on ``sys.path``, so these tests run from anywhere. The repo's
``pytest.ini`` (``pythonpath = .``, ``testpaths = tests``) does not collect
``api/tests`` by default -- run them explicitly, e.g.::

    python -m pytest api/tests
"""

from __future__ import annotations

import warnings

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


def pytest_configure(config: pytest.Config) -> None:
    """Silence two known, harmless third-party deprecation warnings (Phase 0).

    1. Starlette's ``TestClient`` warns that ``httpx`` is deprecated in favor of
       ``httpx2`` -- a Starlette-internal migration note, not our code.
    2. FastAPI 0.136 warns that a custom ``ORJSONResponse`` class is "not
       required". We keep it on purpose (NaN -> null safety net, see
       ``test_app_response_class_degrades_raw_nan_to_null`` and ``api/main.py``).

    Scoped here so the root suite's warning policy is untouched.
    """
    warnings.filterwarnings(
        "ignore",
        message="Using `httpx` with `starlette.testclient` is deprecated.*",
    )
    warnings.filterwarnings("ignore", message="ORJSONResponse is deprecated.*")


@pytest.fixture
def client() -> TestClient:
    """A FastAPI ``TestClient`` over a freshly built app instance."""
    return TestClient(create_app())
