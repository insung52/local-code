from typing import List, Dict
import re


def estimate_tokens(text: str) -> int:
    """토큰 수 대략 추정 (영어 기준 4글자 = 1토큰, 한글은 1글자 = 1토큰)"""
    # 간단한 추정: 공백으로 분리 + 한글 글자 수
    words = len(text.split())
    korean_chars = len(re.findall(r'[가-힣]', text))
    return words + korean_chars


def chunk_by_lines(
    content: str,
    max_lines: int = 100,
    overlap_lines: int = 10,
) -> List[Dict]:
    """
    줄 단위로 청킹

    Returns:
        [{"content": "...", "start_line": 1, "end_line": 100}, ...]
    """
    lines = content.split("\n")
    chunks = []

    i = 0
    while i < len(lines):
        end = min(i + max_lines, len(lines))
        chunk_lines = lines[i:end]
        chunk_content = "\n".join(chunk_lines)

        chunks.append({
            "content": chunk_content,
            "start_line": i + 1,
            "end_line": end,
        })

        # 다음 청크 시작점 (오버랩 적용)
        i = end - overlap_lines if end < len(lines) else len(lines)

    return chunks


def chunk_by_tokens(
    content: str,
    max_tokens: int = 1000,
    overlap_tokens: int = 100,
) -> List[Dict]:
    """
    토큰 단위로 청킹 (대략적 추정)

    Returns:
        [{"content": "...", "start_line": 1, "end_line": 50}, ...]
    """
    lines = content.split("\n")
    chunks = []

    current_chunk_lines = []
    current_tokens = 0
    start_line = 1

    for i, line in enumerate(lines):
        line_tokens = estimate_tokens(line)

        if current_tokens + line_tokens > max_tokens and current_chunk_lines:
            # 현재 청크 저장
            chunks.append({
                "content": "\n".join(current_chunk_lines),
                "start_line": start_line,
                "end_line": start_line + len(current_chunk_lines) - 1,
            })

            # 오버랩 적용
            overlap_lines_count = 0
            overlap_tokens_count = 0
            overlap_start = len(current_chunk_lines) - 1

            while overlap_start >= 0 and overlap_tokens_count < overlap_tokens:
                overlap_tokens_count += estimate_tokens(current_chunk_lines[overlap_start])
                overlap_lines_count += 1
                overlap_start -= 1

            if overlap_lines_count > 0:
                current_chunk_lines = current_chunk_lines[-overlap_lines_count:]
                start_line = start_line + len(current_chunk_lines) - overlap_lines_count
                current_tokens = sum(estimate_tokens(l) for l in current_chunk_lines)
            else:
                current_chunk_lines = []
                start_line = i + 1
                current_tokens = 0

        current_chunk_lines.append(line)
        current_tokens += line_tokens

    # 마지막 청크
    if current_chunk_lines:
        chunks.append({
            "content": "\n".join(current_chunk_lines),
            "start_line": start_line,
            "end_line": start_line + len(current_chunk_lines) - 1,
        })

    return chunks


def chunk_file(
    file_data: Dict,
    max_tokens: int = 1000,
    overlap_tokens: int = 100,
) -> List[Dict]:
    """
    파일을 청크로 분할

    Args:
        file_data: {"path": "...", "content": "...", "language": "..."}

    Returns:
        [{"id": "path:0", "content": "...", "metadata": {...}}, ...]
    """
    path = file_data["path"]
    content = file_data["content"]
    language = file_data.get("language", "text")

    # 파일이 작으면 청킹 안 함
    if estimate_tokens(content) <= max_tokens:
        return [{
            "id": f"{path}:0",
            "content": content,
            "metadata": {
                "path": path,
                "language": language,
                "chunk_index": 0,
                "start_line": 1,
                "end_line": content.count("\n") + 1,
            }
        }]

    chunks = chunk_by_tokens(content, max_tokens, overlap_tokens)

    return [
        {
            "id": f"{path}:{i}",
            "content": chunk["content"],
            "metadata": {
                "path": path,
                "language": language,
                "chunk_index": i,
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
            }
        }
        for i, chunk in enumerate(chunks)
    ]


def chunk_files(
    files: List[Dict],
    max_tokens: int = 1000,
    overlap_tokens: int = 100,
) -> List[Dict]:
    """여러 파일을 청크로 분할"""
    all_chunks = []
    for file_data in files:
        chunks = chunk_file(file_data, max_tokens, overlap_tokens)
        all_chunks.extend(chunks)
    return all_chunks
