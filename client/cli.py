import click
import asyncio
import sys
import os
import signal
import threading
import time
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import ANSI

from config import (
    save_global_config,
    get_global_config,
    get_server_url,
    get_api_key,
    get_default_model,
)
from scanner import scan_files
from api_client import APIClient
from storage import SummaryStore, VectorStore, ConversationHistory
from agent import agent_chat, get_system_prompt
from version import VERSION
from claude_client import ClaudeClient, test_cli_available
from display import StatusInfo, set_status_info

console = Console()

# 전역 중지 플래그
stop_requested = False


def create_multiline_prompt():
    """멀티라인 입력을 위한 PromptSession 생성
    - Enter: 제출
    - Ctrl+J: 줄바꿈
    """
    bindings = KeyBindings()

    @bindings.add('c-j')  # Ctrl+J
    def _(event):
        """Ctrl+J: 줄바꿈"""
        event.current_buffer.insert_text('\n')

    @bindings.add('escape', 'enter')  # Alt+Enter (some terminals)
    def _(event):
        """Alt+Enter: 줄바꿈"""
        event.current_buffer.insert_text('\n')

    return PromptSession(key_bindings=bindings)


# 상태 업데이터 (백그라운드 스레드) - 터미널 제목 갱신
class StatusUpdater:
    """10초마다 서버 상태를 가져와서 터미널 제목 갱신"""

    def __init__(self, client: APIClient, status_info: StatusInfo, interval: int = 5):
        self.client = client
        self.status_info = status_info
        self.interval = interval
        self.running = False
        self.thread = None
        self._loop = None

    async def _fetch_status(self):
        """서버에서 상태 가져오기"""
        try:
            health = await self.client.health_check()

            # 메모리 상태
            memory = health.get("memory", {})
            ram_total = memory.get("total_gb", 0)
            available = memory.get("available_gb", 0)
            ram_used = ram_total - available

            # Ollama 상태
            ollama = health.get("ollama", {})
            ollama_connected = ollama.get("status") == "connected"
            model = ollama.get("model", "")

            # status_info에 업데이트
            self.status_info.update_server_status(
                ram_used, ram_total, ollama_connected, model
            )

            # 터미널 제목 갱신
            self.status_info.update_title()

        except Exception:
            pass

    def _run_loop(self):
        """백그라운드 루프"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        while self.running:
            try:
                self._loop.run_until_complete(self._fetch_status())
            except Exception:
                pass

            # interval 동안 대기 (1초씩 체크해서 빠른 종료 가능)
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

        self._loop.close()

    def start(self):
        """업데이터 시작"""
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        """업데이터 중지"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)


def signal_handler(signum, frame):
    """Ctrl+C 핸들러"""
    global stop_requested
    stop_requested = True
    console.print("\n[yellow]Stopping...[/yellow]")


def ensure_config() -> tuple[str, str]:
    """설정 확인, 없으면 입력받기"""
    server_url = get_server_url()
    api_key = get_api_key()

    if not server_url or not api_key:
        console.print("[yellow]Setup required.[/yellow]\n")

        server_url = Prompt.ask("Server URL", default="http://100.104.99.20:8000")
        api_key = Prompt.ask("API Key")

        config = get_global_config()
        config["server_url"] = server_url.rstrip("/")
        config["api_key"] = api_key
        config["default_model"] = "qwen2.5-coder:14b"
        save_global_config(config)

        console.print("[green]Config saved![/green]\n")

    return server_url, api_key


def get_client() -> APIClient:
    """API 클라이언트 생성"""
    server_url, api_key = ensure_config()
    return APIClient(server_url, api_key)


# 업데이트 관련
update_info_cache = None


def check_update_background():
    """백그라운드에서 업데이트 확인"""
    global update_info_cache
    try:
        from updater import check_for_update

        update_info_cache = check_for_update()
    except Exception:
        pass


def show_update_notice():
    """업데이트 알림 표시"""
    global update_info_cache
    if update_info_cache:
        current = update_info_cache["current_version"]
        latest = update_info_cache["latest_version"]
        console.print(f"[yellow]Update available: v{current} → {latest}[/yellow]")
        console.print("[dim]Run 'llmcode --update' to update[/dim]\n")


