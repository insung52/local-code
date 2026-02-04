import click
import asyncio
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.prompt import Prompt

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


def get_client() -> APIClient:
    """API 클라이언트 생성"""
    server_url = get_server_url()
    api_key = get_api_key()

    if not server_url or not api_key:
        console.print("[red]설정이 없습니다. 'llmcode init'을 먼저 실행하세요.[/red]")
        raise SystemExit(1)

    return APIClient(server_url, api_key)


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Local Code Assistant - LLM 기반 코드 분석 도구"""
    pass


@cli.command()
@click.option("--server", "-s", required=True, help="서버 URL (예: http://localhost:8000)")
@click.option("--api-key", "-k", required=True, help="API 키")
@click.option("--model", "-m", default="llama3.2:3b", help="기본 모델")
def init(server: str, api_key: str, model: str):
    """서버 설정 초기화"""
    config = get_global_config()
    config["server_url"] = server.rstrip("/")
    config["api_key"] = api_key
    config["default_model"] = model
    save_global_config(config)

    console.print(f"[green]설정 저장 완료![/green]")
    console.print(f"  서버: {server}")
    console.print(f"  모델: {model}")

    # 연결 테스트
    console.print("\n[dim]서버 연결 테스트 중...[/dim]")
    try:
        client = APIClient(server, api_key)
        result = asyncio.run(client.health_check())
        if result.get("status") == "ok":
            console.print(f"[green]서버 연결 성공![/green]")
            console.print(f"  Ollama: {result.get('ollama', {}).get('status')}")
            console.print(f"  모델: {', '.join(result.get('loaded_models', []))}")
        else:
            console.print(f"[yellow]서버 응답 이상: {result}[/yellow]")
    except Exception as e:
        console.print(f"[red]서버 연결 실패: {e}[/red]")


@cli.command()
def status():
    """현재 설정 및 서버 상태 확인"""
    server_url = get_server_url()
    api_key = get_api_key()

    if not server_url or not api_key:
        console.print("[red]설정이 없습니다. 'llmcode init'을 먼저 실행하세요.[/red]")
        return

    console.print(f"[bold]현재 설정[/bold]")
    console.print(f"  서버: {server_url}")
    console.print(f"  모델: {get_default_model()}")

    # 프로젝트 상태
    base_path = Path.cwd()
    try:
        summary_store = SummaryStore(base_path)
        vector_store = VectorStore(base_path)
        summaries = summary_store.get_all_summaries()
        vector_stats = vector_store.get_stats()
        console.print(f"\n[bold]프로젝트 인덱스[/bold]")
        console.print(f"  요약된 파일: {len(summaries)}개")
        console.print(f"  벡터 청크: {vector_stats['total_chunks']}개")
    except Exception:
        console.print(f"\n[dim]프로젝트 인덱스 없음[/dim]")

    console.print("\n[dim]서버 상태 확인 중...[/dim]")
    try:
        client = APIClient(server_url, api_key)
        result = asyncio.run(client.health_check())
        console.print(f"[green]서버 연결됨[/green]")
        console.print(f"  Ollama: {result.get('ollama', {}).get('status')}")
        console.print(f"  모델: {', '.join(result.get('loaded_models', []))}")
        memory = result.get("memory", {})
        console.print(f"  메모리: {memory.get('available_gb', '?')}GB / {memory.get('total_gb', '?')}GB")
    except Exception as e:
        console.print(f"[red]서버 연결 실패: {e}[/red]")


@cli.command()
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option("--ext", "-e", default=None, help="확장자 필터 (예: .py,.js)")
@click.option("--full", is_flag=True, help="전체 재스캔 (캐시 무시)")
def scan(paths: tuple, ext: str, full: bool):
    """프로젝트 스캔 (요약 + 임베딩 생성)"""
    client = get_client()

    if not paths:
        paths = (".",)

    extensions = None
    if ext:
        extensions = [e.strip() for e in ext.split(",")]

    # 파일 스캔
    all_files = []
    base_path = Path(paths[0]).resolve()
    if base_path.is_file():
        base_path = base_path.parent

    for path_str in paths:
        path = Path(path_str)
        if path.is_file():
            file_data = scan_single_file(path)
            if file_data:
                all_files.append(file_data)
        else:
            files = scan_files(path, extensions=extensions)
            all_files.extend(files)

    if not all_files:
        console.print("[yellow]스캔할 파일이 없습니다.[/yellow]")
        return

    console.print(f"[bold]파일 {len(all_files)}개 발견[/bold]\n")

    # 저장소 초기화
    summary_store = SummaryStore(base_path)
    vector_store = VectorStore(base_path)

    if full:
        summary_store.clear()
        vector_store.clear()
        console.print("[dim]캐시 초기화됨[/dim]\n")

    # 요약이 필요한 파일 필터링
    files_to_summarize = []
    for f in all_files:
        content_hash = get_file_hash(f["content"])
        if summary_store.needs_update(f["path"], content_hash):
            files_to_summarize.append((f, content_hash))

    console.print(f"[dim]요약 필요: {len(files_to_summarize)}개 / {len(all_files)}개[/dim]\n")

    # 요약 생성
    async def generate_summaries():
        model = get_default_model()

        for i, (file_data, content_hash) in enumerate(files_to_summarize):
            console.print(f"[{i+1}/{len(files_to_summarize)}] {file_data['path']} 요약 중...")

            summary_text = ""
            try:
                async for chunk in client.summarize_stream(file_data, model):
                    if chunk.get("type") == "token":
                        summary_text += chunk.get("content", "")
                    elif chunk.get("type") == "error":
                        console.print(f"  [red]오류: {chunk.get('message')}[/red]")
                        break

                if summary_text:
                    summary_store.save_summary(
                        file_data["path"],
                        content_hash,
                        summary_text,
                        file_data.get("language", "text")
                    )
                    console.print(f"  [green]완료[/green]")
            except Exception as e:
                console.print(f"  [red]오류: {e}[/red]")

    if files_to_summarize:
        asyncio.run(generate_summaries())
        console.print()

    # 임베딩 생성
    console.print("[bold]임베딩 생성 중...[/bold]")

    chunks = chunk_files(all_files, max_tokens=500, overlap_tokens=50)
    console.print(f"[dim]청크 {len(chunks)}개 생성됨[/dim]")

    async def generate_embeddings():
        # 배치로 임베딩 생성
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
                    console.print(f"  [{i + len(batch)}/{len(chunks)}] 임베딩 저장")
            except Exception as e:
                console.print(f"  [red]오류: {e}[/red]")

    asyncio.run(generate_embeddings())

    # 완료 통계
    console.print(f"\n[green]스캔 완료![/green]")
    console.print(f"  요약: {len(summary_store.get_all_summaries())}개 파일")
    console.print(f"  벡터: {vector_store.get_stats()['total_chunks']}개 청크")


@cli.command()
@click.argument("prompt")
@click.argument("paths", nargs=-1, type=click.Path(exists=True))
@click.option("--ext", "-e", default=None, help="확장자 필터 (예: .py,.js)")
@click.option("--model", "-m", default=None, help="사용할 모델")
@click.option("--rag/--no-rag", default=True, help="RAG 사용 여부")
def ask(prompt: str, paths: tuple, ext: str, model: str, rag: bool):
    """코드 분석 질문

    PROMPT: 질문 내용
    PATHS: 분석할 파일/디렉토리 (선택, 없으면 현재 디렉토리)
    """
    client = get_client()

    # 경로 처리
    if not paths:
        paths = (".",)

    base_path = Path(paths[0]).resolve()
    if base_path.is_file():
        base_path = base_path.parent

    # 확장자 파싱
    extensions = None
    if ext:
        extensions = [e.strip() for e in ext.split(",")]

    # 파일 스캔
    all_files = []
    for path_str in paths:
        path = Path(path_str)
        if path.is_file():
            file_data = scan_single_file(path)
            if file_data:
                all_files.append(file_data)
        else:
            files = scan_files(path, extensions=extensions)
            all_files.extend(files)

    # RAG 컨텍스트 구성
    context_files = all_files
    rag_used = False

    if rag and len(all_files) > 3:
        try:
            vector_store = VectorStore(base_path)
            summary_store = SummaryStore(base_path)

            if vector_store.get_stats()["total_chunks"] > 0:
                # 질문 임베딩
                async def get_relevant_chunks():
                    result = await client.embed([prompt])
                    query_embedding = result.get("embeddings", [[]])[0]

                    if query_embedding:
                        return vector_store.search(query_embedding, n_results=10)
                    return []

                relevant_chunks = asyncio.run(get_relevant_chunks())

                if relevant_chunks:
                    # 관련 파일만 컨텍스트에 포함
                    relevant_paths = set(c["metadata"]["path"] for c in relevant_chunks)
                    context_files = [f for f in all_files if f["path"] in relevant_paths]
                    rag_used = True

                    console.print(f"[dim]RAG: {len(relevant_chunks)}개 청크에서 {len(context_files)}개 파일 선택[/dim]")
        except Exception as e:
            console.print(f"[dim]RAG 비활성화: {e}[/dim]")

    if not context_files:
        console.print("[yellow]분석할 파일이 없습니다.[/yellow]")
        return

    if not rag_used:
        console.print(f"[dim]파일 {len(context_files)}개 분석 중...[/dim]\n")

    # 파일 목록 출력 (5개까지)
    for f in context_files[:5]:
        console.print(f"  [dim]- {f['path']}[/dim]")
    if len(context_files) > 5:
        console.print(f"  [dim]  ... 외 {len(context_files) - 5}개[/dim]")

    console.print()

    # API 호출
    model = model or get_default_model()

    async def run_analysis():
        try:
            async for chunk in client.analyze_stream(context_files, prompt, model):
                chunk_type = chunk.get("type")

                if chunk_type == "token":
                    content = chunk.get("content", "")
                    console.print(content, end="")

                elif chunk_type == "error":
                    console.print(f"\n[red]오류: {chunk.get('message')}[/red]")
                    return

                elif chunk_type == "done":
                    usage = chunk.get("usage", {})
                    console.print(f"\n\n[dim]토큰: {usage.get('total_tokens', '?')}[/dim]")

        except Exception as e:
            console.print(f"\n[red]오류: {e}[/red]")

    asyncio.run(run_analysis())


@cli.command()
@click.option("--model", "-m", default=None, help="사용할 모델")
def chat(model: str):
    """대화형 모드"""
    client = get_client()
    model = model or get_default_model()

    base_path = Path.cwd()
    history = ConversationHistory(base_path)

    # 프로젝트 컨텍스트 로드
    summaries = []
    try:
        summary_store = SummaryStore(base_path)
        summaries = summary_store.get_all_summaries()
    except Exception:
        pass

    console.print("[bold]대화형 모드[/bold]")
    console.print("[dim]종료: /quit | 히스토리 초기화: /clear[/dim]")

    if summaries:
        console.print(f"[dim]프로젝트 컨텍스트: {len(summaries)}개 파일 요약 로드됨[/dim]")
    console.print()

    # 시스템 메시지 구성
    system_content = "당신은 전문 코드 분석가입니다."
    if summaries:
        system_content += "\n\n## 프로젝트 파일 요약\n"
        for s in summaries[:20]:  # 최대 20개
            system_content += f"\n### {s['path']}\n{s['summary']}\n"

    async def chat_loop():
        while True:
            try:
                user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]종료[/dim]")
                break

            if not user_input.strip():
                continue

            if user_input.strip() == "/quit":
                console.print("[dim]종료[/dim]")
                break

            if user_input.strip() == "/clear":
                history.clear()
                console.print("[dim]히스토리 초기화됨[/dim]")
                continue

            # 메시지 구성
            messages = [{"role": "system", "content": system_content}]
            messages.extend(history.get_messages(limit=10))
            messages.append({"role": "user", "content": user_input})

            # 히스토리에 추가
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

                # 응답을 히스토리에 추가
                if response_text:
                    history.add_message("assistant", response_text)

            except Exception as e:
                console.print(f"\n[red]오류: {e}[/red]")

    asyncio.run(chat_loop())


@cli.command()
def clear():
    """프로젝트 인덱스 초기화"""
    base_path = Path.cwd()

    try:
        summary_store = SummaryStore(base_path)
        vector_store = VectorStore(base_path)
        history = ConversationHistory(base_path)

        summary_store.clear()
        vector_store.clear()
        history.clear()

        console.print("[green]인덱스 초기화 완료[/green]")
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")


def main():
    cli()


if __name__ == "__main__":
    main()
