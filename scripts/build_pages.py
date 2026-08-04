import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
SITE = ROOT / "_site"
DOWNLOAD = ROOT / "_download"
MAX_BUNDLE_BYTES = 64 * 1024 * 1024


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command):
    subprocess.run(command, cwd=ROOT, check=True)


def safe_extract(archive_path: Path, destination: Path):
    destination = destination.resolve()
    with zipfile.ZipFile(archive_path, "r") as archive:
        for item in archive.infolist():
            target = (destination / item.filename).resolve()
            if destination != target and destination not in target.parents:
                raise RuntimeError(f"Unsafe archive path: {item.filename}")
        archive.extractall(destination)


def copy_public():
    for source in PUBLIC.rglob("*"):
        relative = source.relative_to(PUBLIC)
        target = SITE / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def download_release_assets(release: str, include_bundles: bool):
    fixture = os.environ.get("WEBGL_RELEASE_ASSET_DIR", "").strip()
    if fixture:
        fixture_path = Path(fixture)
        for source in fixture_path.glob("webgl-player-*.zip"):
            shutil.copy2(source, DOWNLOAD / source.name)
        if include_bundles:
            for source in fixture_path.glob("*.cuongdev"):
                shutil.copy2(source, DOWNLOAD / source.name)
        return
    command = ["gh", "release", "download", release, "--repo", os.environ["GITHUB_REPOSITORY"], "--dir", str(DOWNLOAD), "--clobber", "--pattern", "webgl-player-*.zip"]
    if include_bundles:
        command.extend(["--pattern", "*.cuongdev"])
    run(command)


def deploy_player(release: str, include_bundles: bool):
    download_release_assets(release, include_bundles)
    archives = list(DOWNLOAD.glob("webgl-player-*.zip"))
    if len(archives) != 1:
        raise RuntimeError(f"Expected one WebGL Player archive, found {len(archives)}")
    safe_extract(archives[0], SITE)
    if not include_bundles:
        return

    manifest_path = PUBLIC / "releases" / release / "manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("version") != release or manifest.get("releaseId") != release:
        raise RuntimeError("Active manifest release does not match runtime.json")
    files = manifest.get("files") or []
    if not files:
        raise RuntimeError("Active manifest has no bundle files")

    bundle_destination = SITE / "bundles" / release
    bundle_destination.mkdir(parents=True, exist_ok=True)
    actual_total = 0
    for item in files:
        name = item.get("name", "")
        if not name or Path(name).name != name or not name.endswith(".cuongdev"):
            raise RuntimeError(f"Invalid bundle name: {name}")
        source = DOWNLOAD / name
        if not source.is_file():
            raise RuntimeError(f"Missing release asset: {name}")
        size = source.stat().st_size
        if size != int(item.get("size", 0)):
            raise RuntimeError(f"Bundle size mismatch: {name}")
        if size > MAX_BUNDLE_BYTES:
            raise RuntimeError(f"Bundle exceeds mobile limit: {name} ({size} bytes)")
        if sha256(source).lower() != str(item.get("sha256", "")).lower():
            raise RuntimeError(f"Bundle checksum mismatch: {name}")
        shutil.move(str(source), bundle_destination / name)
        actual_total += size
    if actual_total != int(manifest.get("totalSize", 0)):
        raise RuntimeError("Manifest total size mismatch")


def main():
    runtime_path = PUBLIC / "control" / "runtime.json"
    runtime = load_json(runtime_path)
    if SITE.exists():
        shutil.rmtree(SITE)
    if DOWNLOAD.exists():
        shutil.rmtree(DOWNLOAD)
    SITE.mkdir(parents=True)
    DOWNLOAD.mkdir(parents=True)

    release = str(runtime.get("activeRelease", "")).strip()
    status = str(runtime.get("status", "")).lower()
    copy_public()
    if release:
        deploy_player(release, status == "active")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    shutil.rmtree(DOWNLOAD, ignore_errors=True)
    print(f"Pages artifact ready: status={status}, release={release or 'none'}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