def perform_update_interactive():
    """대화형 업데이트 수행"""
    from updater import (
        check_for_update,
        find_installer_asset,
        download_installer,
        run_installer,
    )

    console.print("[bold]Checking for updates...[/bold]")

    update_info = check_for_update()
    if not update_info:
        console.print("[green]Already up to date![/green]")
        return

    current = update_info["current_version"]
    latest = update_info["latest_version"]

    console.print(f"\n[yellow]Update available: v{current} → {latest}[/yellow]")

    if update_info.get("body"):
        console.print(f"\n[dim]Release notes:[/dim]\n{update_info['body'][:300]}...")

    if not Confirm.ask("\n[yellow]Download and install?[/yellow]", default=True):
        console.print("[dim]Cancelled[/dim]")
        return

    # installer URL 찾기
    installer_url = find_installer_asset(update_info.get("assets", []))
    if not installer_url:
        console.print("[red]Installer not found in release[/red]")
        console.print(f"[dim]Manual download: {update_info.get('release_url')}[/dim]")
        return

    # 다운로드
    console.print("\n[bold]Downloading...[/bold]")

    def progress(downloaded, total):
        pct = int(downloaded / total * 100)
        # 한 줄에서 덮어쓰기
        sys.stdout.write(f"\r  {pct}% ({downloaded // 1024}KB / {total // 1024}KB)    ")
        sys.stdout.flush()

    exe_path = download_installer(installer_url, progress)
    sys.stdout.write("\n")  # 줄바꿈

    if not exe_path:
        console.print("[red]Download failed[/red]")
        return

    console.print("[green]Download complete![/green]")
    console.print("\n[bold]Running installer...[/bold]")

    if run_installer(exe_path, silent=False):
        console.print("[green]Installer started. Please follow the prompts.[/green]")
        console.print("[dim]Restart llmcode after installation.[/dim]")
    else:
        console.print("[red]Failed to start installer[/red]")


