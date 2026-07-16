from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock

from fastapi import HTTPException


_events: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def enforce_rate_limit(user_id: str, limit: int) -> None:
    now = datetime.now(timezone.utc).timestamp()
    with _lock:
        bucket = _events[user_id]
        while bucket and bucket[0] <= now - 60:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(status_code=429, detail={"code": "rate_limit_exceeded", "message": "Too many requests"})
        bucket.append(now)
