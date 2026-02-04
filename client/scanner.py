from pathlib import Path
from typing import List, Optional
import fnmatch

# 기본 무시 패턴
DEFAULT_IGNORE_PATTERNS = [
    # 디렉토리
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".env",
    "build",
    "dist",
    ".llmcode",

    # 파일
    "*.pyc",
    "*.pyo",
    "*.exe",
    "*.dll",
    "*.so",
    "*.dylib",
    "*.bin",
    "*.obj",
    "*.o",
    "*.a",
    "*.lib",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.pdf",
    "*.zip",
    "*.tar",
    "*.gz",
    "*.rar",
    "*.7z",
    ".DS_Store",
    "Thumbs.db",
    "*.lock",
    "package-lock.json",
]

# 기본 확장자 (코드 파일)
DEFAULT_EXTENSIONS = [
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".c", ".cpp", ".cc", ".h", ".hpp",
    ".java", ".kt", ".scala",
    ".go", ".rs", ".rb",
    ".php", ".swift", ".m", ".mm",
    ".cs", ".fs",
    ".lua", ".pl", ".pm",
    ".sh", ".bash", ".zsh",
    ".sql", ".graphql",
    ".html", ".css", ".scss", ".sass", ".less",
    ".json", ".yaml", ".yml", ".toml", ".xml",
    ".md", ".rst", ".txt",
    ".hlsl", ".glsl", ".vert", ".frag", ".comp",
]


def should_ignore(path: Path, ignore_patterns: List[str]) -> bool:
    """파일/디렉토리를 무시해야 하는지 확인"""
    name = path.name

    for pattern in ignore_patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
        if fnmatch.fnmatch(str(path), f"*/{pattern}/*"):
            return True

    return False


def get_language_from_extension(ext: str) -> str:
    """확장자로 언어 추론"""
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".c": "c",
        ".cpp": "cpp",
        ".cc": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".java": "java",
        ".kt": "kotlin",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".cs": "csharp",
        ".lua": "lua",
        ".sh": "bash",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".xml": "xml",
        ".md": "markdown",
        ".hlsl": "hlsl",
        ".glsl": "glsl",
        ".vert": "glsl",
        ".frag": "glsl",
    }
    return mapping.get(ext.lower(), "text")


def scan_files(
    path: Path,
    extensions: Optional[List[str]] = None,
    ignore_patterns: Optional[List[str]] = None,
    max_file_size: int = 200 * 1024,  # 200KB
) -> List[dict]:
    """
    디렉토리/파일 스캔

    Returns:
        [{"path": "relative/path", "content": "...", "language": "python"}, ...]
    """
    if extensions is None:
        extensions = DEFAULT_EXTENSIONS

    if ignore_patterns is None:
        ignore_patterns = DEFAULT_IGNORE_PATTERNS

    # 확장자 정규화 (점 추가)
    extensions = [ext if ext.startswith(".") else f".{ext}" for ext in extensions]

    files = []
    base_path = path.resolve()

    if path.is_file():
        # 단일 파일
        files_to_scan = [path]
    else:
        # 디렉토리
        files_to_scan = []
        for file_path in path.rglob("*"):
            if file_path.is_file():
                files_to_scan.append(file_path)

    for file_path in files_to_scan:
        # 무시 패턴 확인
        if should_ignore(file_path, ignore_patterns):
            continue

        # 확장자 확인
        if extensions and file_path.suffix.lower() not in extensions:
            continue

        # 파일 크기 확인
        try:
            if file_path.stat().st_size > max_file_size:
                continue
        except OSError:
            continue

        # 파일 읽기
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            # 바이너리 파일이거나 읽기 실패
            continue

        # 상대 경로 계산
        try:
            relative_path = file_path.relative_to(base_path)
        except ValueError:
            relative_path = file_path.name

        files.append({
            "path": str(relative_path).replace("\\", "/"),
            "content": content,
            "language": get_language_from_extension(file_path.suffix),
        })

    return files


def scan_single_file(file_path: Path) -> Optional[dict]:
    """단일 파일 스캔"""
    if not file_path.exists() or not file_path.is_file():
        return None

    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None

    return {
        "path": file_path.name,
        "content": content,
        "language": get_language_from_extension(file_path.suffix),
    }
