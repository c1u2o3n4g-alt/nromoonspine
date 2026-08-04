import json
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
STATUSES = {"active", "suspended", "maintenance", "expired"}
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_BUNDLE_BYTES = 64 * 1024 * 1024


def fail(message):
    raise RuntimeError(message)


def load_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_time(value, field):
    if not value:
        fail(f"Missing {field}")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        fail(f"Invalid {field}: {exc}")


def https_url(value, field):
    parsed = urlparse(value or "")
    if parsed.scheme != "https" or not parsed.netloc:
        fail(f"Invalid HTTPS URL in {field}")


def validate_runtime(runtime):
    if runtime.get("schemaVersion") != 1:
        fail("Unsupported runtime schemaVersion")
    try:
        uuid.UUID(runtime.get("modId", ""))
    except ValueError:
        fail("Invalid runtime modId")
    if not runtime.get("companyName"):
        fail("Missing runtime companyName")
    if runtime.get("status") not in STATUSES:
        fail("Invalid runtime status")
    parse_time(runtime.get("expiresAt"), "expiresAt")
    parse_time(runtime.get("graceUntil"), "graceUntil")
    parse_time(runtime.get("updatedAt"), "updatedAt")
    if int(runtime.get("revision", 0)) <= 0:
        fail("Invalid runtime revision")


def validate_manifest(runtime):
    release = str(runtime.get("activeRelease", "")).strip()
    if not release:
        if runtime.get("status") == "active":
            fail("Active runtime has no activeRelease")
        return
    manifest_path = PUBLIC / "releases" / release / "manifest.json"
    if not manifest_path.is_file():
        fail(f"Missing manifest for active release: {release}")
    https_url(runtime.get("manifestUrl"), "manifestUrl")
    if not SHA256.fullmatch(str(runtime.get("manifestSha256", ""))):
        fail("Invalid manifestSha256")

    manifest = load_json(manifest_path)
    if manifest.get("schemaVersion") != 1:
        fail("Unsupported manifest schemaVersion")
    if manifest.get("modId") != runtime.get("modId") or manifest.get("companyName") != runtime.get("companyName"):
        fail("Manifest identity does not match runtime")
    if manifest.get("releaseId") != release or manifest.get("version") != release:
        fail("Manifest release does not match activeRelease")

    files = manifest.get("files") or []
    if not files:
        fail("Manifest has no files")
    names = set()
    total = 0
    has_bootstrap = False
    has_spine = False
    for item in files:
        name = str(item.get("name", ""))
        if not name.endswith(".cuongdev") or Path(name).name != name:
            fail(f"Invalid bundle name: {name}")
        if name in names:
            fail(f"Duplicate bundle name: {name}")
        names.add(name)
        size = int(item.get("size", 0))
        if size <= 0 or size > MAX_BUNDLE_BYTES:
            fail(f"Invalid mobile bundle size: {name}")
        if not SHA256.fullmatch(str(item.get("sha256", ""))):
            fail(f"Invalid bundle SHA-256: {name}")
        if int(item.get("unityCrc", 0)) < 0:
            fail(f"Invalid Unity CRC: {name}")
        https_url(item.get("downloadUrl"), f"downloadUrl for {name}")
        scope = str(item.get("scope", ""))
        has_bootstrap = has_bootstrap or scope == "bootstrap"
        has_spine = has_spine or scope == "spine"
        total += size
    if total != int(manifest.get("totalSize", 0)):
        fail("Manifest totalSize mismatch")
    if not has_bootstrap:
        fail("Manifest has no bootstrap bundle")
    if not has_spine:
        fail("Manifest has no deferred Spine bundle")


def main():
    runtime = load_json(PUBLIC / "control" / "runtime.json")
    validate_runtime(runtime)
    validate_manifest(runtime)
    print("WebGL control validation passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
