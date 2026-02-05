"""자동 업데이트 모듈"""

import os
import sys
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import urllib.request
import json

from version import VERSION, GITHUB_REPO


def get_latest_release() -> Optional[dict]:
    """GitHub에서 최신 릴리즈 정보 가져오기"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LLMCode-Updater"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception:
        return None


def parse_version(version_str: str) -> Tuple[int, ...]:
    """버전 문자열을 튜플로 변환 (비교용)"""
    # v0.4.0 -> (0, 4, 0)
    clean = version_str.lstrip("vV")
    parts = clean.split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def check_for_update() -> Optional[dict]:
    """
    업데이트 확인

    Returns:
        새 버전 있으면 릴리즈 정보, 없으면 None
    """
    release = get_latest_release()
    if not release:
        return None

    latest_version = release.get("tag_name", "")

    try:
        current = parse_version(VERSION)
        latest = parse_version(latest_version)

        if latest > current:
            return {
                "current_version": VERSION,
                "latest_version": latest_version,
                "release_url": release.get("html_url"),
                "assets": release.get("assets", []),
                "body": release.get("body", "")[:500],  # 릴리즈 노트
            }
    except Exception:
        pass

    return None


def find_installer_asset(assets: list) -> Optional[str]:
    """릴리즈 에셋에서 installer exe 찾기"""
    for asset in assets:
        name = asset.get("name", "").lower()
        if "setup" in name and name.endswith(".exe"):
            return asset.get("browser_download_url")
    return None


def download_installer(url: str, progress_callback=None) -> Optional[Path]:
    """installer exe 다운로드"""
    try:
        # 임시 폴더에 다운로드
        temp_dir = Path(tempfile.gettempdir()) / "llmcode_update"
        temp_dir.mkdir(exist_ok=True)

        exe_path = temp_dir / "llmcode-setup.exe"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LLMCode-Updater"}
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            total_size = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 8192

            with open(exe_path, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    if progress_callback and total_size:
                        progress_callback(downloaded, total_size)

        return exe_path

    except Exception as e:
        print(f"Download failed: {e}")
        return None


def run_installer(exe_path: Path, silent: bool = True) -> bool:
    """installer 실행"""
    try:
        args = [str(exe_path)]
        if silent:
            args.append("--silent")

        # 새 프로세스로 실행 (현재 프로세스와 분리)
        if os.name == "nt":
            # Windows
            subprocess.Popen(
                args,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                close_fds=True
            )
        else:
            subprocess.Popen(args)

        return True
    except Exception as e:
        print(f"Failed to run installer: {e}")
        return False


def perform_update(silent: bool = True, progress_callback=None) -> bool:
    """
    업데이트 수행

    Returns:
        성공 여부
    """
    update_info = check_for_update()
    if not update_info:
        return False

    # installer URL 찾기
    installer_url = find_installer_asset(update_info.get("assets", []))
    if not installer_url:
        print("Installer not found in release assets")
        return False

    # 다운로드
    exe_path = download_installer(installer_url, progress_callback)
    if not exe_path:
        return False

    # 실행
    return run_installer(exe_path, silent)
