"""Claude 클라이언트 - CLI/API 모드 지원"""

import json
import shutil
import subprocess
import urllib.request
from typing import Optional


def get_claude_path() -> str:
    """Claude CLI 경로 찾기"""
    # shutil.which로 PATH에서 찾기
    claude_path = shutil.which("claude")
    if claude_path:
        return claude_path
    # 못 찾으면 그냥 "claude" 반환 (shell=True에서 처리)
    return "claude"


class ClaudeClient:
    """
    Claude 클라이언트
    - cli 모드: claude -p 명령어 사용 (Pro 구독)
    - api 모드: Anthropic API 직접 호출 (크레딧)
    """

    API_URL = "https://api.anthropic.com/v1/messages"
    MODEL = "claude-sonnet-4-20250514"
    MAX_SUMMARY_TOKENS = 1000

    def __init__(self, mode: str = "cli", api_key: str = None):
        """
        Args:
            mode: "cli" (claude -p) 또는 "api" (Anthropic API)
            api_key: API 모드일 때 필요
        """
        self.mode = mode
        self.api_key = api_key

        if mode == "api" and not api_key:
            raise ValueError("API mode requires api_key")

    def _chat_cli(self, prompt: str, system: str = None) -> str:
        """CLI 모드: claude -p 실행"""
        try:
            # 시스템 프롬프트가 있으면 프롬프트에 포함
            full_prompt = prompt
            if system:
                full_prompt = f"[System: {system}]\n\n{prompt}"

            claude_path = get_claude_path()

            # subprocess.Popen으로 stdin 통해 프롬프트 전달
            process = subprocess.Popen(
                [claude_path, "-p", "-", "--output-format", "json"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            stdout, stderr = process.communicate(input=full_prompt, timeout=120)

            if process.returncode != 0:
                return f"[Claude CLI Error] {stderr}"

            try:
                data = json.loads(stdout)
                return data.get("result", "")
            except json.JSONDecodeError:
                # JSON 파싱 실패시 stdout 그대로 반환
                return stdout

        except subprocess.TimeoutExpired:
            process.kill()
            return "[Claude CLI Error] Timeout"
        except FileNotFoundError:
            return "[Claude CLI Error] claude command not found. Install Claude Code first."
        except Exception as e:
            return f"[Claude CLI Error] {str(e)}"

    def _chat_api(self, messages: list, system: str = None, max_tokens: int = 4096) -> str:
        """API 모드: Anthropic API 직접 호출"""
        payload = {
            "model": self.MODEL,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system:
            payload["system"] = system

        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self.API_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode())
                content = result.get("content", [])
                if content and len(content) > 0:
                    return content[0].get("text", "")
                return ""
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            return f"[Claude API Error] HTTP {e.code}: {error_body}"
        except Exception as e:
            return f"[Claude API Error] {str(e)}"

    def chat(self, prompt: str, system: str = None) -> str:
        """
        단일 메시지 요청

        Args:
            prompt: 사용자 프롬프트
            system: 시스템 프롬프트 (선택)

        Returns:
            Claude 응답 텍스트
        """
        if self.mode == "cli":
            return self._chat_cli(prompt, system)
        else:
            messages = [{"role": "user", "content": prompt}]
            return self._chat_api(messages, system)

    def plan(self, user_request: str, context: str = None) -> dict:
        """
        작업 계획 수립 요청

        Returns:
            {
                "plan": "계획 내용",
                "steps": ["단계1", "단계2", ...],
                "needs_more_info": False,
                "questions": []
            }
        """
        system = """You are a code assistant supervisor. Create a clear execution plan.

Respond in JSON format:
{
    "plan": "Brief description of the approach",
    "steps": ["Step 1: ...", "Step 2: ...", ...],
    "needs_more_info": false,
    "questions": []
}

If you need more information before planning, set needs_more_info to true and list questions.

Keep plans concise and actionable. Focus on what needs to be done, not how (the executor will handle details).
Respond in the same language as the user request."""

        prompt = f"User request: {user_request}"

        if context:
            # 컨텍스트 압축
            if len(context) > self.MAX_SUMMARY_TOKENS * 4:
                context = context[: self.MAX_SUMMARY_TOKENS * 4] + "\n... (truncated)"
            prompt += f"\n\nContext:\n{context}"

        response = self.chat(prompt, system)

        # JSON 파싱 시도
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response

            return json.loads(json_str.strip())
        except json.JSONDecodeError:
            return {
                "plan": response,
                "steps": [],
                "needs_more_info": False,
                "questions": [],
            }

    def review(self, original_request: str, execution_result: str) -> dict:
        """
        실행 결과 검토 및 다음 단계 결정

        Returns:
            {
                "status": "completed" | "continue" | "failed",
                "feedback": "피드백 내용",
                "next_steps": ["다음 단계", ...] (continue인 경우)
            }
        """
        system = """You are reviewing the execution result of a task.

Respond in JSON format:
{
    "status": "completed" | "continue" | "failed",
    "feedback": "Brief feedback on the result",
    "next_steps": ["Next step 1", ...]
}

- "completed": Task is done successfully
- "continue": More work needed, provide next_steps
- "failed": Task failed, explain in feedback

Be concise. Respond in the same language as the original request."""

        # 결과 압축
        if len(execution_result) > self.MAX_SUMMARY_TOKENS * 4:
            execution_result = execution_result[: self.MAX_SUMMARY_TOKENS * 4] + "\n... (truncated)"

        prompt = f"Original request: {original_request}\n\nExecution result:\n{execution_result}"

        response = self.chat(prompt, system)

        # JSON 파싱
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response

            return json.loads(json_str.strip())
        except json.JSONDecodeError:
            return {
                "status": "completed",
                "feedback": response,
                "next_steps": [],
            }


def test_cli_available() -> bool:
    """Claude CLI 사용 가능한지 테스트"""
    try:
        claude_path = get_claude_path()

        # shutil.which가 None 반환하면 못 찾은 것
        if claude_path == "claude" and not shutil.which("claude"):
            return False

        result = subprocess.run(
            [claude_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def test_api_key(api_key: str) -> bool:
    """API 키 테스트"""
    client = ClaudeClient(mode="api", api_key=api_key)
    result = client.chat("Hi")
    return not result.startswith("[Claude")
