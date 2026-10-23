"""Live candidate lists for workers; transactions remain the source of truth.

Keep the worker's original clock cadence without paying for a query every tick.
A periodic authoritative read also recovers from a silently stalled listener.
Never use these snapshots for authorization or final state transitions.
"""
from copy import deepcopy
from threading import Lock
from time import monotonic
from app.core.logging import logger


class WatchedQuery:
    def __init__(self, query, *, reconcile_seconds=60, clock=monotonic):
        self.query = query
        self.reconcile_seconds = reconcile_seconds
        self.clock = clock
        self._lock = Lock()
        self._read_lock = Lock()
        self._watch = None
        self._rows = None
        self._revision = 0
        self._next_reconcile = 0
        self._next_connect = 0
        self._connect_failures = 0

    def _snapshot(self, documents, changes, read_time):
        rows = [dict(document.to_dict() or {}, _document_id=document.id)
                for document in documents]
        with self._lock:
            self._rows = rows
            self._revision += 1

    def read(self):
        # Called in a worker thread. Serialize reconnects and fallback queries.
        with self._read_lock:
            now = self.clock()
            if self._watch is None or not self._watch.is_active:
                self._close_watch()
                with self._lock:
                    self._rows = None
                if now >= self._next_connect:
                    self._connect_failures = min(self._connect_failures + 1, 7)
                    self._next_connect = now + min(60, 2 ** (self._connect_failures - 1))
                    try:
                        self._watch = self.query.on_snapshot(self._snapshot)
                    except Exception:
                        logger.exception('Firestore listener unavailable; using direct worker query')
            with self._lock:
                active = self._watch is not None and self._watch.is_active
                if active and self._rows is not None and now < self._next_reconcile:
                    self._connect_failures = 0
                    return deepcopy(self._rows)
                revision = self._revision
            # No SDK retry storm on 429; the caller owns bounded retry/backoff.
            rows = [dict(document.to_dict() or {}, _document_id=document.id)
                    for document in self.query.stream(retry=None, timeout=3)]
            with self._lock:
                # Do not overwrite a newer snapshot delivered during the RPC.
                if self._revision == revision:
                    self._rows = rows
                self._next_reconcile = self.clock() + self.reconcile_seconds
                return deepcopy(self._rows)

    def _close_watch(self):
        if self._watch is not None:
            self._watch.unsubscribe()
            self._watch = None

    def close(self):
        with self._read_lock:
            self._close_watch()
            with self._lock:
                self._rows = None
                self._next_reconcile = 0
                self._next_connect = 0
                self._connect_failures = 0
