"""
터미널 상태바 관리 (간단한 방식)
- 매 출력 후 상태바를 맨 아래에 다시 그림
- 스크롤 영역 분리 없이 동작
"""

import sys
import os
import shutil
import threading
import time
from typing import Optional, Callable


class TerminalDisplay:
    """
    터미널 하단에 상태바를 유지하는 디스플레이 관리자
    """

    SAVE_CURSOR = "\033[s"
    RESTORE_CURSOR = "\033[u"
    CLEAR_LINE = "\033[2K"

    def __init__(self):
        self._lock = threading.Lock()
        self._status_text = ""
        self._running = False
        self._update_thread = None
        self._status_callback: Optional[Callable[[], str]] = None
        self._last_height = 0

        # Windows에서 ANSI 활성화
        self._enable_ansi()

    def _enable_ansi(self):
        """Windows에서 ANSI escape sequence 활성화"""
        if os.name == 'nt':
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
                mode = ctypes.c_ulong()
                kernel32.GetConsoleMode(handle, ctypes.byref(mode))
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            except Exception:
                pass

    def _get_terminal_size(self) -> tuple[int, int]:
        """터미널 크기 (rows, cols)"""
        try:
            size = shutil.get_terminal_size()
            return size.lines, size.columns
        except Exception:
            return 24, 80

    def _draw_status_bar(self):
        """상태바를 터미널 맨 아래에 그리기"""
        with self._lock:
            height, width = self._get_terminal_size()

            # 커서 위치 저장
            sys.stdout.write(self.SAVE_CURSOR)

            # 맨 아래 줄로 이동
            sys.stdout.write(f"\033[{height};1H")

            # 줄 클리어 후 상태바 출력
            sys.stdout.write(self.CLEAR_LINE)
            status = self._status_text[:width-1]  # 너비 제한
            sys.stdout.write(status)

            # 커서 복원
            sys.stdout.write(self.RESTORE_CURSOR)
            sys.stdout.flush()

    def _update_loop(self):
        """백그라운드 상태바 업데이트"""
        while self._running:
            if self._status_callback:
                try:
                    self._status_text = self._status_callback()
                except Exception:
                    pass
            self._draw_status_bar()
            time.sleep(1)

    def start(self, status_callback: Callable[[], str] = None):
        """디스플레이 시작"""
        self._status_callback = status_callback
        self._running = True

        # 초기 상태바 그리기
        if status_callback:
            self._status_text = status_callback()

        # 빈 줄 추가해서 상태바 공간 확보
        print()
        self._draw_status_bar()

        # 백그라운드 업데이트 시작
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._update_thread.start()

    def stop(self):
        """디스플레이 중지"""
        self._running = False
        if self._update_thread:
            self._update_thread.join(timeout=2)
        # 마지막 상태바 클리어
        height, _ = self._get_terminal_size()
        sys.stdout.write(f"\033[{height};1H")
        sys.stdout.write(self.CLEAR_LINE)
        sys.stdout.write("\033[1;1H")  # 맨 위로
        sys.stdout.flush()

    def set_status(self, text: str):
        """상태바 텍스트 직접 설정"""
        self._status_text = text
        self._draw_status_bar()

    def print(self, text: str = "", end: str = "\n"):
        """출력 (상태바 유지)"""
        with self._lock:
            sys.stdout.write(text + end)
            sys.stdout.flush()
        # 상태바 다시 그리기
        self._draw_status_bar()

    def print_token(self, token: str):
        """스트리밍 토큰 출력"""
        with self._lock:
            sys.stdout.write(token)
            sys.stdout.flush()
        # 줄바꿈 있으면 상태바 갱신
        if "\n" in token:
            self._draw_status_bar()


class StatusBar:
    """상태바 정보 관리"""

    def __init__(self):
        self.claude_enabled = False
        self.claude_mode = "cli"
        self.ram_used = 0.0
        self.ram_total = 0.0
        self.ollama_connected = False

    def set_claude_status(self, enabled: bool, mode: str):
        self.claude_enabled = enabled
        self.claude_mode = mode

    def update_server_status(self, ram_used: float, ram_total: float, ollama_connected: bool):
        self.ram_used = ram_used
        self.ram_total = ram_total
        self.ollama_connected = ollama_connected

    def render(self) -> str:
        """상태바를 문자열로 렌더링"""
        parts = ["───"]

        # Claude 상태
        if self.claude_enabled:
            parts.append(f" Claude: ON ({self.claude_mode.upper()})")
        else:
            parts.append(" Claude: OFF")

        parts.append(" │")

        # RAM 상태
        if self.ram_total > 0:
            pct = int((self.ram_used / self.ram_total) * 100)
            parts.append(f" RAM: {self.ram_used:.1f}/{self.ram_total:.1f}GB ({pct}%)")
        else:
            parts.append(" RAM: --")

        parts.append(" │")

        # Ollama 상태
        if self.ollama_connected:
            parts.append(" ● Ollama")
        else:
            parts.append(" ○ Ollama")

        parts.append(" ───")

        return "".join(parts)


# 전역 인스턴스
_display: Optional[TerminalDisplay] = None
_status_bar: Optional[StatusBar] = None


def get_display() -> Optional[TerminalDisplay]:
    return _display


def set_display(display: Optional[TerminalDisplay]):
    global _display
    _display = display


def get_status_bar() -> Optional[StatusBar]:
    return _status_bar


def set_status_bar(status_bar: Optional[StatusBar]):
    global _status_bar
    _status_bar = status_bar
