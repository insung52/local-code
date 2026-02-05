import click
import asyncio
import sys
import os
import signal
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm

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

console = Console()

# 전역 중지 플래그
stop_requested = False


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

        server_url = Prompt.ask(
            "Server URL",
            default="http://100.104.99.20:8000"
        )
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


async def run_agent_chat(client: APIClient, base_path: Path, continue_chat: bool = False):
    """에이전트 대화 모드"""
    global stop_requested

    history = ConversationHistory(base_path)

    # 프로젝트 요약 로드 (있으면)
    summaries = []
    try:
        summary_store = SummaryStore(base_path)
        summaries = summary_store.get_all_summaries()
    except Exception:
        pass

    console.print("[bold]Agent Mode[/bold]")
    console.print("[dim]Commands: /quit, /clear, /scan, /include <path>[/dim]")

    if summaries:
        console.print(f"[dim]Project indexed: {len(summaries)} files[/dim]")

    # 시스템 프롬프트 (이전 요약 포함)
    prev_summary = history.get_summary()
    system_prompt = get_system_prompt(summaries, prev_summary)
    messages = [{"role": "system", "content": system_prompt}]

    # -c 옵션이면 이전 대화 로드
    if continue_chat:
        prev_messages = history.get_messages(limit=20)
        if prev_messages:
            # 터미널 클리어
            os.system('cls' if os.name == 'nt' else 'clear')

            # 헤더 다시 출력
            console.print("[bold]Agent Mode[/bold] [dim](continued)[/dim]")
            console.print("[dim]Commands: /quit, /clear, /scan, /include <path>[/dim]\n")

            # 이전 대화 표시
            for msg in prev_messages:
                role = msg.get("role")
                content = msg.get("content", "")

                if role == "user":
                    # Tool results는 생략
                    if content.startswith("Tool results:"):
                        continue
                    console.print(f"[bold cyan]You[/bold cyan]: {content[:200]}{'...' if len(content) > 200 else ''}")
                elif role == "assistant":
                    # 긴 응답은 줄이기
                    display = content[:300] + "..." if len(content) > 300 else content
                    console.print(f"[bold green]Assistant[/bold green]: {display}")

            messages.extend(prev_messages)
            console.print(f"\n[dim]--- {len(prev_messages)} messages loaded ---[/dim]")
        else:
            console.print("[dim]No previous conversation[/dim]")
    else:
        # 새 대화 - 히스토리 클리어
        history.clear()
        console.print("[dim]New conversation[/dim]")

    console.print()

    while True:
        stop_requested = False

        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
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
                system_prompt = get_system_prompt(summaries)
                messages[0] = {"role": "system", "content": system_prompt}
            except Exception:
                pass
            continue

        if cmd.lower().startswith("/include "):
            include_path = cmd[9:].strip()
            try:
                full_path = base_path / include_path
                if full_path.is_file():
                    content = full_path.read_text(encoding='utf-8', errors='replace')
                    messages.append({
                        "role": "user",
                        "content": f"[File added to context: {include_path}]\n```\n{content[:5000]}\n```"
                    })
                    console.print(f"[green]Added: {include_path}[/green]")
                elif full_path.is_dir():
                    files = list(full_path.rglob("*"))[:10]
                    file_list = [str(f.relative_to(base_path)) for f in files if f.is_file()]
                    messages.append({
                        "role": "user",
                        "content": f"[Directory added: {include_path}]\nFiles: {', '.join(file_list)}"
                    })
                    console.print(f"[green]Added directory: {include_path} ({len(file_list)} files)[/green]")
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
        response, messages = await agent_chat(client, messages, base_path)

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
            console.print(f"  [{i+1}/{len(files_to_summarize)}] {file_data['path']}", end=" ")

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
                        file_data.get("language", "text")
                    )
                    console.print("[green]OK[/green]")
            except Exception as e:
                console.print(f"[red]Error[/red]")

    # 임베딩
    console.print(f"[dim]Creating embeddings...[/dim]")
    chunks = chunk_files(all_files, max_tokens=500, overlap_tokens=50)

    batch_size = 20
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
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
        {"role": "user", "content": prompt}
    ]

    console.print("[bold green]Assistant[/bold green]\n")

    response, _ = await agent_chat(client, messages, base_path)

    console.print()


@click.command()
@click.argument("prompt", required=False)
@click.option("--scan", "-s", is_flag=True, help="Scan project first")
@click.option("--path", "-p", type=click.Path(exists=True), default=".", help="Project path")
@click.option("--continue", "-c", "continue_chat", is_flag=True, help="Continue previous conversation")
@click.option("--config", is_flag=True, help="Reconfigure")
@click.version_option(version="0.3.0")
def cli(prompt: str, scan: bool, path: str, continue_chat: bool, config: bool):
    """
    Local Code Assistant - AI Code Agent

    \b
    Usage:
      llmcode              New conversation
      llmcode -c           Continue previous conversation
      llmcode "question"   Quick question
      llmcode -s           Scan then start
      llmcode --config     Reconfigure
    """
    # Ctrl+C 핸들러
    signal.signal(signal.SIGINT, signal_handler)

    if config:
        console.print("[yellow]Reconfiguring...[/yellow]\n")
        server_url = Prompt.ask("Server URL", default=get_server_url() or "http://100.104.99.20:8000")
        api_key = Prompt.ask("API Key", default=get_api_key() or "")

        cfg = get_global_config()
        cfg["server_url"] = server_url.rstrip("/")
        cfg["api_key"] = api_key
        cfg["default_model"] = "qwen2.5-coder:14b"
        save_global_config(cfg)

        console.print("[green]Config saved![/green]")
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
