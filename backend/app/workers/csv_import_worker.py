"""Dedicated Linux CSV-import worker; no model loading or assessment enqueue capability."""

import argparse
import json
import secrets
import signal
import sys
import threading
from pathlib import Path
from uuid import UUID, uuid4

from app.services.csv_imports import (
    CSVImportService,
    ImportConflict,
    ImportInvalid,
    ImportLeaseLost,
    ImportTimeout,
    ImportUnavailable,
    ImportWorkerDenied,
)
from app.services.csv_staging import UploadDenied, UploadExpired


class CSVImportWorker:
    def __init__(self, service, token):
        if sys.platform != "linux":
            raise ImportUnavailable
        self.service, self.token = service, token

    def run_once(self):
        self.service.recover_expired(self.token)
        claim = self.service.claim(self.token)
        if claim is None:
            return None
        try:
            return self.service.process_chunk(self.token, claim)
        except UploadDenied:
            return self.service.fail(self.token, claim, "authorization_changed", retryable=False)
        except UploadExpired:
            return self.service.fail(self.token, claim, "source_expired", retryable=False)
        except (ImportConflict, ImportInvalid):
            return self.service.fail(self.token, claim, "validation_changed", retryable=False)
        except ImportTimeout:
            return self.service.fail(self.token, claim, "chunk_timeout")
        except (ImportWorkerDenied, ImportLeaseLost):
            raise
        except ImportUnavailable:
            return self.service.fail(self.token, claim, "database_unavailable")
        except Exception:
            return self.service.fail(self.token, claim, "processing_unavailable")


def main():
    from app.core.config import Settings
    from app.core.database import make_engine

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--token-file", default="/run/secrets/csv_import_worker_token")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--admin-id", type=UUID)
    parser.add_argument("--name", default="csv-import-local")
    args = parser.parse_args()
    stop = threading.Event()
    engine = None
    try:
        if sys.platform != "linux":
            raise ImportUnavailable
        settings = Settings(_env_file=None, jwt_secret=secrets.token_urlsafe(48))
        engine = make_engine(settings.database_url)
        service = CSVImportService(engine, settings)
        token = Path(args.token_file).read_text(encoding="ascii").strip()
        if args.register:
            if args.admin_id is None:
                raise ImportInvalid
            service.register_worker(args.admin_id, args.name, token)
            print(json.dumps({"event": "csv.import.worker", "status": "registered"}), flush=True)
            return 0
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        worker = CSVImportWorker(service, token)
        while not stop.is_set():
            try:
                result = worker.run_once()
                print(
                    json.dumps(
                        {
                            "event": "csv.import.worker",
                            "correlation_id": uuid4().hex,
                            "status": result.status if result else "idle",
                        }
                    ),
                    flush=True,
                )
            except ImportWorkerDenied:
                return 1
            except (ImportUnavailable, ImportLeaseLost):
                if args.once:
                    return 1
                stop.wait(5)
            if args.once:
                return 0
            stop.wait(2)
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "event": "csv.import.worker",
                    "correlation_id": uuid4().hex,
                    "status": "unavailable",
                }
            ),
            flush=True,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
