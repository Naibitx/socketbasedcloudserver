# analytics.py
import time
import csv
import os
from threading import Lock

LOG_FILE = "network_stats.csv"
_LOCK = Lock()

_FIELDNAMES = [
    "timestamp",
    "role",
    "operation",
    "command",
    "file_name",
    "bytes",
    "duration_sec",
    "data_rate_MBps",
    "status",
    "note",
    "start_clock",
    "end_clock",
]


def now():
    """
    High-resolution timer for measuring durations.
    Use now() at the start and end of an operation.
    """
    return time.perf_counter()


def _write_row(row: dict):
    """Internal helper to append one row to the CSV in a thread-safe way."""
    file_exists = os.path.isfile(LOG_FILE)

    with _LOCK:
        with open(LOG_FILE, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)


def record_transfer(
    role: str,
    op_type: str,
    file_name: str,
    num_bytes: int,
    start: float,
    end: float,
    status: str = "OK",
    note: str = "",
):
    """
    Record a file transfer (UPLOAD or DOWNLOAD).

    role     : "client" or "server"
    op_type  : "UPLOAD" or "DOWNLOAD"
    num_bytes: total bytes transferred
    start/end: timestamps from now()
    """
    duration = max(end - start, 0.0)
    data_rate = 0.0
    if duration > 0 and num_bytes is not None:
        # bytes/sec -> MB/sec
        data_rate = num_bytes / duration / (1024 * 1024)

    row = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "role": role,
        "operation": op_type,
        "command": "",
        "file_name": file_name,
        "bytes": num_bytes,
        "duration_sec": round(duration, 6),
        "data_rate_MBps": round(data_rate, 6),
        "status": status,
        "note": note,
        "start_clock": start,
        "end_clock": end,
    }
    _write_row(row)


def record_event(
    role: str,
    event: str,
    start: float,
    end: float,
    status: str = "OK",
    note: str = "",
):
    """
    Record a non-file operation, e.g. DIR / DELETE / SUBFOLDER,
    or general system response time.

    role : "client" or "server"
    event: name of the command (e.g. "DIR", "DELETE", "SERVER_START")
    """
    duration = max(end - start, 0.0)

    row = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "role": role,
        "operation": "EVENT",
        "command": event,
        "file_name": "",
        "bytes": 0,
        "duration_sec": round(duration, 6),
        "data_rate_MBps": 0.0,
        "status": status,
        "note": note,
        "start_clock": start,
        "end_clock": end,
    }
    _write_row(row)