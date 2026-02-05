"""Claude API 클라이언트"""

import json
import urllib.request
from typing import Optional, Generator


class ClaudeClient:
    """Claude API 클라이언트"""

    API_URL = "https://api.anthropic.com/v1/messages"
    MODEL = "claude-sonnet-4-20250514"
    MAX_SUMMARY_TOKENS = 1000

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _make_request(self, messages: list, system: str = None, max_tokens: int = 4096) -> dict:
        """API 요청"""
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
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else ""
            return {"error": f"HTTP {e.code}: {error_body}"}
        except Exception as e:
            return {"error": str(e)}

    def chat(self, messages: list, system: str = None) -> str:
        """단일 메시지 요청"""
        result = self._make_request(messages, system)

        if "error" in result:
            return f"[Claude Error] {result['error']}"

        # 응답 추출
        content = result.get("content", [])
        if content and len(content) > 0:
            return content[0].get("text", "")

        return "[Claude Error] Empty response"

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

        messages = [{"role": "user", "content": f"User request: {user_request}"}]

        if context:
            # 컨텍스트 압축 (MAX_SUMMARY_TOKENS 제한)
            if len(context) > self.MAX_SUMMARY_TOKENS * 4:
                context = context[: self.MAX_SUMMARY_TOKENS * 4] + "\n... (truncated)"
            messages[0]["content"] += f"\n\nContext:\n{context}"

        response = self.chat(messages, system)

        # JSON 파싱 시도
        try:
            # JSON 블록 추출
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

        messages = [
            {
                "role": "user",
                "content": f"Original request: {original_request}\n\nExecution result:\n{execution_result}",
            }
        ]

        response = self.chat(messages, system)

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


def test_connection(api_key: str) -> bool:
    """API 키 테스트"""
    client = ClaudeClient(api_key)
    result = client.chat([{"role": "user", "content": "Hi"}])
    return not result.startswith("[Claude Error]")
