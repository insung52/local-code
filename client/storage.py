import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict
import hashlib

# 프로젝트 설정 디렉토리
PROJECT_DIR = ".llmcode"


def get_project_dir(base_path: Path) -> Path:
    """프로젝트 .llmcode 디렉토리 경로"""
    project_dir = base_path / PROJECT_DIR
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def get_file_hash(content: str) -> str:
    """파일 내용의 해시값"""
    return hashlib.md5(content.encode()).hexdigest()[:16]


class SummaryStore:
    """파일 요약 저장소 (SQLite)"""

    def __init__(self, base_path: Path):
        self.db_path = get_project_dir(base_path) / "summaries.db"
        self._init_db()

    def _init_db(self):
        """데이터베이스 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                path TEXT PRIMARY KEY,
                content_hash TEXT,
                summary TEXT,
                language TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def get_summary(self, path: str) -> Optional[Dict]:
        """요약 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT path, content_hash, summary, language FROM summaries WHERE path = ?",
            (path,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "path": row[0],
                "content_hash": row[1],
                "summary": row[2],
                "language": row[3],
            }
        return None

    def save_summary(self, path: str, content_hash: str, summary: str, language: str):
        """요약 저장"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO summaries (path, content_hash, summary, language, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (path, content_hash, summary, language))
        conn.commit()
        conn.close()

    def get_all_summaries(self) -> List[Dict]:
        """모든 요약 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT path, content_hash, summary, language FROM summaries")
        rows = cursor.fetchall()
        conn.close()

        return [
            {"path": row[0], "content_hash": row[1], "summary": row[2], "language": row[3]}
            for row in rows
        ]

    def needs_update(self, path: str, content_hash: str) -> bool:
        """요약 업데이트 필요 여부"""
        existing = self.get_summary(path)
        if not existing:
            return True
        return existing["content_hash"] != content_hash

    def clear(self):
        """모든 요약 삭제"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM summaries")
        conn.commit()
        conn.close()


class VectorStore:
    """벡터 저장소 (ChromaDB)"""

    def __init__(self, base_path: Path):
        import chromadb
        from chromadb.config import Settings

        self.db_path = get_project_dir(base_path) / "vectors"
        self.db_path.mkdir(parents=True, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name="code_chunks",
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunks(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict],
    ):
        """청크 추가/업데이트"""
        # 기존 ID 삭제 후 추가
        existing_ids = self.collection.get(ids=ids)["ids"]
        if existing_ids:
            self.collection.delete(ids=existing_ids)

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def search(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        where: Optional[Dict] = None,
    ) -> List[Dict]:
        """유사 청크 검색"""
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                chunks.append({
                    "id": chunk_id,
                    "content": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                })

        return chunks

    def get_stats(self) -> Dict:
        """저장소 통계"""
        return {
            "total_chunks": self.collection.count(),
        }

    def clear(self):
        """모든 벡터 삭제"""
        # 컬렉션 삭제 후 재생성
        self.client.delete_collection("code_chunks")
        self.collection = self.client.get_or_create_collection(
            name="code_chunks",
            metadata={"hnsw:space": "cosine"}
        )


class ConversationHistory:
    """대화 히스토리 관리"""

    def __init__(self, base_path: Path):
        self.history_file = get_project_dir(base_path) / "history.json"
        self.messages: List[Dict] = []
        self._load()

    def _load(self):
        """히스토리 로드"""
        if self.history_file.exists():
            try:
                data = json.loads(self.history_file.read_text(encoding="utf-8"))
                self.messages = data.get("messages", [])
            except (json.JSONDecodeError, KeyError):
                self.messages = []

    def _save(self):
        """히스토리 저장"""
        self.history_file.write_text(
            json.dumps({"messages": self.messages}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def add_message(self, role: str, content: str):
        """메시지 추가"""
        self.messages.append({"role": role, "content": content})
        self._save()

    def get_messages(self, limit: int = 20) -> List[Dict]:
        """최근 메시지 조회"""
        return self.messages[-limit:]

    def clear(self):
        """히스토리 초기화"""
        self.messages = []
        self._save()
