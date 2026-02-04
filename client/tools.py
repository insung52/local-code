import os
import re
import subprocess
from pathlib import Path
from typing import Optional
import json


def list_files(path: str = ".", recursive: bool = False, max_depth: int = 2) -> dict:
    """디렉토리 파일 목록 조회"""
    try:
        base = Path(path).resolve()
        if not base.exists():
            return {"error": f"Path not found: {path}"}

        if not base.is_dir():
            return {"error": f"Not a directory: {path}"}

        files = []
        dirs = []

        def scan(p: Path, depth: int):
            if depth > max_depth:
                return
            try:
                for item in sorted(p.iterdir()):
                    # 무시 패턴
                    if item.name.startswith('.') or item.name in ['node_modules', '__pycache__', 'venv', '.venv', 'build', 'dist']:
                        continue

                    rel_path = str(item.relative_to(base))

                    if item.is_dir():
                        dirs.append(rel_path + "/")
                        if recursive:
                            scan(item, depth + 1)
                    else:
                        files.append(rel_path)
            except PermissionError:
                pass

        scan(base, 0)

        return {
            "path": str(base),
            "directories": dirs[:50],  # 최대 50개
            "files": files[:100],  # 최대 100개
            "total_dirs": len(dirs),
            "total_files": len(files),
        }
    except Exception as e:
        return {"error": str(e)}


def read_file(path: str, max_lines: int = 500) -> dict:
    """파일 내용 읽기"""
    try:
        file_path = Path(path).resolve()

        if not file_path.exists():
            return {"error": f"File not found: {path}"}

        if not file_path.is_file():
            return {"error": f"Not a file: {path}"}

        # 파일 크기 체크 (500KB 제한)
        if file_path.stat().st_size > 500 * 1024:
            return {"error": f"File too large: {path} (>500KB)"}

        content = file_path.read_text(encoding='utf-8', errors='replace')
        lines = content.split('\n')

        truncated = False
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            truncated = True

        return {
            "path": str(file_path),
            "content": '\n'.join(lines),
            "lines": len(lines),
            "truncated": truncated,
        }
    except Exception as e:
        return {"error": str(e)}


def search_code(query: str, path: str = ".", file_pattern: str = "*") -> dict:
    """코드 검색 (grep)"""
    try:
        base = Path(path).resolve()

        if not base.exists():
            return {"error": f"Path not found: {path}"}

        matches = []

        # 파일 패턴 처리
        if file_pattern == "*":
            patterns = ["*.py", "*.js", "*.ts", "*.cpp", "*.c", "*.h", "*.java", "*.go", "*.rs", "*.md", "*.json", "*.yaml", "*.yml"]
        else:
            patterns = [file_pattern]

        for pattern in patterns:
            for file_path in base.rglob(pattern):
                # 무시 패턴
                path_str = str(file_path)
                if any(ignore in path_str for ignore in ['node_modules', '__pycache__', '.git', 'venv', '.venv']):
                    continue

                try:
                    content = file_path.read_text(encoding='utf-8', errors='replace')
                    for i, line in enumerate(content.split('\n'), 1):
                        if query.lower() in line.lower():
                            matches.append({
                                "file": str(file_path.relative_to(base)),
                                "line": i,
                                "content": line.strip()[:200],
                            })
                            if len(matches) >= 50:
                                break
                except Exception:
                    continue

                if len(matches) >= 50:
                    break

            if len(matches) >= 50:
                break

        return {
            "query": query,
            "matches": matches,
            "total": len(matches),
            "truncated": len(matches) >= 50,
        }
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str) -> dict:
    """파일 쓰기 (실제 쓰기는 확인 후)"""
    # 이 함수는 실제로 쓰지 않고, 쓰기 요청 정보만 반환
    # 실제 쓰기는 사용자 확인 후 별도 처리
    try:
        file_path = Path(path).resolve()

        exists = file_path.exists()

        if exists:
            old_content = file_path.read_text(encoding='utf-8', errors='replace')
        else:
            old_content = ""

        return {
            "action": "write_file",
            "path": str(file_path),
            "exists": exists,
            "old_content": old_content,
            "new_content": content,
            "requires_confirmation": True,
        }
    except Exception as e:
        return {"error": str(e)}


