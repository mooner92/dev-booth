from __future__ import annotations

import time

from dashboard.backend.services.session_registry import SessionListCache


def test_lists_existing_sessions(make_session, tmp_sessions_root):
    make_session("alpha")
    make_session("beta")
    cache = SessionListCache(sessions_root=tmp_sessions_root, ttl_s=5.0)
    listing = cache.list()
    names = {s.name for s in listing}
    assert names == {"alpha", "beta"}


def test_ttl_cache_hits(make_session, tmp_sessions_root):
    make_session("alpha")
    cache = SessionListCache(sessions_root=tmp_sessions_root, ttl_s=5.0)
    first = cache.list()

    # Add another session — cache should still return only alpha until TTL expires
    make_session("beta")
    second = cache.list()
    assert {s.name for s in second} == {s.name for s in first}

    cache.invalidate()
    third = cache.list()
    assert {s.name for s in third} == {"alpha", "beta"}


def test_ttl_expiry(make_session, tmp_sessions_root):
    make_session("alpha")
    cache = SessionListCache(sessions_root=tmp_sessions_root, ttl_s=0.05)
    cache.list()
    make_session("beta")
    time.sleep(0.1)
    listing = cache.list()
    assert {s.name for s in listing} == {"alpha", "beta"}
