"""Small transactional document adapter. Reads precede buffered writes.

Callbacks must have no network side effects: Firestore can retry them.
"""
from google.cloud import firestore
from google.cloud.firestore import FieldFilter
from app.infrastructure.firestore.watched_query import WatchedQuery


class FirestoreStore:
    def __init__(self, db):
        self.db = db
        self._work_queries = {}

    def work_scan(self, collection, filters):
        # Only fixed, global worker queries are watched. User-facing reads and
        # transactions always go directly to Firestore.
        if collection not in self._work_queries:
            query = self.db.collection(collection)
            for field, op, value in filters:
                query = query.where(filter=FieldFilter(field, op, value))
            self._work_queries[collection] = WatchedQuery(query)
        return self._work_queries[collection].read()

    def close(self):
        for query in self._work_queries.values():
            query.close()
        self._work_queries.clear()

    def read(self, path):
        return self.db.document(path).get().to_dict()

    def scan(self, collection, filters=()):
        query = self.db.collection(collection)
        for field, op, value in filters:
            query = query.where(filter=FieldFilter(field, op, value))
        return [s.to_dict() for s in query.stream()]

    def atomic(self, callback):
        @firestore.transactional
        def run(transaction):
            view = TransactionView(self.db, transaction)
            result = callback(view)
            for path, data in view.writes.items():
                transaction.set(self.db.document(path), data)
            return result
        return run(self.db.transaction())


class TransactionView:
    def __init__(self, db, transaction):
        self.db, self.transaction, self.writes = db, transaction, {}

    def get(self, path):
        if path in self.writes:
            return dict(self.writes[path])
        return self.db.document(path).get(transaction=self.transaction).to_dict()

    def set(self, path, data):
        self.writes[path] = dict(data)

    def query(self, collection, filters):
        query = self.db.collection(collection)
        for field, op, value in filters:
            query = query.where(filter=FieldFilter(field, op, value))
        return [s.to_dict() for s in self.transaction.get(query)]
