"""In-process data store with optional write-through persistence to Firestore.

The app runs as ONE instance (Cloud Run min 1, max 1). That lets every read come from memory,
so polling desks and boards cost nothing, while every write is also saved to Firestore (when
STORE=firestore) so a restart does not lose the demo. On start the store reloads from Firestore.

Collections: cases, tips, referrals, partners, media, audit, officers, counters.
"""
import copy
import queue
import threading
import time


class Store:
    def __init__(self, persister=None):
        self.lock = threading.RLock()
        self.data = {}
        self.counters = {}
        self.version = 0
        self.persister = persister

    # -- loading -----------------------------------------------------------------
    def load(self):
        if not self.persister:
            return
        docs, counters = self.persister.load_all()
        with self.lock:
            self.data = docs
            self.counters = counters
            self.version += 1

    # -- basic operations --------------------------------------------------------
    def _coll(self, name):
        return self.data.setdefault(name, {})

    def put(self, coll, doc):
        with self.lock:
            self._coll(coll)[doc["id"]] = doc
            self.version += 1
            if self.persister:
                self.persister.save(coll, doc["id"], doc)
        return doc

    def get(self, coll, doc_id):
        with self.lock:
            doc = self._coll(coll).get(doc_id)
            return copy.deepcopy(doc) if doc is not None else None

    def all(self, coll):
        with self.lock:
            return [copy.deepcopy(d) for d in self._coll(coll).values()]

    def patch(self, coll, doc_id, fn):
        """Run fn(doc) on the stored document under the lock, then persist it. Returns a copy."""
        with self.lock:
            doc = self._coll(coll).get(doc_id)
            if doc is None:
                return None
            fn(doc)
            self.version += 1
            if self.persister:
                self.persister.save(coll, doc_id, doc)
            return copy.deepcopy(doc)

    def next_seq(self, name):
        with self.lock:
            self.counters[name] = self.counters.get(name, 0) + 1
            if self.persister:
                self.persister.save_counter(name, self.counters[name])
            return self.counters[name]

    def clear(self):
        with self.lock:
            self.data = {}
            self.counters = {}
            self.version += 1
            if self.persister:
                self.persister.clear()

    def snapshot_version(self):
        with self.lock:
            return self.version


class FirestorePersister:
    """Write-through persistence on a background thread so requests never wait on Firestore."""

    def __init__(self, project, prefix="saps_"):
        from google.cloud import firestore  # imported lazily so memory mode needs no GCP libs

        self.db = firestore.Client(project=project)
        self.prefix = prefix
        self.q = queue.Queue()
        self.failed = 0
        threading.Thread(target=self._worker, daemon=True).start()

    def _col(self, name):
        return self.db.collection(self.prefix + name)

    def _worker(self):
        while True:
            op, args = self.q.get()
            try:
                if op == "save":
                    coll, doc_id, doc = args
                    self._col(coll).document(doc_id).set(doc)
                elif op == "counter":
                    name, value = args
                    self._col("counters").document(name).set({"value": value})
                elif op == "clear":
                    for coll in ("cases", "tips", "referrals", "partners", "media", "audit", "officers", "shifts", "counters"):
                        for snap in self._col(coll).stream():
                            snap.reference.delete()
            except Exception as exc:  # never crash the worker; the in-memory copy stays correct
                self.failed += 1
                print(f"[firestore] {op} failed: {type(exc).__name__}: {exc}", flush=True)
            finally:
                self.q.task_done()

    def save(self, coll, doc_id, doc):
        self.q.put(("save", (coll, doc_id, copy.deepcopy(doc))))

    def save_counter(self, name, value):
        self.q.put(("counter", (name, value)))

    def clear(self):
        self.q.put(("clear", ()))

    def load_all(self):
        docs, counters = {}, {}
        for coll in ("cases", "tips", "referrals", "partners", "media", "audit", "officers", "shifts"):
            docs[coll] = {s.id: s.to_dict() for s in self._col(coll).stream()}
        for snap in self._col("counters").stream():
            counters[snap.id] = (snap.to_dict() or {}).get("value", 0)
        return docs, counters


def now():
    return time.time()