async def run_agent_chat(
    client: APIClient, base_path: Path, continue_chat: bool = False
):
    """에이전트 대화 모드"""
    global stop_requested

    history = ConversationHistory(base_path)

    # 상태 정보 생성
    status_info = StatusInfo()
    status_info.server_url = get_server_url()
    set_status_info(status_info)

    # 상태 업데이터 시작 (터미널 제목 갱신, 5초마다)
    status_updater = StatusUpdater(client, status_info, interval=5)
    status_updater.start()

    # Claude 설정
    config = get_global_config()
    claude_mode = config.get("claude_mode", "cli")
    claude_api_key = config.get("claude_api_key", "")
    claude_client = None

    # Claude 클라이언트 초기화
    if claude_mode == "cli":
        if test_cli_available():
            claude_client = ClaudeClient(mode="cli")
    elif claude_mode == "api" and claude_api_key:
        claude_client = ClaudeClient(mode="api", api_key=claude_api_key)

    # Claude enabled 상태 로드 (클라이언트가 있을 때만)
    claude_enabled = config.get("claude_enabled", False) and claude_client is not None

    # 상태 정보에 Claude 상태 설정
    status_info.set_claude_status(claude_enabled, claude_mode)
    status_info.update_title()

    # 프로젝트 요약 로드
    summaries = []
    try:
        summary_store = SummaryStore(base_path)
        summaries = summary_store.get_all_summaries()
    except Exception:
        pass

    # 터미널 클리어
    os.system("cls" if os.name == "nt" else "clear")

    # 시스템 프롬프트 (이전 요약 포함)
    prev_summary = history.get_summary()
    system_prompt = get_system_prompt(
        summaries, prev_summary, claude_enabled=claude_enabled
    )
    messages = [{"role": "system", "content": system_prompt}]

    # -c 옵션이면 이전 대화 로드
    if continue_chat:
        prev_messages = history.get_messages(limit=20)
        if prev_messages:
            # 헤더 출력
            console.print("[bold]Agent Mode[/bold] [dim](continued)[/dim]")
            console.print(
                "[dim]Commands: /quit, /clear, /scan, /status, /include <path>[/dim]"
            )
            if summaries:
                console.print(f"[dim]Project indexed: {len(summaries)} files[/dim]")
            console.print()

            # 이전 대화 표시
            for msg in prev_messages:
                role = msg.get("role")
                content = msg.get("content", "")

                if role == "user":
                    # Tool results는 생략
                    if content.startswith("Tool results:"):
                        continue
                    console.print(
                        f"[bold cyan]You[/bold cyan]: {content[:200]}{'...' if len(content) > 200 else ''}"
                    )
                elif role == "assistant":
                    # 긴 응답은 줄이기
                    display = content[:300] + "..." if len(content) > 300 else content
                    console.print(f"[bold green]Assistant[/bold green]: {display}")

            messages.extend(prev_messages)
            console.print(f"\n[dim]--- {len(prev_messages)} messages loaded ---[/dim]")
        else:
            # 이전 대화 없음
            console.print("[bold]Agent Mode[/bold]")
            console.print(
                "[dim]Commands: /quit, /clear, /scan, /status, /include <path>[/dim]"
            )
            if summaries:
                console.print(f"[dim]Project indexed: {len(summaries)} files[/dim]")
            console.print("[dim]No previous conversation[/dim]")
    else:
        # 새 대화
        console.print("[bold]Agent Mode[/bold]")
        console.print(
            "[dim]Commands: /quit, /clear, /scan, /status, /include <path>[/dim]"
        )
        if summaries:
            console.print(f"[dim]Project indexed: {len(summaries)} files[/dim]")
        history.clear()

    # 업데이트 알림 (모든 출력 후)
    show_update_notice()

    console.print("[dim]Tip: Ctrl+J for newline[/dim]")
    console.print()

    # 멀티라인 입력 세션 생성
    prompt_session = create_multiline_prompt()

    while True:
        stop_requested = False

        try:
            user_input = await prompt_session.prompt_async(ANSI("\n\033[1;36mYou:\033[0m "))
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Bye![/dim]")
            break

        if not user_input.strip():
            continue

        cmd = user_input.strip()

        # 명령어 처리
        if cmd.lower() == "/quit":
            console.print("[dim]Bye![/dim]")
            break

        if cmd.lower() == "/clear":
            history.clear()
            messages = [{"role": "system", "content": system_prompt}]
            console.print("[dim]History cleared[/dim]")
            continue

        if cmd.lower() == "/scan":
            console.print("[dim]Scanning project...[/dim]")
            await run_scan(client, base_path)
            # 요약 다시 로드
            try:
                summaries = SummaryStore(base_path).get_all_summaries()
                system_prompt = get_system_prompt(
                    summaries, claude_enabled=claude_enabled
                )
                messages[0] = {"role": "system", "content": system_prompt}
            except Exception:
                pass
            continue

        if cmd.lower() == "/status":
            console.print(status_info.get_detailed_status())
            continue

        if cmd.lower() == "/claude on":
            if not claude_client:
                if claude_mode == "cli":
                    console.print(
                        "[red]Claude CLI not available. Install Claude Code first.[/red]"
                    )
                else:
                    console.print(
                        "[red]Claude API key not set. Run: llmcode --config[/red]"
                    )
            else:
                claude_enabled = True
                system_prompt = get_system_prompt(
                    summaries, prev_summary, claude_enabled=True
                )
                messages[0] = {"role": "system", "content": system_prompt}
                mode_str = "CODE" if claude_mode == "cli" else "API"
                console.print(f"[green]Claude enabled ({mode_str} mode)[/green]")
                # 상태 저장 및 갱신
                status_info.set_claude_status(True, claude_mode)
                status_info.update_title()
                config["claude_enabled"] = True
                save_global_config(config)
            continue

        if cmd.lower() == "/claude off":
            claude_enabled = False
            system_prompt = get_system_prompt(
                summaries, prev_summary, claude_enabled=False
            )
            messages[0] = {"role": "system", "content": system_prompt}
            console.print("[dim]Claude disabled[/dim]")
            # 상태 저장 및 갱신
            status_info.set_claude_status(False, claude_mode)
            status_info.update_title()
            config["claude_enabled"] = False
            save_global_config(config)
            continue

        if cmd.lower() == "/claude":
            status = "[green]ON[/green]" if claude_enabled else "[dim]OFF[/dim]"
            mode_str = "CODE" if claude_mode == "cli" else "API"
            if claude_mode == "cli":
                avail = (
                    "[green]available[/green]"
                    if claude_client
                    else "[red]not found[/red]"
                )
            else:
                avail = (
                    "[green]configured[/green]"
                    if claude_api_key
                    else "[red]no key[/red]"
                )
            console.print(f"Claude: {status} | Mode: {mode_str} ({avail})")
            console.print("[dim]Usage: /claude on, /claude off[/dim]")
            continue

        if cmd.lower().startswith("/include "):
            include_path = cmd[9:].strip()
            try:
                full_path = base_path / include_path
                if full_path.is_file():
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    messages.append(
                        {
                            "role": "user",
                            "content": f"[File added to context: {include_path}]\n```\n{content[:5000]}\n```",
                        }
                    )
                    console.print(f"[green]Added: {include_path}[/green]")
                elif full_path.is_dir():
                    files = list(full_path.rglob("*"))[:10]
                    file_list = [
                        str(f.relative_to(base_path)) for f in files if f.is_file()
                    ]
                    messages.append(
                        {
                            "role": "user",
                            "content": f"[Directory added: {include_path}]\nFiles: {', '.join(file_list)}",
                        }
                    )
                    console.print(
                        f"[green]Added directory: {include_path} ({len(file_list)} files)[/green]"
                    )
                else:
                    console.print(f"[red]Not found: {include_path}[/red]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
            continue

        # 사용자 메시지 추가
        messages.append({"role": "user", "content": user_input})
        history.add_message("user", user_input)

        console.print("\n[bold green]Assistant[/bold green]")

        # 에이전트 루프 실행
        response, messages = await agent_chat(
            client,
            messages,
            base_path,
            claude_enabled=claude_enabled,
            claude_approved=False,  # 새 요청마다 리셋
            claude_client=claude_client,
        )

        # 응답 저장
        if response:
            history.add_message("assistant", response)

        # 대화 압축 체크
        if history.needs_compression():
            to_compress = history.compress(keep_recent=6)
            if to_compress:
                # 압축된 메시지 간단 요약 생성
                summary_parts = []
                for m in to_compress[-4:]:  # 최근 4개만
                    role = "User" if m["role"] == "user" else "Assistant"
                    content = m["content"][:100]
                    summary_parts.append(f"{role}: {content}...")

                new_summary = history.get_summary()
                if new_summary:
                    new_summary += "\n---\n"
                new_summary += "\n".join(summary_parts)
                history.set_summary(new_summary[-2000:])  # 2000자 제한

                # 메시지 리스트도 재구성
                system_prompt = get_system_prompt(summaries, history.get_summary())
                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(history.get_messages())
                console.print("[dim]Conversation compressed[/dim]")

        console.print()

    # 종료 시 정리
    status_updater.stop()
    set_status_info(None)


async def run_scan(client: APIClient, base_path: Path):
    """프로젝트 스캔"""
    from storage import SummaryStore, VectorStore, get_file_hash
    from chunker import chunk_files

    all_files = scan_files(base_path)

    if not all_files:
        console.print("[yellow]No files to scan[/yellow]")
        return

    console.print(f"[dim]Found {len(all_files)} files[/dim]")

    summary_store = SummaryStore(base_path)
    vector_store = VectorStore(base_path)
    model = get_default_model()

    # 요약 생성
    files_to_summarize = []
    for f in all_files:
        content_hash = get_file_hash(f["content"])
        if summary_store.needs_update(f["path"], content_hash):
            files_to_summarize.append((f, content_hash))

    if files_to_summarize:
        console.print(f"[dim]Summarizing {len(files_to_summarize)} files...[/dim]")

        for i, (file_data, content_hash) in enumerate(files_to_summarize):
            console.print(
                f"  [{i+1}/{len(files_to_summarize)}] {file_data['path']}", end=" "
            )

            summary_text = ""
            try:
                async for chunk in client.summarize_stream(file_data, model):
                    if chunk.get("type") == "token":
                        summary_text += chunk.get("content", "")

                if summary_text:
                    summary_store.save_summary(
                        file_data["path"],
                        content_hash,
                        summary_text,
                        file_data.get("language", "text"),
                    )
                    console.print("[green]OK[/green]")
            except Exception as e:
                console.print(f"[red]Error[/red]")

    # 임베딩
    console.print(f"[dim]Creating embeddings...[/dim]")
    chunks = chunk_files(all_files, max_tokens=500, overlap_tokens=50)

    batch_size = 20
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["content"] for c in batch]

        try:
            result = await client.embed(texts)
            embeddings = result.get("embeddings", [])

            if embeddings:
                vector_store.add_chunks(
                    ids=[c["id"] for c in batch],
                    embeddings=embeddings,
                    documents=texts,
                    metadatas=[c["metadata"] for c in batch],
                )
        except Exception:
            pass

    console.print(f"[green]Scan complete![/green] ({len(chunks)} chunks)")


