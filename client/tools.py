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


def read_file(path: str, line_start: int = None, line_end: int = None, max_lines: int = 500) -> dict:
    """
    파일 내용 읽기
    - line_start/line_end: 특정 줄 범위만 읽기 (1-based)
    - max_lines: 최대 줄 수 (기본 500)
    """
    try:
        file_path = Path(path).resolve()

        if not file_path.exists():
            return {"error": f"File not found: {path}"}

        if not file_path.is_file():
            return {"error": f"Not a file: {path}"}

        # 파일 크기 체크 (1MB 제한, 범위 지정시 더 큼)
        file_size = file_path.stat().st_size
        if file_size > 1024 * 1024 and line_start is None:
            return {
                "error": f"File too large: {path} ({file_size // 1024}KB)",
                "hint": "Use search_code first to find line numbers, then read_file with line_start/line_end",
                "total_lines": sum(1 for _ in open(file_path, encoding='utf-8', errors='replace'))
            }

        content = file_path.read_text(encoding='utf-8', errors='replace')
        all_lines = content.split('\n')
        total_lines = len(all_lines)

        # 범위 지정된 경우
        if line_start is not None:
            start_idx = max(0, line_start - 1)  # 1-based to 0-based
            end_idx = line_end if line_end else start_idx + max_lines
            end_idx = min(end_idx, total_lines)

            lines = all_lines[start_idx:end_idx]
            # 줄 번호 포함해서 반환
            numbered_lines = [f"{i}: {line}" for i, line in enumerate(lines, start=start_idx + 1)]

            return {
                "path": str(file_path),
                "content": '\n'.join(numbered_lines),
                "line_range": f"{start_idx + 1}-{end_idx}",
                "total_lines": total_lines,
                "lines_read": len(lines),
            }

        # 전체 읽기 (max_lines 제한)
        truncated = False
        if total_lines > max_lines:
            lines = all_lines[:max_lines]
            truncated = True
        else:
            lines = all_lines

        return {
            "path": str(file_path),
            "content": '\n'.join(lines),
            "lines": len(lines),
            "total_lines": total_lines,
            "truncated": truncated,
            "hint": "Use line_start/line_end to read specific sections" if truncated else None,
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


def git_status(path: str = ".") -> dict:
    """Git 상태 확인"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return {"error": result.stderr or "Not a git repository"}

        lines = result.stdout.strip().split('\n') if result.stdout.strip() else []

        changes = []
        for line in lines:
            if len(line) >= 3:
                status = line[:2].strip()
                file_path = line[3:]
                changes.append({"status": status, "file": file_path})

        # 현재 브랜치
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=5
        )
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

        return {
            "branch": branch,
            "changes": changes,
            "total_changes": len(changes),
            "clean": len(changes) == 0
        }
    except subprocess.TimeoutExpired:
        return {"error": "Git command timed out"}
    except FileNotFoundError:
        return {"error": "Git not installed"}
    except Exception as e:
        return {"error": str(e)}


def git_diff(path: str = ".", file: str = None, staged: bool = False) -> dict:
    """Git diff 확인"""
    try:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        if file:
            cmd.append("--")
            cmd.append(file)

        result = subprocess.run(
            cmd,
            cwd=path,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            return {"error": result.stderr or "Git diff failed"}

        diff_output = result.stdout

        # 너무 길면 자르기
        if len(diff_output) > 10000:
            diff_output = diff_output[:10000] + "\n... (truncated)"

        return {
            "diff": diff_output,
            "staged": staged,
            "file": file,
            "has_changes": len(diff_output.strip()) > 0
        }
    except subprocess.TimeoutExpired:
        return {"error": "Git command timed out"}
    except FileNotFoundError:
        return {"error": "Git not installed"}
    except Exception as e:
        return {"error": str(e)}


def run_command(command: str, path: str = ".", timeout: int = 30) -> dict:
    """터미널 명령 실행 (확인 필요)"""
    # 위험한 명령 차단
    dangerous = ["rm -rf", "del /", "format", "mkfs", ":(){", "fork bomb"]
    cmd_lower = command.lower()
    for d in dangerous:
        if d in cmd_lower:
            return {"error": f"Dangerous command blocked: {d}"}

    return {
        "action": "run_command",
        "command": command,
        "path": path,
        "timeout": timeout,
        "requires_confirmation": True,
    }


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
        "description": "Read file content (supports line ranges for large files)",
        "parameters": {
            "path": "File path to read",
            "line_start": "Start line number (1-based, optional)",
            "line_end": "End line number (optional)",
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
    "git_status": {
        "fn": git_status,
        "description": "Check git status (branch, changed files)",
        "parameters": {
            "path": "Repository path (default: current directory)",
        }
    },
    "git_diff": {
        "fn": git_diff,
        "description": "Show git diff",
        "parameters": {
            "path": "Repository path",
            "file": "Specific file (optional)",
            "staged": "Show staged changes (default: false)",
        }
    },
    "run_command": {
        "fn": run_command,
        "description": "Run terminal command (requires user confirmation)",
        "parameters": {
            "command": "Command to run",
            "path": "Working directory",
        }
    },
}


def get_tools_prompt() -> str:
    """도구 설명 프롬프트 생성"""
    prompt = """You are a code assistant. Be accurate and thorough.

## Thinking Process
ALWAYS use <think> tags to analyze before acting:

<think>
- What does the user want exactly?
- What is the exact path/file mentioned? (Use FULL path if provided)
- What tools do I need?
- What could go wrong?
</think>

Use <think> tags also when:
- A tool fails → analyze why and how to fix
- Command output needs interpretation
- Complex decisions required
- Errors occur

## Tools
- list_files: {"tool": "list_files", "args": {"path": "."}}
- read_file: {"tool": "read_file", "args": {"path": "file.py"}}
- read_file (range): {"tool": "read_file", "args": {"path": "file.py", "line_start": 100, "line_end": 150}}
- search_code: {"tool": "search_code", "args": {"query": "keyword"}}
- write_file: {"tool": "write_file", "args": {"path": "file.py", "content": "..."}}
- git_status: {"tool": "git_status", "args": {"path": "."}}
- git_diff: {"tool": "git_diff", "args": {"path": ".", "file": "optional.py"}}
- run_command: {"tool": "run_command", "args": {"command": "npm test"}}

## Large File Strategy
For large files (>500 lines or truncated):
1. Use search_code to find relevant line numbers first
2. Then use read_file with line_start/line_end to read specific sections
3. Never try to read entire large files at once

## Rules
1. ALWAYS think first with <think> tags before using tools.
2. Use EXACT paths provided by user. Never shorten or modify paths.
3. If a tool fails, analyze in <think> and retry with corrected approach.
4. After task completion, give a brief summary. Don't show full file contents.
5. Respond in the same language as the user. Default to Korean if unclear.
6. For file writes and commands, just call the tool. User will confirm.

## Format
{"tool": "tool_name", "args": {...}}
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
