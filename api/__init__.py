"""FastAPI analytics service.

A read-only HTTP/JSON layer that sits between the existing Python trading and
analytics core (``src/``) and the React SPA in ``frontend/``. It reuses the
existing compute (DB readers, ``build_tearsheet``, the ``StrategyConfig``
registry) and exposes it as REST. See ``docs/fastapi_react_migration_spec.md``.

Phase 0 scaffold: only the ``/health`` probe is wired; no business endpoints.
"""
