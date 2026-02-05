"""
터미널 제목 기반 상태 표시
- 터미널 창 제목에 상태 정보 표시
- 10초마다 갱신
"""

import os
import ctypes
from typing import Optional


def set_terminal_title(title: str):
    """터미널 창 제목 설정"""
    if os.name == 'nt':
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass
    else:
        # Unix 계열
        print(f"\033]0;{title}\007", end="", flush=True)


class StatusInfo:
    """상태 정보 관리"""

    def __init__(self):
        # Claude 상태: "OFF", "CODE", "API"
        self.claude_status = "OFF"

        # 서버 상태
        self.ram_used = 0.0
        self.ram_total = 0.0
        self.ollama_connected = False
        self.ollama_model = ""

        # 서버 정보
        self.server_url = ""

    def set_claude_status(self, enabled: bool, mode: str):
        """Claude 상태 설정"""
        if not enabled:
            self.claude_status = "OFF"
        elif mode == "cli":
            self.claude_status = "CODE"
        else:
            self.claude_status = "API"

    def update_server_status(self, ram_used: float, ram_total: float, ollama_connected: bool, model: str = ""):
        """서버 상태 업데이트"""
        self.ram_used = ram_used
        self.ram_total = ram_total
        self.ollama_connected = ollama_connected
        self.ollama_model = model

    def get_title(self) -> str:
        """터미널 제목용 짧은 상태 문자열"""
        parts = []

        # RAM (소수점 없이)
        if self.ram_total > 0:
            parts.append(f"RAM:{int(self.ram_used)}/{int(self.ram_total)}GB")

        # Claude
        parts.append(f"Claude:{self.claude_status}")

        # Ollama 연결 상태 (간단히)
        if self.ollama_connected:
            parts.append("Ollama:OK")
        else:
            parts.append("Ollama:X")

        return " | ".join(parts)

    def update_title(self):
        """터미널 제목 업데이트"""
        title = self.get_title()
        set_terminal_title(title)

    def get_detailed_status(self) -> str:
        """자세한 상태 문자열 (Rich 마크업)"""
        lines = []
        lines.append("[bold]═══ Status ═══[/bold]")

        # Claude 상태
        if self.claude_status == "OFF":
            lines.append(f"  Claude: [dim]OFF[/dim]")
        elif self.claude_status == "CODE":
            lines.append(f"  Claude: [bold green]ON[/bold green] [dim](CLI/Pro subscription)[/dim]")
        else:
            lines.append(f"  Claude: [bold cyan]ON[/bold cyan] [dim](API credits)[/dim]")

        # RAM 상태
        if self.ram_total > 0:
            pct = int((self.ram_used / self.ram_total) * 100)
            if pct > 80:
                color = "bold red"
            elif pct > 60:
                color = "yellow"
            else:
                color = "green"
            lines.append(f"  RAM: [{color}]{self.ram_used:.1f}/{self.ram_total:.1f}GB ({pct}%)[/{color}]")
        else:
            lines.append(f"  RAM: [dim]Unknown[/dim]")

        # Ollama 상태
        if self.ollama_connected:
            model_info = f" [dim]({self.ollama_model})[/dim]" if self.ollama_model else ""
            lines.append(f"  Ollama: [green]Connected[/green]{model_info}")
        else:
            lines.append(f"  Ollama: [red]Disconnected[/red]")

        # 서버 URL
        if self.server_url:
            lines.append(f"  Server: [dim]{self.server_url}[/dim]")

        lines.append("[bold]══════════════[/bold]")

        return "\n".join(lines)


# 전역 인스턴스
_status_info: Optional[StatusInfo] = None


def get_status_info() -> Optional[StatusInfo]:
    return _status_info


def set_status_info(status_info: Optional[StatusInfo]):
    global _status_info
    _status_info = status_info
