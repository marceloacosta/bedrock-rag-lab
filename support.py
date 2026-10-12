"""Budget reservations, result serialization, and answer validation."""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import uuid

def now():
    return datetime.now(timezone.utc).isoformat()

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)

def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

class BudgetExceeded(RuntimeError):
    pass

class Budget:
    """Persistent reservations cover every attempted call, including uncertain failures."""
    def __init__(self, path, max_usd, max_calls):
        self.path, self.max_usd, self.max_calls = Path(path), max_usd, max_calls
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads(self.path.read_text()) if self.path.exists() else {"calls": []}
            yield data
            write_json(self.path, data)

    @staticmethod
    def charge(call):
        return call.get("actual_estimated_usd", call["reserved_usd"])

    def reserve(self, usd, trial_id):
        with self.locked() as data:
            if not math.isfinite(usd) or usd <= 0:
                raise ValueError("Invalid reservation")
            if len(data["calls"]) >= self.max_calls:
                raise BudgetExceeded("Project call limit reached")
            if sum(self.charge(c) for c in data["calls"]) + usd > self.max_usd:
                raise BudgetExceeded("Project model-cost limit reached")
            key = str(uuid.uuid4())
            data["calls"].append({"id": key, "trial_id": trial_id, "at": now(),
                                  "reserved_usd": usd, "status": "reserved"})
            return key

    def settle(self, key, usd):
        with self.locked() as data:
            call = next(c for c in data["calls"] if c["id"] == key)
            call.update(actual_estimated_usd=usd, status="measured")

    def summary(self):
        with self.locked() as data:
            return {"attempted_model_calls": len(data["calls"]),
                    "estimated_or_reserved_usd": sum(self.charge(c) for c in data["calls"]),
                    "uncertain_calls": sum(c["status"] == "reserved" for c in data["calls"])}

def cost(config, input_tokens, output_tokens):
    return (input_tokens * config["input_usd_per_million"] +
            output_tokens * config["output_usd_per_million"]) / 1_000_000

def parse_answer(text, supplied_ids):
    # Normalize optional thinking blocks while preserving the raw response in traces.
    text = re.sub(r"^\s*<thinking>.*?</thinking>\s*", "", text, count=1, flags=re.DOTALL)
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    answer = json.loads(text)
    if set(answer) != {"answer", "abstain", "citations"}:
        raise ValueError("Wrong answer fields")
    if not isinstance(answer["answer"], str) or type(answer["abstain"]) is not bool:
        raise ValueError("Wrong answer types")
    if not isinstance(answer["citations"], list) or not all(isinstance(i, str) for i in answer["citations"]):
        raise ValueError("Wrong citation type")
    return answer, all(i in supplied_ids for i in answer["citations"])