async def run_single_query(client: APIClient, prompt: str, base_path: Path):
    """단일 질문 실행"""
    # 간단한 에이전트 루프
    system_prompt = get_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    console.print("[bold green]Assistant[/bold green]\n")

    response, _ = await agent_chat(client, messages, base_path)

    console.print()


@click.command()
@click.argument("prompt", required=False)
@click.option("--scan", "-s", is_flag=True, help="Scan project first")
@click.option(
    "--path", "-p", type=click.Path(exists=True), default=".", help="Project path"
)
@click.option(
    "--continue",
    "-c",
    "continue_chat",
    is_flag=True,
    help="Continue previous conversation",
)
@click.option("--config", is_flag=True, help="Reconfigure")
@click.option("--update", "-u", is_flag=True, help="Check and install updates")
@click.version_option(version=VERSION)
def cli(
    prompt: str, scan: bool, path: str, continue_chat: bool, config: bool, update: bool
):
    """
    Local Code Assistant - AI Code Agent

    \b
    Usage:
      llmcode              New conversation
      llmcode -c           Continue previous conversation
      llmcode "question"   Quick question
      llmcode -s           Scan then start
      llmcode --config     Reconfigure
      llmcode --update     Check for updates
    """
    # Ctrl+C 핸들러
    signal.signal(signal.SIGINT, signal_handler)

    # 업데이트 명령
    if update:
        perform_update_interactive()
        return

    # 백그라운드에서 업데이트 체크 시작
    update_thread = threading.Thread(target=check_update_background, daemon=True)
    update_thread.start()

    if config:
        console.print("[yellow]Reconfiguring...[/yellow]\n")
        server_url = Prompt.ask(
            "Server URL", default=get_server_url() or "http://100.104.99.20:8000"
        )
        api_key = Prompt.ask("API Key (local server)", default=get_api_key() or "")

        cfg = get_global_config()

        # Claude 설정
        console.print("\n[bold]Claude Settings[/bold]")
        current_mode = cfg.get("claude_mode", "cli")

        # CLI 사용 가능 여부 체크
        cli_available = test_cli_available()
        if cli_available:
            console.print("[green]✓ Claude CLI available[/green]")
        else:
            console.print(
                "[yellow]✗ Claude CLI not found (install Claude Code first)[/yellow]"
            )

        console.print(
            "\n[dim]1. CLI mode - uses 'claude -p' command (Pro subscription)[/dim]"
        )
        console.print("[dim]2. API mode - uses Anthropic API (requires credits)[/dim]")

        mode_choice = Prompt.ask(
            "Claude mode",
            choices=["1", "2", "skip"],
            default="1" if current_mode == "cli" else "2",
        )

        if mode_choice == "1":
            cfg["claude_mode"] = "cli"
            if not cli_available:
                console.print(
                    "[yellow]Warning: Claude CLI not detected. Install Claude Code first.[/yellow]"
                )
        elif mode_choice == "2":
            cfg["claude_mode"] = "api"
            claude_key = cfg.get("claude_api_key", "")
            claude_api_key = Prompt.ask("Claude API Key", default=claude_key or "")
            if claude_api_key:
                cfg["claude_api_key"] = claude_api_key
            else:
                console.print("[yellow]Warning: API mode requires API key[/yellow]")

        cfg["server_url"] = server_url.rstrip("/")
        cfg["api_key"] = api_key
        cfg["default_model"] = "qwen2.5-coder:14b"

        save_global_config(cfg)

        console.print("\n[green]Config saved![/green]")
        console.print(f"[dim]Claude mode: {cfg.get('claude_mode', 'cli')}[/dim]")
        console.print("[dim]Use /claude on to enable Claude supervisor[/dim]")
        return

    client = get_client()
    base_path = Path(path).resolve()

    # 연결 테스트
    try:
        result = asyncio.run(client.health_check())
        if result.get("status") != "ok":
            console.print("[red]Server connection failed[/red]")
            return
    except Exception as e:
        console.print(f"[red]Server connection failed: {e}[/red]")
        return

    # 업데이트 체크 완료 대기 (최대 1초)
    update_thread.join(timeout=1.0)

    # 스캔 요청
    if scan:
        asyncio.run(run_scan(client, base_path))
        console.print()

    # 실행 모드
    if prompt:
        asyncio.run(run_single_query(client, prompt, base_path))
    else:
        asyncio.run(run_agent_chat(client, base_path, continue_chat))


def main():
    cli()


if __name__ == "__main__":
    main()
