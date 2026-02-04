import click
import asyncio
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
from scanner import scan_files, scan_single_file
from api_client import APIClient
from storage import SummaryStore, VectorStore, ConversationHistory, get_file_hash
from chunker import chunk_files

console = Console()


def ensure_config() -> tuple[str, str]:
    """설정 확인, 없으면 입력받기"""
    server_url = get_server_url()
    api_key = get_api_key()

    if not server_url or not api_key:
        console.print("[yellow]설정이 필요합니다.[/yellow]\n")

        server_url = Prompt.ask(
            "서버 URL",
            default="http://100.104.99.20:8000"
        )
        api_key = Prompt.ask("API Key")

        config = get_global_config()
        config["server_url"] = server_url.rstrip("/")
        config["api_key"] = api_key
        config["default_model"] = "qwen2.5-coder:14b"
        save_global_config(config)

        console.print("[green]설정 저장 완료![/green]\n")

    return server_url, api_key


def get_client() -> APIClient:
    """API 클라이언트 생성"""
    server_url, api_key = ensure_config()
    return APIClient(server_url, api_key)


def check_index(base_path: Path) -> bool:
    """인덱스 존재 여부 확인"""
    try:
        vector_store = VectorStore(base_path)
        return vector_store.get_stats()["total_chunks"] > 0
    except Exception:
        return False


async def run_scan(client: APIClient, base_path: Path, extensions: list = None):
    """프로젝트 스캔 실행"""
    console.print("[dim]프로젝트 스캔 중...[/dim]\n")

    all_files = scan_files(base_path, extensions=extensions)

    if not all_files:
        console.print("[yellow]스캔할 파일이 없습니다.[/yellow]")
        return

    console.print(f"[dim]파일 {len(all_files)}개 발견[/dim]")

    summary_store = SummaryStore(base_path)
    vector_store = VectorStore(base_path)

    # 요약 생성
    model = get_default_model()
    files_to_summarize = []

    for f in all_files:
        content_hash = get_file_hash(f["content"])
        if summary_store.needs_update(f["path"], content_hash):
            files_to_summarize.append((f, content_hash))

    if files_to_summarize:
        console.print(f"[dim]요약 생성: {len(files_to_summarize)}개 파일[/dim]")

        for i, (file_data, content_hash) in enumerate(files_to_summarize):
            console.print(f"  [{i+1}/{len(files_to_summarize)}] {file_data['path']}", end=" ")

            summary_text = ""
            try:
                async for chunk in client.summarize_stream(file_data, model):
                    if chunk.get("type") == "token":
                        summary_text += chunk.get("content", "")
                    elif chunk.get("type") == "error":
                        console.print(f"[red]오류[/red]")
                        break

                if summary_text:
                    summary_store.save_summary(
                        file_data["path"],
                        content_hash,
                        summary_text,
                        file_data.get("language", "text")
                    )
                    console.print("[green]✓[/green]")
            except Exception as e:
                console.print(f"[red]오류: {e}[/red]")

    # 임베딩 생성
    console.print(f"[dim]임베딩 생성 중...[/dim]")
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
        except Exception as e:
            console.print(f"[red]임베딩 오류: {e}[/red]")

    console.print(f"[green]스캔 완료![/green] (청크 {len(chunks)}개)\n")


async def run_ask(client: APIClient, prompt: str, base_path: Path):
    """질문 실행"""
    model = get_default_model()

    # RAG 컨텍스트 구성
    context_files = []

    try:
        vector_store = VectorStore(base_path)

        if vector_store.get_stats()["total_chunks"] > 0:
            # 질문 임베딩
            result = await client.embed([prompt])
            query_embedding = result.get("embeddings", [[]])[0]

            if query_embedding:
                relevant_chunks = vector_store.search(query_embedding, n_results=10)

                if relevant_chunks:
                    relevant_paths = set(c["metadata"]["path"] for c in relevant_chunks)
                    all_files = scan_files(base_path)
                    context_files = [f for f in all_files if f["path"] in relevant_paths]
                    console.print(f"[dim]관련 파일 {len(context_files)}개 선택[/dim]\n")
    except Exception:
        pass

    # RAG 실패시 전체 스캔
    if not context_files:
        all_files = scan_files(base_path)
        context_files = all_files[:10]  # 최대 10개
        console.print(f"[dim]파일 {len(context_files)}개 분석 중...[/dim]\n")

    # 분석 실행
    try:
        async for chunk in client.analyze_stream(context_files, prompt, model):
            chunk_type = chunk.get("type")

            if chunk_type == "token":
                console.print(chunk.get("content", ""), end="")
            elif chunk_type == "error":
                console.print(f"\n[red]오류: {chunk.get('message')}[/red]")
                return
            elif chunk_type == "done":
                usage = chunk.get("usage", {})
                console.print(f"\n\n[dim]토큰: {usage.get('total_tokens', '?')}[/dim]")
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")


