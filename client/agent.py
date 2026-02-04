import asyncio
import json
import sys
import threading
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Confirm
import difflib

from api_client import APIClient
from tools import parse_tool_calls, execute_tool, get_tools_prompt
from config import get_default_model

console = Console()

MAX_ITERATIONS = 10  # 최대 도구 호출 반복 횟수

# ESC 감지용 전역 변수
stop_generation = False


def check_escape_key():
    """ESC 키 감지 (Windows)"""
    global stop_generation
    try:
        import msvcrt
        while True:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key == b'\x1b':  # ESC
                    stop_generation = True
                    return
            if stop_generation:
                return
            import time
            time.sleep(0.05)
    except ImportError:
        # Unix 계열
        pass


def start_escape_listener():
    """ESC 리스너 시작"""
    global stop_generation
    stop_generation = False
    thread = threading.Thread(target=check_escape_key, daemon=True)
    thread.start()
    return thread


def show_diff(old_content: str, new_content: str, path: str):
    """파일 변경 diff 표시 (Claude Code 스타일)"""
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    # 파일 경로 표시
    console.print(f"\n[bold]{path}[/bold]")

    # diff 계산
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

    has_changes = False

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            # 변경 없는 줄 (컨텍스트로 앞뒤 2줄만)
            continue
        elif tag == 'delete':
            has_changes = True
            for idx, line in enumerate(old_lines[i1:i2], start=i1 + 1):
                console.print(f"[dim]{idx:4}[/dim] [red]- {line}[/red]")
        elif tag == 'insert':
            has_changes = True
            for idx, line in enumerate(new_lines[j1:j2], start=j1 + 1):
                console.print(f"[dim]{idx:4}[/dim] [green]+ {line}[/green]")
        elif tag == 'replace':
            has_changes = True
            # 먼저 삭제된 줄들
            for idx, line in enumerate(old_lines[i1:i2], start=i1 + 1):
                console.print(f"[dim]{idx:4}[/dim] [red]- {line}[/red]")
            # 그 다음 추가된 줄들
            for idx, line in enumerate(new_lines[j1:j2], start=j1 + 1):
                console.print(f"[dim]{idx:4}[/dim] [green]+ {line}[/green]")

    if not has_changes:
        console.print("[dim]No changes[/dim]")


async def agent_chat(
    client: APIClient,
    messages: list[dict],
    base_path: Path,
) -> tuple[str, list[dict]]:
    """
    에이전트 루프 실행

    Returns:
        (최종 응답 텍스트, 업데이트된 메시지 리스트)
    """
    global stop_generation
    model = get_default_model()
    iteration = 0

    while iteration < MAX_ITERATIONS:
        iteration += 1

        # ESC 리스너 시작
        start_escape_listener()

        # LLM 호출
        full_response = ""
        stopped = False

        try:
            async for chunk in client.chat_stream(messages, model=model):
                # ESC 체크
                if stop_generation:
                    stopped = True
                    console.print("\n[yellow](Stopped)[/yellow]")
                    break

                chunk_type = chunk.get("type")

                if chunk_type == "token":
                    content = chunk.get("content", "")
                    full_response += content
                    console.print(content, end="")

                elif chunk_type == "error":
                    console.print(f"\n[red]Error: {chunk.get('message')}[/red]")
                    stop_generation = True
                    return full_response, messages

                elif chunk_type == "done":
                    pass

        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            stop_generation = True
            return full_response, messages

        # 중지됨
        stop_generation = True  # 리스너 종료
        if stopped:
            return full_response, messages

        # 도구 호출 파싱
        tool_calls = parse_tool_calls(full_response)

        if not tool_calls:
            # 도구 호출 없음 = 최종 응답
            console.print()  # 줄바꿈
            return full_response, messages

        # 도구 실행
        console.print("\n")

        # assistant 메시지 추가
        messages.append({"role": "assistant", "content": full_response})

        tool_results = []

        for call in tool_calls:
            tool_name = call.get("tool")
            args = call.get("args", {})

            console.print(f"[dim]> {tool_name}({args})[/dim]")

            # 현재 디렉토리 기준으로 경로 조정
            if "path" in args and not Path(args["path"]).is_absolute():
                args["path"] = str(base_path / args["path"])

            result = execute_tool(tool_name, args)

            # write_file 은 확인 필요
            if tool_name == "write_file" and result.get("requires_confirmation"):
                console.print()
                show_diff(
                    result.get("old_content", ""),
                    result.get("new_content", ""),
                    result.get("path", "")
                )

                if Confirm.ask("\n[yellow]Apply changes?[/yellow]", default=False):
                    # 실제 파일 쓰기
                    try:
                        Path(result["path"]).write_text(
                            result["new_content"],
                            encoding="utf-8"
                        )
                        result = {"success": True, "path": result["path"], "message": "File updated"}
                        console.print("[green]File updated![/green]")
                    except Exception as e:
                        result = {"error": str(e)}
                        console.print(f"[red]Failed: {e}[/red]")
                else:
                    result = {"cancelled": True, "message": "User cancelled"}
                    console.print("[dim]Cancelled[/dim]")

            tool_results.append({
                "tool": tool_name,
                "result": result
            })

        # 도구 결과를 메시지에 추가
        result_text = "Tool results:\n"
        for tr in tool_results:
            result_json = json.dumps(tr["result"], ensure_ascii=False, indent=2)
            # 너무 길면 자르기
            if len(result_json) > 3000:
                result_json = result_json[:3000] + "\n... (truncated)"
            result_text += f"\n### {tr['tool']}\n```json\n{result_json}\n```\n"

        messages.append({"role": "user", "content": result_text})

        console.print()  # 줄바꿈 후 다음 반복

    console.print("[yellow]Max iterations reached[/yellow]")
    return full_response, messages


def get_system_prompt(summaries: list = None) -> str:
    """시스템 프롬프트 생성"""
    prompt = get_tools_prompt()

    prompt += "\n\n## Context\n"
    prompt += "You are a code assistant. Help the user understand and modify their code.\n"

    if summaries:
        prompt += "\n### Project File Summaries\n"
        for s in summaries[:15]:
            prompt += f"\n**{s['path']}**: {s['summary'][:200]}...\n"

    return prompt
