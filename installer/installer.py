"""
LLMCode Installer
- 파일 복사 → %LOCALAPPDATA%\llmcode\
- 환경변수 PATH 등록
- 설정 초기화
"""

import os
import sys
import shutil
import subprocess
import ctypes
from pathlib import Path

# 설치 경로
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "llmcode"


def get_python_executable():
    """시스템 Python 경로 찾기 (PyInstaller exe가 아닌)"""
    if getattr(sys, 'frozen', False):
        # PyInstaller로 빌드된 경우 - 시스템 Python 찾기
        possible_paths = [
            shutil.which("python"),
            shutil.which("python3"),
            r"C:\Python310\python.exe",
            r"C:\Python311\python.exe",
            r"C:\Python312\python.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python310\python.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python311\python.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"),
            r"C:\Program Files\Python310\python.exe",
            r"C:\Program Files\Python311\python.exe",
            r"C:\Program Files\Python312\python.exe",
        ]
        for path in possible_paths:
            if path and Path(path).exists():
                return path
        return "python"  # fallback
    else:
        return sys.executable
CLIENT_FILES = [
    "cli.py",
    "api_client.py",
    "agent.py",
    "tools.py",
    "config.py",
    "scanner.py",
    "chunker.py",
    "storage.py",
]


def is_admin():
    """관리자 권한 확인"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def print_banner():
    """배너 출력"""
    print("=" * 50)
    print("  LLMCode Installer")
    print("  Local LLM Code Assistant")
    print("=" * 50)
    print()


def get_embedded_files():
    """
    PyInstaller로 빌드시 포함된 파일 경로 반환
    개발 중에는 client/ 폴더 사용
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 빌드된 exe
        base_path = Path(sys._MEIPASS)
    else:
        # 개발 모드
        base_path = Path(__file__).parent.parent / "client"

    return base_path


def copy_files():
    """클라이언트 파일 복사"""
    print("[1/4] Copying files...")

    # 설치 폴더 생성
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    source_dir = get_embedded_files()

    for filename in CLIENT_FILES:
        src = source_dir / filename
        dst = INSTALL_DIR / filename

        if src.exists():
            shutil.copy2(src, dst)
            print(f"  + {filename}")
        else:
            print(f"  ! Missing: {filename}")

    # requirements도 복사
    req_src = source_dir / "requirements.txt"
    if not req_src.exists():
        req_src = source_dir.parent / "client" / "requirements.txt"
    if req_src.exists():
        shutil.copy2(req_src, INSTALL_DIR / "requirements.txt")
        print("  + requirements.txt")

    print(f"  -> Installed to: {INSTALL_DIR}")
    print()


def create_launcher():
    """llmcode.bat 생성"""
    print("[2/4] Creating launcher...")

    bat_content = f'''@echo off
python "{INSTALL_DIR}\\cli.py" %*
'''

    bat_path = INSTALL_DIR / "llmcode.bat"
    bat_path.write_text(bat_content, encoding="utf-8")
    print(f"  + llmcode.bat")
    print()


def add_to_path():
    """환경변수 PATH에 추가"""
    print("[3/4] Adding to PATH...", flush=True)

    install_str = str(INSTALL_DIR)

    # 현재 사용자 PATH 읽기
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_ALL_ACCESS
        )

        try:
            current_path, _ = winreg.QueryValueEx(key, "Path")
        except WindowsError:
            current_path = ""

        # 이미 있으면 스킵
        if install_str.lower() in current_path.lower():
            print("  Already in PATH", flush=True)
        else:
            # PATH에 추가
            if current_path:
                new_path = f"{current_path};{install_str}"
            else:
                new_path = install_str

            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            print(f"  + Added: {install_str}", flush=True)

        winreg.CloseKey(key)

        # 환경변수 변경 알림 (타임아웃 버전 사용)
        try:
            import ctypes
            from ctypes import wintypes

            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            SMTO_ABORTIFHUNG = 0x0002

            SendMessageTimeoutW = ctypes.windll.user32.SendMessageTimeoutW
            SendMessageTimeoutW.argtypes = [
                wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                wintypes.LPCWSTR, wintypes.UINT, wintypes.UINT,
                ctypes.POINTER(wintypes.DWORD)
            ]
            result = wintypes.DWORD()

            # 1초 타임아웃으로 브로드캐스트
            SendMessageTimeoutW(
                HWND_BROADCAST, WM_SETTINGCHANGE, 0,
                "Environment", SMTO_ABORTIFHUNG, 1000, ctypes.byref(result)
            )
        except Exception:
            pass  # 실패해도 무시 (새 터미널에서는 적용됨)

    except Exception as e:
        print(f"  ! Failed to add to PATH: {e}", flush=True)
        print(f"  Manual: Add '{install_str}' to your PATH", flush=True)

    print(flush=True)