async def run_chat(client: APIClient, base_path: Path):
    """대화형 모드"""
    model = get_default_model()
    history = ConversationHistory(base_path)

    # 프로젝트 요약 로드
    summaries = []
    try:
        summary_store = SummaryStore(base_path)
        summaries = summary_store.get_all_summaries()
    except Exception:
        pass

    console.print("[bold]대화형 모드[/bold]")
    console.print("[dim]종료: /quit | 초기화: /clear | 스캔: /scan[/dim]")

    if summaries:
        console.print(f"[dim]프로젝트 컨텍스트: {len(summaries)}개 파일[/dim]")
    else:
        console.print("[dim]프로젝트 스캔 안 됨. /scan으로 스캔하세요.[/dim]")

    console.print()

    # 시스템 메시지
    system_content = "당신은 전문 코드 분석가입니다. 한국어로 답변하세요."
    if summaries:
        system_content += "\n\n## 프로젝트 파일 요약\n"
        for s in summaries[:20]:
            system_content += f"\n### {s['path']}\n{s['summary']}\n"

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]종료[/dim]")
            break

        if not user_input.strip():
            continue

        cmd = user_input.strip().lower()

        if cmd == "/quit":
            console.print("[dim]종료[/dim]")
            break

        if cmd == "/clear":
            history.clear()
            console.print("[dim]히스토리 초기화됨[/dim]")
            continue

        if cmd == "/scan":
            await run_scan(client, base_path)
            # 요약 다시 로드
            try:
                summaries = summary_store.get_all_summaries()
                system_content = "당신은 전문 코드 분석가입니다. 한국어로 답변하세요."
                if summaries:
                    system_content += "\n\n## 프로젝트 파일 요약\n"
                    for s in summaries[:20]:
                        system_content += f"\n### {s['path']}\n{s['summary']}\n"
            except Exception:
                pass
            continue

        # 메시지 구성
        messages = [{"role": "system", "content": system_content}]
        messages.extend(history.get_messages(limit=10))
        messages.append({"role": "user", "content": user_input})

        history.add_message("user", user_input)

        console.print("\n[bold green]Assistant[/bold green]")

        response_text = ""
        try:
            async for chunk in client.chat_stream(messages, model=model):
                chunk_type = chunk.get("type")

                if chunk_type == "token":
                    content = chunk.get("content", "")
                    response_text += content
                    console.print(content, end="")
                elif chunk_type == "error":
                    console.print(f"\n[red]오류: {chunk.get('message')}[/red]")
                    break
                elif chunk_type == "done":
                    usage = chunk.get("usage", {})
                    console.print(f"\n[dim]토큰: {usage.get('total_tokens', '?')}[/dim]")

            if response_text:
                history.add_message("assistant", response_text)
        except Exception as e:
            console.print(f"\n[red]오류: {e}[/red]")


@click.command()
@click.argument("prompt", required=False)
@click.option("--scan", "-s", is_flag=True, help="프로젝트 스캔 후 시작")
@click.option("--path", "-p", type=click.Path(exists=True), default=".", help="프로젝트 경로")
@click.option("--config", "-c", is_flag=True, help="설정 재구성")
@click.version_option(version="0.1.0")
def cli(prompt: str, scan: bool, path: str, config: bool):
    """
    Local Code Assistant - LLM 기반 코드 분석 도구

    \b
    사용법:
      llmcode              대화형 모드
      llmcode "질문"       바로 질문하기
      llmcode -s           스캔 후 대화형 모드
      llmcode -c           설정 재구성
    """
    # 설정 재구성
    if config:
        console.print("[yellow]설정을 재구성합니다.[/yellow]\n")
        server_url = Prompt.ask("서버 URL", default=get_server_url() or "http://100.104.99.20:8000")
        api_key = Prompt.ask("API Key", default=get_api_key() or "")

        cfg = get_global_config()
        cfg["server_url"] = server_url.rstrip("/")
        cfg["api_key"] = api_key
        cfg["default_model"] = "qwen2.5-coder:14b"
        save_global_config(cfg)

        console.print("[green]설정 저장 완료![/green]")
        return

    client = get_client()
    base_path = Path(path).resolve()

    # 연결 테스트
    try:
        result = asyncio.run(client.health_check())
        if result.get("status") != "ok":
            console.print("[red]서버 연결 실패[/red]")
            return
    except Exception as e:
        console.print(f"[red]서버 연결 실패: {e}[/red]")
        console.print("[dim]서버가 실행 중인지 확인하세요.[/dim]")
        return

    # 스캔 요청 또는 인덱스 없을 때 제안
    if scan:
        asyncio.run(run_scan(client, base_path))
    elif not check_index(base_path) and not prompt:
        if Confirm.ask("프로젝트가 스캔되지 않았습니다. 스캔할까요?", default=True):
            asyncio.run(run_scan(client, base_path))

    # 실행 모드 결정
    if prompt:
        # 바로 질문
        asyncio.run(run_ask(client, prompt, base_path))
    else:
        # 대화형 모드
        asyncio.run(run_chat(client, base_path))


def main():
    cli()


if __name__ == "__main__":
    main()