# 도구 레지스트리
TOOLS = {
    "list_files": {
        "fn": list_files,
        "description": "List files and directories in a path",
        "parameters": {
            "path": "Directory path (default: current directory)",
            "recursive": "Include subdirectories (default: false)",
        }
    },
    "read_file": {
        "fn": read_file,
        "description": "Read file content",
        "parameters": {
            "path": "File path to read",
        }
    },
    "search_code": {
        "fn": search_code,
        "description": "Search for text in code files",
        "parameters": {
            "query": "Search query",
            "path": "Directory to search (default: current directory)",
        }
    },
    "write_file": {
        "fn": write_file,
        "description": "Write content to a file (requires user confirmation)",
        "parameters": {
            "path": "File path to write",
            "content": "Content to write",
        }
    },
}


def get_tools_prompt() -> str:
    """도구 설명 프롬프트 생성"""
    prompt = """You have access to the following tools to help answer questions about code:

## Available Tools

1. **list_files** - List files and directories
   Usage: <tool_call>{"tool": "list_files", "args": {"path": "."}}</tool_call>

2. **read_file** - Read file content
   Usage: <tool_call>{"tool": "read_file", "args": {"path": "src/main.py"}}</tool_call>

3. **search_code** - Search for text in code files
   Usage: <tool_call>{"tool": "search_code", "args": {"query": "def main", "path": "."}}</tool_call>

4. **write_file** - Write/modify a file (requires user confirmation)
   Usage: <tool_call>{"tool": "write_file", "args": {"path": "src/main.py", "content": "..."}}</tool_call>

## Instructions

- When you need to explore or understand code, use these tools
- First use list_files to see project structure, then read_file to examine specific files
- You can make multiple tool calls in sequence
- After gathering information, provide your analysis
- For file modifications, always use write_file tool (user will confirm)
- Always respond in Korean

## Tool Call Format

To call a tool, use this exact format:
<tool_call>{"tool": "tool_name", "args": {"param": "value"}}</tool_call>

You can include multiple tool calls, but put each on its own line.
"""
    return prompt


def parse_tool_calls(response: str) -> list[dict]:
    """응답에서 도구 호출 파싱"""
    tool_calls = []

    # 패턴 1: <tool_call>...</tool_call>
    pattern1 = r'<tool_call>\s*(\{[^}]+\})\s*</tool_call>'
    matches1 = re.findall(pattern1, response, re.DOTALL)

    for match in matches1:
        try:
            call = json.loads(match)
            if "tool" in call:
                tool_calls.append(call)
        except json.JSONDecodeError:
            continue

    # 패턴 2: ```json ... ``` 코드 블록 안에 tool/args
    pattern2 = r'```(?:json)?\s*(\{[^`]*"tool"[^`]*\})\s*```'
    matches2 = re.findall(pattern2, response, re.DOTALL)

    for match in matches2:
        try:
            call = json.loads(match)
            if "tool" in call:
                tool_calls.append(call)
        except json.JSONDecodeError:
            continue

    # 패턴 3: 그냥 {"tool": ...} 형태 (줄 단위)
    pattern3 = r'\{\s*"tool"\s*:\s*"(\w+)"\s*,\s*"args"\s*:\s*(\{[^}]*\})\s*\}'
    matches3 = re.findall(pattern3, response)

    for tool_name, args_str in matches3:
        try:
            args = json.loads(args_str)
            call = {"tool": tool_name, "args": args}
            # 중복 체크
            if call not in tool_calls:
                tool_calls.append(call)
        except json.JSONDecodeError:
            continue

    return tool_calls


def execute_tool(tool_name: str, args: dict) -> dict:
    """도구 실행"""
    if tool_name not in TOOLS:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        fn = TOOLS[tool_name]["fn"]
        return fn(**args)
    except Exception as e:
        return {"error": str(e)}
