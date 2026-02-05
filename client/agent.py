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
    claude_enabled: bool = False,
    claude_approved: bool = False,
    claude_client=None,
) -> tuple[str, list[dict]]:
    """
    에이전트 루프 실행

    Args:
        claude_enabled: /claude on 상태인지
        claude_approved: 이번 요청에서 Claude 사용이 승인되었는지
        claude_client: ClaudeClient 인스턴스

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
        in_think_mode = False  # <think> 태그 추적
        buffer = ""  # 태그 감지용 버퍼

        # ANSI 코드 (dim/reset)
        DIM = "\033[2m"
        RESET = "\033[0m"

        def print_raw(text, dim=False):
            """ANSI 코드로 직접 출력"""
            if dim:
                sys.stdout.write(DIM + text + RESET)
            else:
                sys.stdout.write(text)
            sys.stdout.flush()

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
                    buffer += content

                    # <think> 태그 감지
                    while True:
                        if not in_think_mode:
                            # <think> 시작 찾기
                            think_start = buffer.find("<think>")
                            if think_start != -1:
                                # <think> 이전 내용 출력
                                before = buffer[:think_start]
                                if before:
                                    print_raw(before)
                                in_think_mode = True
                                buffer = buffer[think_start + 7:]  # <think> 제거
                            else:
                                # 태그 없으면 버퍼 일부 출력 (태그 잘림 방지)
                                if len(buffer) > 10:
                                    safe = buffer[:-10]
                                    print_raw(safe)
                                    buffer = buffer[-10:]
                                break
                        else:
                            # </think> 종료 찾기
                            think_end = buffer.find("</think>")
                            if think_end != -1:
                                # thinking 내용 dim으로 출력
                                thinking = buffer[:think_end]
                                if thinking:
                                    print_raw(thinking, dim=True)
                                in_think_mode = False
                                buffer = buffer[think_end + 8:]  # </think> 제거
                            else:
                                # 태그 없으면 버퍼 일부 출력
                                if len(buffer) > 10:
                                    safe = buffer[:-10]
                                    print_raw(safe, dim=in_think_mode)
                                    buffer = buffer[-10:]
                                break

                elif chunk_type == "error":
                    console.print(f"\n[red]Error: {chunk.get('message')}[/red]")
                    stop_generation = True
                    return full_response, messages

                elif chunk_type == "done":
                    # 남은 버퍼 출력
                    if buffer:
                        print_raw(buffer, dim=in_think_mode)
                        buffer = ""

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

        # Claude 요청 감지 (claude_enabled이고 아직 승인 안 받은 경우)
        if claude_enabled and not claude_approved:
            claude_reason = parse_claude_request(full_response)
            if claude_reason:
                console.print(f"\n\n[yellow]Claude API 사용 추천: {claude_reason}[/yellow]")
                if Confirm.ask("[yellow]Use Claude API?[/yellow]", default=True):
                    # Claude로 전환
                    if claude_client:
                        # 현재 사용자 요청 찾기
                        user_request = ""
                        for msg in reversed(messages):
                            if msg["role"] == "user" and not msg["content"].startswith("Tool results:"):
                                user_request = msg["content"]
                                break

                        response, messages = run_with_claude(
                            claude_client,
                            user_request,
                            client,
                            messages,
                            base_path,
                            model,
                        )
                        return response, messages
                    else:
                        console.print("[red]Claude API key not configured[/red]")
                else:
                    console.print("[dim]Continuing without Claude[/dim]")

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

            # run_command 는 확인 필요
            elif tool_name == "run_command" and result.get("requires_confirmation"):
                console.print(f"\n[bold]Command:[/bold] {result.get('command')}")
                console.print(f"[dim]Working dir: {result.get('path')}[/dim]")

                if Confirm.ask("\n[yellow]Run this command?[/yellow]", default=False):
                    # 실제 명령 실행
                    try:
                        import subprocess
                        proc = subprocess.run(
                            result["command"],
                            cwd=result["path"],
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=result.get("timeout", 30)
                        )
                        output = proc.stdout + proc.stderr
                        # 출력이 너무 길면 자르기
                        if len(output) > 5000:
                            output = output[:5000] + "\n... (truncated)"
                        result = {
                            "success": proc.returncode == 0,
                            "returncode": proc.returncode,
                            "output": output
                        }
                        if proc.returncode == 0:
                            console.print("[green]Command completed![/green]")
                        else:
                            console.print(f"[yellow]Command exited with code {proc.returncode}[/yellow]")
                        if output.strip():
                            console.print(f"[dim]{output[:500]}[/dim]")
                    except subprocess.TimeoutExpired:
                        result = {"error": "Command timed out"}
                        console.print("[red]Command timed out[/red]")
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


def get_system_prompt(summaries: list = None, prev_summary: str = None, claude_enabled: bool = False) -> str:
    """시스템 프롬프트 생성"""
    prompt = get_tools_prompt(claude_enabled=claude_enabled)

    prompt += "\n\n## Context\n"
    prompt += "You are a code assistant. Help the user understand and modify their code.\n"

    if prev_summary:
        prompt += "\n### Previous Conversation Summary\n"
        prompt += prev_summary + "\n"

    if summaries:
        prompt += "\n### Project File Summaries\n"
        for s in summaries[:15]:
            prompt += f"\n**{s['path']}**: {s['summary'][:200]}...\n"

    return prompt


def parse_claude_request(response: str) -> str:
    """<request_claude> 태그에서 이유 추출"""
    import re
    match = re.search(r'<request_claude>reason:\s*(.+?)</request_claude>', response, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def run_with_claude(
    claude_client,
    user_request: str,
    local_client: APIClient,
    messages: list,
    base_path: Path,
    model: str,
) -> tuple[str, list]:
    """
    Claude supervisor 모드로 실행

    Returns:
        (최종 응답, 업데이트된 메시지)
    """
    import asyncio

    console.print("\n[bold magenta]Claude[/bold magenta] Planning...")

    # 현재 컨텍스트 요약 (최근 메시지들)
    context_parts = []
    for msg in messages[-6:]:
        if msg["role"] != "system":
            content = msg["content"][:500]
            context_parts.append(f"{msg['role']}: {content}")
    context = "\n".join(context_parts)

    # Claude에게 계획 요청
    plan_result = claude_client.plan(user_request, context)

    if plan_result.get("needs_more_info"):
        questions = plan_result.get("questions", [])
        return f"[Claude] 추가 정보 필요:\n" + "\n".join(f"- {q}" for q in questions), messages

    plan = plan_result.get("plan", "")
    steps = plan_result.get("steps", [])

    console.print(f"\n[magenta]Plan:[/magenta] {plan}")
    if steps:
        for i, step in enumerate(steps, 1):
            console.print(f"[dim]  {i}. {step}[/dim]")

    # 로컬 LLM에게 실행 지시
    execution_prompt = f"""Claude has created this plan:
{plan}