def install_dependencies():
    """Python 패키지 설치"""
    print("[4/4] Installing dependencies...", flush=True)
    print("  (This may take a few minutes for chromadb...)", flush=True)
    print(flush=True)

    python_exe = get_python_executable()
    print(f"  Using Python: {python_exe}", flush=True)

    if not python_exe or python_exe == "python":
        # Python을 못 찾으면 경고
        print("  ! Could not find Python executable", flush=True)
        print("  Make sure Python is installed and in PATH", flush=True)
        print("  Manual: pip install click httpx rich chromadb", flush=True)
        print(flush=True)
        return

    req_file = INSTALL_DIR / "requirements.txt"

    if req_file.exists():
        try:
            print("  Running pip install...", flush=True)
            # 실시간 출력 표시
            process = subprocess.Popen(
                [python_exe, "-m", "pip", "install", "--progress-bar", "on", "-r", str(req_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            # 실시간 출력
            for line in process.stdout:
                print(f"  {line.rstrip()}", flush=True)
            process.wait()

            if process.returncode == 0:
                print()
                print("  + Dependencies installed", flush=True)
            else:
                print(f"  ! pip install failed (exit code {process.returncode})", flush=True)
                print(f"  Manual: pip install -r {req_file}", flush=True)
        except Exception as e:
            print(f"  ! pip install failed: {e}", flush=True)
            print(f"  Manual: pip install -r {req_file}", flush=True)
    else:
        # 직접 설치
        packages = ["click", "httpx", "rich", "chromadb"]
        try:
            print("  Running pip install...", flush=True)
            process = subprocess.Popen(
                [python_exe, "-m", "pip", "install", "--progress-bar", "on"] + packages,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            for line in process.stdout:
                print(f"  {line.rstrip()}", flush=True)
            process.wait()

            if process.returncode == 0:
                print()
                print("  + Dependencies installed", flush=True)
            else:
                print(f"  ! pip install failed", flush=True)
                print(f"  Manual: pip install {' '.join(packages)}", flush=True)
        except Exception as e:
            print(f"  ! pip install failed: {e}", flush=True)
            print(f"  Manual: pip install {' '.join(packages)}", flush=True)

    print(flush=True)


def setup_config():
    """초기 설정"""
    config_dir = Path.home() / ".llmcode"
    config_file = config_dir / "config.json"

    if not config_file.exists():
        config_dir.mkdir(parents=True, exist_ok=True)

        # 기본 설정
        import json
        default_config = {
            "server_url": "http://100.104.99.20:8000",
            "api_key": "",
            "default_model": "qwen2.5-coder:14b"
        }
        config_file.write_text(
            json.dumps(default_config, indent=2),
            encoding="utf-8"
        )
        print("  + Default config created")
        print("  ! Run 'llmcode --config' to set API key")


def print_success():
    """완료 메시지"""
    print("=" * 50)
    print("  Installation Complete!")
    print("=" * 50)
    print()
    print("Usage:")
    print("  1. Open a NEW terminal (PowerShell/CMD)")
    print("  2. Navigate to your project folder")
    print("  3. Run: llmcode")
    print()
    print("First time setup:")
    print("  llmcode --config")
    print()
    print("Options:")
    print("  llmcode          New conversation")
    print("  llmcode -c       Continue previous")
    print("  llmcode -s       Scan project first")
    print()


def main():
    print_banner()

    # Windows 확인
    if os.name != 'nt':
        print("This installer is for Windows only.")
        print("For Linux/Mac, use: pip install -e .")
        input("Press Enter to exit...")
        return

    # Python 확인
    if sys.version_info < (3, 9):
        print(f"Python 3.9+ required. Current: {sys.version}")
        input("Press Enter to exit...")
        return

    print(f"Install location: {INSTALL_DIR}")
    print()

    response = input("Continue? [Y/n]: ").strip().lower()
    if response and response != 'y':
        print("Cancelled.")
        return

    print()

    try:
        copy_files()
        create_launcher()
        add_to_path()
        install_dependencies()
        setup_config()
        print_success()
    except Exception as e:
        print(f"\nError: {e}")
        print("Installation failed.")

    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
