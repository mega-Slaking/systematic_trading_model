"""Import-root bootstrap for the API process.

The existing core mixes import roots (verified in the design spec, §3.3):

* ``src/storage/db_reader.py`` does ``from src.storage.paths import ...`` -> it
  needs the **repo root** on ``sys.path``.
* ``src/accounting/tearsheet_builder.py`` does ``from accounting.tearsheet_models
  import ...`` -> it needs **``src/``** on ``sys.path`` (``accounting`` lives at
  ``src/accounting``).

So the API process must have *both* the repo root and ``src/`` on ``sys.path``
before any ``src.*`` / ``accounting.*`` import is attempted. Importing this
module performs that insertion as an idempotent side effect. It is imported at
the very top of ``api.config`` and ``api.main`` so the paths are set up before
anything else in the package resolves a core import.

This mirrors what the test harness (``pytest.ini`` ``pythonpath = .``) and the
Streamlit app do, but makes it explicit and CWD-independent: the roots are
derived from this file's location, not from where ``uvicorn`` was launched.
"""

from __future__ import annotations

import sys
from pathlib import Path

# api/_bootstrap.py -> parents[1] is the repo root (sibling of src/, streamlit/).
REPO_ROOT: Path = Path(__file__).resolve().parents[1]
SRC_ROOT: Path = REPO_ROOT / "src"


def ensure_import_roots() -> None:
    """Idempotently put the repo root and ``src/`` at the front of ``sys.path``.

    Front-insert (rather than append) so the project's own packages win over any
    similarly named site-packages, matching the engine's existing expectations.
    """
    for root in (SRC_ROOT, REPO_ROOT):
        resolved = str(root)
        if resolved not in sys.path:
            sys.path.insert(0, resolved)


ensure_import_roots()