Steps:
{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(steps))}

Execute these steps using available tools. After completing, summarize what was done."""

    messages.append({"role": "user", "content": execution_prompt})

    console.print("\n[bold green]Local LLM[/bold green] Executing...")

    # 로컬 LLM 실행 (agent_chat 재사용, claude 비활성)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        response, messages = loop.run_until_complete(
            agent_chat(local_client, messages, base_path, claude_enabled=False, claude_approved=False)
        )
    finally:
        loop.close()

    # Claude에게 결과 검토 요청
    console.print("\n[bold magenta]Claude[/bold magenta] Reviewing...")

    review_result = claude_client.review(user_request, response)

    status = review_result.get("status", "completed")
    feedback = review_result.get("feedback", "")

    console.print(f"[magenta]Status:[/magenta] {status}")
    console.print(f"[magenta]Feedback:[/magenta] {feedback}")

    if status == "continue":
        next_steps = review_result.get("next_steps", [])
        if next_steps:
            # 다음 단계 실행 (재귀적으로 한 번만)
            next_prompt = "Continue with:\n" + "\n".join(f"- {s}" for s in next_steps)
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": next_prompt})

            console.print("\n[bold green]Local LLM[/bold green] Continuing...")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                response, messages = loop.run_until_complete(
                    agent_chat(local_client, messages, base_path, claude_enabled=False, claude_approved=False)
                )
            finally:
                loop.close()

    final_response = f"{response}\n\n[Claude feedback: {feedback}]"
    return final_response, messages
