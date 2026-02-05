"""
LLMCode Uninstaller
- 설치 폴더 삭제
- 환경변수 PATH에서 제거
- 설정 폴더 삭제 (선택)
"""

import os
import sys
import shutil
from pathlib import Path


INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "llmcode"
CONFIG_DIR = Path.home() / ".llmcode"


def print_banner():
    print("=" * 50)
    print("  LLMCode Uninstaller")
    print("=" * 50)
    print()


def remove_from_path():
    """환경변수 PATH에서 제거"""
    print("[1/3] Removing from PATH...")

    install_str = str(INSTALL_DIR)

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

        # PATH에서 제거
        paths = current_path.split(";")
        new_paths = [p for p in paths if p.lower() != install_str.lower()]

        if len(new_paths) < len(paths):
            new_path = ";".join(new_paths)
            winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            print(f"  - Removed from PATH")
        else:
            print("  Not in PATH")

        winreg.CloseKey(key)

        # 환경변수 변경 알림
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        ctypes.windll.user32.SendMessageW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment"
        )

    except Exception as e:
        print(f"  ! Failed: {e}")

    print()


def remove_install_dir():
    """설치 폴더 삭제"""
    print("[2/3] Removing install directory...")

    if INSTALL_DIR.exists():
        try:
            shutil.rmtree(INSTALL_DIR)
            print(f"  - Deleted: {INSTALL_DIR}")
        except Exception as e:
            print(f"  ! Failed: {e}")
    else:
        print("  Not found")

    print()


def remove_config():
    """설정 폴더 삭제"""
    print("[3/3] Removing config directory...")

    response = input(f"  Delete {CONFIG_DIR}? [y/N]: ").strip().lower()

    if response == 'y':
        if CONFIG_DIR.exists():
            try:
                shutil.rmtree(CONFIG_DIR)
                print(f"  - Deleted: {CONFIG_DIR}")
            except Exception as e:
                print(f"  ! Failed: {e}")
        else:
            print("  Not found")
    else:
        print("  Skipped (config preserved)")

    print()


def print_complete():
    print("=" * 50)
    print("  Uninstall Complete!")
    print("=" * 50)
    print()
    print("LLMCode has been removed from your system.")
    print()


def main():
    print_banner()

    if os.name != 'nt':
        print("This uninstaller is for Windows only.")
        input("Press Enter to exit...")
        return

    print(f"Install directory: {INSTALL_DIR}")
    print(f"Config directory: {CONFIG_DIR}")
    print()

    response = input("Uninstall LLMCode? [y/N]: ").strip().lower()
    if response != 'y':
        print("Cancelled.")
        input("Press Enter to exit...")
        return

    print()

    remove_from_path()
    remove_install_dir()
    remove_config()
    print_complete()

    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
