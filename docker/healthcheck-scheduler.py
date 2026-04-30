"""Docker healthcheck for the scheduler container.

Exits 0 if the heartbeat file was written within the last 3 minutes, 1 otherwise.
Called by the docker-compose healthcheck; never imported by application code.
"""
import json
import sys
from datetime import datetime

HEARTBEAT = "/data/scheduler_heartbeat.json"
MAX_AGE_SECONDS = 180

try:
    with open(HEARTBEAT) as f:
        d = json.load(f)
    ts = datetime.fromisoformat(d["timestamp"])
    age = (datetime.now().astimezone() - ts).total_seconds()
    sys.exit(0 if age < MAX_AGE_SECONDS else 1)
except Exception:
    sys.exit(1)
