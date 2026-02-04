import json
from pathlib import Path
from typing import Optional

# 전역 설정 파일 위치
GLOBAL_CONFIG_DIR = Path.home() / ".llmcode"
GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.json"

# 프로젝트 설정 디렉토리 이름
PROJECT_CONFIG_DIR = ".llmcode"


def get_global_config() -> dict:
    """전역 설정 로드"""
    if GLOBAL_CONFIG_FILE.exists():
        return json.loads(GLOBAL_CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def save_global_config(config: dict) -> None:
    """전역 설정 저장"""
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    GLOBAL_CONFIG_FILE.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def get_project_config(project_path: Path) -> dict:
    """프로젝트 설정 로드"""
    config_file = project_path / PROJECT_CONFIG_DIR / "config.json"
    if config_file.exists():
        return json.loads(config_file.read_text(encoding="utf-8"))
    return {}


def save_project_config(project_path: Path, config: dict) -> None:
    """프로젝트 설정 저장"""
    config_dir = project_path / PROJECT_CONFIG_DIR
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"
    config_file.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def get_server_url() -> Optional[str]:
    """서버 URL 가져오기 (프로젝트 > 전역 순서)"""
    # 현재 디렉토리의 프로젝트 설정 확인
    project_config = get_project_config(Path.cwd())
    if project_config.get("server_url"):
        return project_config["server_url"]

    # 전역 설정 확인
    global_config = get_global_config()
    return global_config.get("server_url")


def get_api_key() -> Optional[str]:
    """API 키 가져오기 (프로젝트 > 전역 순서)"""
    project_config = get_project_config(Path.cwd())
    if project_config.get("api_key"):
        return project_config["api_key"]

    global_config = get_global_config()
    return global_config.get("api_key")


def get_default_model() -> str:
    """기본 모델 가져오기"""
    project_config = get_project_config(Path.cwd())
    if project_config.get("default_model"):
        return project_config["default_model"]

    global_config = get_global_config()
    return global_config.get("default_model", "llama3.2:3b")
