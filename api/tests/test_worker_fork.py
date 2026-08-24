"""Forked workers must not share the parent's database connection.

`multiprocessing` forks on Linux, so a child inherits the parent's connection
pool with its sockets. Two processes talking over one connection desync the
wire protocol, which surfaces as `ResourceClosedError` on an ordinary SELECT.

"""

from __future__ import annotations

import multiprocessing
import os

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import Session
from tests.conftest import TEST_DATABASE_URL


def _query(engine, dispose: bool, results) -> None:
    """One child: optionally drop the inherited pool, then query."""
    if dispose:
        engine.dispose(close=False)
    try:
        for _ in range(5):
            with Session(engine) as session:
                session.exec(text("SELECT 1")).first()
        results.put("ok")
    except Exception as exc:  # noqa: BLE001 - the failure is the subject
        results.put(f"{type(exc).__name__}: {exc}")


def _run_children(dispose: bool, count: int = 4) -> list[str]:
    engine = create_engine(TEST_DATABASE_URL)
    # The parent touches the database first, exactly as the keyring check does
    # before `run_worker` forks. The connection returns to the pool still open.
    with Session(engine) as session:
        session.exec(text("SELECT 1")).first()

    context = multiprocessing.get_context("fork")
    results = context.Queue()
    children = [
        context.Process(target=_query, args=(engine, dispose, results))
        for _ in range(count)
    ]
    try:
        for child in children:
            child.start()
        outcomes = [results.get(timeout=30) for _ in children]
        for child in children:
            child.join(timeout=30)
        return outcomes
    finally:
        # This engine is this test's own -- the whole point is to fork across a
        # pool it built. Dispose it so it does not leak connections into the
        # shared test database.
        engine.dispose()


def test_disposing_the_inherited_pool_keeps_forked_children_working():
    """What `_worker_loop` does on entry."""
    assert _run_children(dispose=True) == ["ok"] * 4


def test_the_worker_loop_disposes_before_touching_the_database():
    """Pin the call itself: the fix is one line and easy to delete.

    Asserted by source rather than behavior because reproducing the corruption
    through `run_worker` would need a live job queue and a real reconcile.
    """
    import inspect

    from app import worker

    source = inspect.getsource(worker._worker_loop)
    assert "dispose(close=False)" in source
    assert source.index("dispose(close=False)") < source.index("while not shutdown")
