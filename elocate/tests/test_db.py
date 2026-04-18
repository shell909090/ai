"""Tests for VectorDB (uses tmp_path for real LanceDB)."""

from pathlib import Path

import numpy as np
import pytest

from elocate.db import VectorDB

DIM = 8


@pytest.fixture
def db(tmp_path: Path) -> VectorDB:
    d = VectorDB(tmp_path / "index")
    d.init_tables(DIM)
    return d


def _vec() -> list[float]:
    return list(np.random.rand(DIM).astype(np.float32))


# ---- table management ----


def test_tables_exist_after_init(db: VectorDB) -> None:
    assert db.tables_exist()


def test_tables_not_exist_before_init(tmp_path: Path) -> None:
    d = VectorDB(tmp_path / "fresh")
    assert not d.tables_exist()


def test_drop_tables(db: VectorDB) -> None:
    db.drop_tables()
    assert not db.tables_exist()


def test_drop_tables_idempotent(tmp_path: Path) -> None:
    d = VectorDB(tmp_path / "idx")
    d.drop_tables()  # should not raise


def test_init_tables_idempotent(db: VectorDB) -> None:
    db.init_tables(DIM)  # second call should not raise


# ---- files table ----


def test_upsert_and_get_file_meta(db: VectorDB) -> None:
    db.upsert_file_meta("/a/b.md", 100, 1.0, "abc123")
    meta = db.get_file_meta("/a/b.md")
    assert meta is not None
    assert meta["path"] == "/a/b.md"
    assert meta["size"] == 100
    assert meta["mtime"] == 1.0
    assert meta["file_hash"] == "abc123"


def test_get_file_meta_missing(db: VectorDB) -> None:
    assert db.get_file_meta("/nonexistent") is None


def test_upsert_overwrites(db: VectorDB) -> None:
    db.upsert_file_meta("/x.md", 10, 1.0, "old")
    db.upsert_file_meta("/x.md", 20, 2.0, "new")
    meta = db.get_file_meta("/x.md")
    assert meta["file_hash"] == "new"
    assert meta["size"] == 20


def test_delete_file_meta(db: VectorDB) -> None:
    db.upsert_file_meta("/del.md", 1, 1.0, "h1")
    db.delete_file_meta("/del.md")
    assert db.get_file_meta("/del.md") is None


def test_list_indexed_paths(db: VectorDB) -> None:
    db.upsert_file_meta("/a.md", 1, 1.0, "h1")
    db.upsert_file_meta("/b.md", 2, 2.0, "h2")
    paths = db.list_indexed_paths()
    assert set(paths) == {"/a.md", "/b.md"}


def test_get_paths_by_hash(db: VectorDB) -> None:
    db.upsert_file_meta("/orig.md", 1, 1.0, "shared")
    db.upsert_file_meta("/copy.md", 1, 1.0, "shared")
    paths = db.get_paths_by_hash("shared")
    assert set(paths) == {"/orig.md", "/copy.md"}


# ---- chunks table ----


def test_add_and_query_chunks(db: VectorDB) -> None:
    v = _vec()
    db.add_chunks(
        [
            {
                "file_hash": "h1",
                "chunk_index": 0,
                "start": 0,
                "end": 10,
                "content": "hello world",
                "vector": v,
            }
        ]
    )
    results = db.query(v, top_k=5)
    assert len(results) == 1
    assert results[0]["file_hash"] == "h1"
    assert results[0]["content"] == "hello world"
    assert "_distance" in results[0]


def test_hash_has_chunks_true(db: VectorDB) -> None:
    db.add_chunks(
        [
            {
                "file_hash": "hx",
                "chunk_index": 0,
                "start": 0,
                "end": 5,
                "content": "data",
                "vector": _vec(),
            }
        ]
    )
    assert db.hash_has_chunks("hx")


def test_hash_has_chunks_false(db: VectorDB) -> None:
    assert not db.hash_has_chunks("notexist")


def test_delete_chunks_by_hash(db: VectorDB) -> None:
    db.add_chunks(
        [
            {
                "file_hash": "del",
                "chunk_index": 0,
                "start": 0,
                "end": 5,
                "content": "data",
                "vector": _vec(),
            }
        ]
    )
    db.delete_chunks_by_hash("del")
    assert not db.hash_has_chunks("del")


def test_query_top_k_limit(db: VectorDB) -> None:
    for i in range(5):
        db.add_chunks(
            [
                {
                    "file_hash": f"h{i}",
                    "chunk_index": 0,
                    "start": 0,
                    "end": 5,
                    "content": f"chunk {i}",
                    "vector": _vec(),
                }
            ]
        )
    results = db.query(_vec(), top_k=3)
    assert len(results) <= 3


# ---- meta table (B002) ----


def test_set_and_get_meta(db: VectorDB) -> None:
    db.set_meta("embedding_model", "all-MiniLM-L6-v2")
    assert db.get_meta("embedding_model") == "all-MiniLM-L6-v2"


def test_get_meta_missing_key(db: VectorDB) -> None:
    assert db.get_meta("nonexistent_key") is None


def test_set_meta_overwrites(db: VectorDB) -> None:
    db.set_meta("key", "old")
    db.set_meta("key", "new")
    assert db.get_meta("key") == "new"


def test_get_meta_no_table(tmp_path: Path) -> None:
    d = VectorDB(tmp_path / "fresh")
    assert d.get_meta("anything") is None


# ---- B011: paths with special characters ----


def test_file_meta_path_with_single_quote(db: VectorDB) -> None:
    """Paths containing single quotes must be stored and retrieved correctly."""
    path = "/home/user/it's a file.md"
    db.upsert_file_meta(path, 10, 1.0, "abc123")
    meta = db.get_file_meta(path)
    assert meta is not None
    assert meta["path"] == path


def test_delete_file_meta_with_single_quote(db: VectorDB) -> None:
    path = "/tmp/o'reilly.md"
    db.upsert_file_meta(path, 5, 2.0, "def456")
    db.delete_file_meta(path)
    assert db.get_file_meta(path) is None
