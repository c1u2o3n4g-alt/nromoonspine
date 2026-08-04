import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "public" / "control" / "runtime.json"


def parse_utc(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def main():
    with PATH.open("r", encoding="utf-8") as handle:
        runtime = json.load(handle)
    if runtime.get("status") != "active":
        return
    expiry_text = runtime.get("graceUntil") or runtime.get("expiresAt")
    if not expiry_text or datetime.now(timezone.utc) < parse_utc(expiry_text):
        return
    now = datetime.now(timezone.utc)
    runtime["status"] = "expired"
    if not runtime.get("message"):
        runtime["message"] = "Mod đã hết hạn sử dụng."
    runtime["revision"] = int(now.timestamp() * 1000)
    runtime["updatedAt"] = now.isoformat().replace("+00:00", "Z")
    with PATH.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(runtime, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("Runtime status changed to expired")


if __name__ == "__main__":
    main()
