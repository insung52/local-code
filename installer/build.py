"""
PyInstaller 빌드 스크립트
llmcode-setup.exe 생성
"""

import subprocess
import shutil
import sys
from pathlib import Path

# 경로
ROOT = Path(__file__).parent.parent
INSTALLER_DIR = ROOT / "installer"
CLIENT_DIR = ROOT / "client"
DIST_DIR = INSTALLER_DIR / "dist"

CLIENT_FILES = [
    "cli.py",
    "api_client.py",
    "agent.py",
    "tools.py",
    "config.py",
    "scanner.py",
    "chunker.py",
    "storage.py",
    "version.py",
    "updater.py",
]


def clean():
    """빌드 폴더 정리"""
    print("Cleaning...")
    for folder in ["build", "dist", "__pycache__"]:
        path = INSTALLER_DIR / folder
        if path.exists():
            shutil.rmtree(path)

    spec_file = INSTALLER_DIR / "installer.spec"
    if spec_file.exists():
        spec_file.unlink()


def build():
    """PyInstaller로 exe 빌드"""
    print("Building llmcode-setup.exe...")

    # 데이터 파일 옵션 생성
    add_data = []
    for f in CLIENT_FILES:
        src = CLIENT_DIR / f
        if src.exists():
            # Windows: --add-data "src;dest"
            add_data.extend(["--add-data", f"{src};."])

    # requirements 파일
    req_file = CLIENT_DIR / "requirements.txt"
    if req_file.exists():
        add_data.extend(["--add-data", f"{req_file};."])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "llmcode-setup",
        "--console",
        *add_data,
        str(INSTALLER_DIR / "installer.py"),
    ]

    print(f"Command: {' '.join(cmd)}")
    print()

    result = subprocess.run(cmd, cwd=str(INSTALLER_DIR))

    if result.returncode == 0:
        exe_path = DIST_DIR / "llmcode-setup.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print()
            print("=" * 50)
            print(f"Build successful!")
            print(f"Output: {exe_path}")
            print(f"Size: {size_mb:.1f} MB")
            print("=" * 50)
        else:
            print("Build completed but exe not found")
    else:
        print("Build failed!")


def main():
    print("LLMCode Installer Builder")
    print("=" * 50)
    print()

    # PyInstaller 확인
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True,
            check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("PyInstaller not found.")
        print("Install with: pip install pyinstaller")
        return

    clean()
    build()


if __name__ == "__main__":
    main()
