from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import tarfile
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
UA = {"User-Agent": "OMEGA-Render-Runner-Bootstrap/1", "Accept": "application/vnd.github+json"}


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise RuntimeError("OMEGA_RUNNER_BOOTSTRAP_RESPONSE_TOO_LARGE")
    return json.loads(raw)


def download(url: str, target: pathlib.Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
    with urllib.request.urlopen(req, timeout=120) as response, target.open("wb") as handle:
        shutil.copyfileobj(response, handle, length=1024 * 1024)


def asset(release: dict, pattern: str) -> tuple[str, str]:
    regex = re.compile(pattern)
    rows = [(str(x.get("name") or ""), str(x.get("browser_download_url") or "")) for x in release.get("assets") or []]
    rows = [(name, url) for name, url in rows if regex.fullmatch(name) and url.startswith("https://github.com/")]
    if len(rows) != 1:
        raise RuntimeError(f"OMEGA_RUNNER_ASSET_AMBIGUOUS:{pattern}:{len(rows)}")
    return rows[0]


def extract_tar(url: str, destination: pathlib.Path, strip_top: bool = False) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="omega-runner-bootstrap-") as tmp:
        archive = pathlib.Path(tmp) / "asset.tar.gz"
        download(url, archive)
        unpack = pathlib.Path(tmp) / "unpack"
        unpack.mkdir()
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(unpack, filter="data")
        if strip_top:
            children = [p for p in unpack.iterdir()]
            if len(children) != 1 or not children[0].is_dir():
                raise RuntimeError("OMEGA_RUNNER_ARCHIVE_LAYOUT_INVALID")
            unpack = children[0]
        for src in unpack.iterdir():
            dst = destination / src.name
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            shutil.move(str(src), str(dst))


runner_release = get_json("https://api.github.com/repos/actions/runner/releases/latest")
runner_name, runner_url = asset(runner_release, r"actions-runner-linux-x64-[0-9.]+\.tar\.gz")
runner_dir = ROOT / "actions-runner"
if runner_dir.exists():
    shutil.rmtree(runner_dir)
extract_tar(runner_url, runner_dir)

gh_release = get_json("https://api.github.com/repos/cli/cli/releases/latest")
gh_name, gh_url = asset(gh_release, r"gh_[0-9.]+_linux_amd64\.tar\.gz")
bin_dir = ROOT / "bin"
if bin_dir.exists():
    shutil.rmtree(bin_dir)
extract_tar(gh_url, bin_dir, strip_top=True)
gh = bin_dir / "bin" / "gh"
if not gh.is_file():
    raise RuntimeError("OMEGA_GH_BINARY_MISSING")

(ROOT / "bootstrap-state.json").write_text(
    json.dumps(
        {
            "runner_asset": runner_name,
            "runner_tag": runner_release.get("tag_name"),
            "gh_asset": gh_name,
            "gh_tag": gh_release.get("tag_name"),
            "credential_material_recorded": False,
        },
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
print("OMEGA_RENDER_RUNNER_BOOTSTRAP_PASS")
