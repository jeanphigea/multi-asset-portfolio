import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from store import FileStore  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return FileStore(tmp_path / "store.db", prefix="t:")


@pytest.fixture
def demo_store(store):
    import portfolio as pf
    pf.seed(store)
    return store
