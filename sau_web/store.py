from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager, closing
from pathlib import Path

ACTIVE = {"queued", "running"}
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted", "unknown"}


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, database: Path):
        self.database = Path(database)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.database, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def migrate(self):
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < 2:
                # Use SQLite's backup API: it includes committed WAL pages as well.
                backup = self.database.with_name(
                    f"database.pre-v2.{uuid.uuid4().hex[:8]}.db"
                )
                with closing(sqlite3.connect(backup)) as destination:
                    conn.backup(destination)
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS web_tasks (
                        id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'queued', phase TEXT NOT NULL DEFAULT '等待执行',
                        progress REAL, payload TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}',
                        error TEXT, detail TEXT, parent_id TEXT, account_id INTEGER, material_id INTEGER,
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS web_batches (
                        id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                        fingerprint TEXT NOT NULL, created_at TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS web_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,
                        event TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS web_tasks_status ON web_tasks(status, kind);
                    CREATE INDEX IF NOT EXISTS web_tasks_parent ON web_tasks(parent_id);
                    CREATE INDEX IF NOT EXISTS web_events_task ON web_events(task_id, id);
                    PRAGMA user_version=2;
                """)
            conn.execute("PRAGMA journal_mode=WAL")

    @staticmethod
    def decode(row):
        if row is None:
            raise KeyError("记录不存在")
        data = dict(row)
        data["payload"] = json.loads(data["payload"])
        data["result"] = json.loads(data["result"])
        return data

    def get(self, task_id):
        with self.connect() as conn:
            return self.decode(
                conn.execute(
                    "SELECT * FROM web_tasks WHERE id=?", (task_id,)
                ).fetchone()
            )

    def list(self, kind=None, parent_id=None, limit=200):
        where, args = [], []
        if kind:
            where.append("kind=?")
            args.append(kind)
        if parent_id:
            where.append("parent_id=?")
            args.append(parent_id)
        query = "SELECT * FROM web_tasks"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY created_at DESC, id DESC LIMIT ?"
        with self.connect() as conn:
            return [self.decode(row) for row in conn.execute(query, (*args, limit))]

    def _insert(
        self,
        conn,
        kind,
        title,
        payload,
        parent_id=None,
        account_id=None,
        material_id=None,
    ):
        task_id, stamp = uuid.uuid4().hex, now()
        conn.execute(
            "INSERT INTO web_tasks(id,kind,title,payload,parent_id,account_id,material_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                task_id,
                kind,
                title,
                json.dumps(payload, ensure_ascii=False),
                parent_id,
                account_id,
                material_id,
                stamp,
                stamp,
            ),
        )
        self._event(conn, task_id, "task", {"id": task_id, "status": "queued"})
        return task_id

    def create(self, kind, title, payload, **kwargs):
        with self.connect() as conn:
            return self._insert(conn, kind, title, payload, **kwargs)

    def create_batch(self, key, fingerprint, jobs):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM web_batches WHERE request_key=?", (key,)
            ).fetchone()
            if row:
                if row["fingerprint"] != fingerprint:
                    raise Conflict("同一提交标识不能用于不同的发布内容")
                return row["id"]
            batch_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO web_batches VALUES(?,?,?,?)",
                (batch_id, key, fingerprint, now()),
            )
            for job in jobs:
                self._insert(
                    conn,
                    "publish",
                    job["title"],
                    job,
                    parent_id=batch_id,
                    account_id=job["account_id"],
                    material_id=job["material_id"],
                )
            return batch_id

    def create_youtube_download(self, key, fingerprint, payload):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            key = "youtube:" + key
            existing = conn.execute("SELECT * FROM web_batches WHERE request_key=?", (key,)).fetchone()
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise Conflict("同一提交标识不能用于不同的视频或发布内容")
                row = conn.execute("SELECT id FROM web_tasks WHERE parent_id=? AND kind='download'", (existing["id"],)).fetchone()
                if not row:
                    raise Conflict("此提交的任务记录已删除，请重新发起")
                return row["id"]
            batch_id = uuid.uuid4().hex
            conn.execute("INSERT INTO web_batches VALUES(?,?,?,?)", (batch_id, key, fingerprint, now()))
            return self._insert(conn, "download", payload["url"], payload, parent_id=batch_id)

    def finish_download(self, task_id, result):
        """Commit the download result and its publishing jobs together, exactly once."""
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            task = self.decode(conn.execute("SELECT * FROM web_tasks WHERE id=?", (task_id,)).fetchone())
            if task["status"] != "running":
                return
            jobs = task["payload"].get("publish_jobs", [])
            problem = None
            for job in jobs:
                account = conn.execute("SELECT status FROM user_info WHERE id=?", (job["account_id"],)).fetchone()
                if not account or account["status"] != 1:
                    problem = "下载完成，但所选账号已失效或被删除，请登录后从素材库发布"
                    break
            publish_ids = []
            if jobs and not problem:
                material = conn.execute("SELECT filename FROM file_records WHERE id=?", (result.get("materialId"),)).fetchone()
                if not material:
                    problem = "下载完成，但素材记录不存在，未创建发布任务"
                else:
                    for job in jobs:
                        payload = {**job, "material_id": result["materialId"], "filename": material["filename"]}
                        publish_ids.append(self._insert(conn, "publish", job["title"], payload,
                            parent_id=task_id, account_id=job["account_id"], material_id=result["materialId"]))
            result = {**result, "publishTaskIds": publish_ids}
            conn.execute("UPDATE web_tasks SET status='succeeded',phase=?,progress=100,result=?,error=?,updated_at=? WHERE id=?",
                ("下载完成，已创建发布任务" if publish_ids else "下载完成", json.dumps(result, ensure_ascii=False), problem, now(), task_id))
            self._event(conn, task_id, "task", {"id": task_id, "status": "succeeded"})
            self._mark_retry_result(conn, task_id, "succeeded")

    def batch(self, batch_id):
        with self.connect() as conn:
            if not conn.execute(
                "SELECT 1 FROM web_batches WHERE id=?", (batch_id,)
            ).fetchone():
                raise KeyError("发布批次不存在")
        return {"id": batch_id, "tasks": self.list(parent_id=batch_id, limit=10000)}

    def update(self, task_id, **fields):
        allowed = {"status", "phase", "progress", "result", "error", "detail"}
        if not fields.keys() <= allowed:
            raise ValueError("Invalid task update")
        if "result" in fields:
            fields["result"] = json.dumps(fields["result"], ensure_ascii=False)
        fields["updated_at"] = now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE web_tasks SET "
                + ",".join(f"{key}=?" for key in fields)
                + " WHERE id=?",
                (*fields.values(), task_id),
            )
            self._event(conn, task_id, "task", {"id": task_id})
            if fields.get("status") in {"succeeded", "unknown"}:
                self._mark_retry_result(conn, task_id, fields["status"])

    def _mark_retry_result(self, conn, task_id, status):
        """Retain retry outcomes on ancestors even when history rows are deleted."""
        task = conn.execute(
            "SELECT kind,parent_id FROM web_tasks WHERE id=?", (task_id,)
        ).fetchone()
        while task and task["parent_id"]:
            parent = conn.execute(
                "SELECT * FROM web_tasks WHERE id=?", (task["parent_id"],)
            ).fetchone()
            if not parent or parent["kind"] != task["kind"]:
                break
            result = json.loads(parent["result"])
            result["retry_status"] = status
            conn.execute(
                "UPDATE web_tasks SET result=?,updated_at=? WHERE id=?",
                (json.dumps(result, ensure_ascii=False), now(), parent["id"]),
            )
            self._event(conn, parent["id"], "task", {"id": parent["id"]})
            task = parent

    def claim(self, task_id):
        with self.connect() as conn:
            changed = conn.execute(
                "UPDATE web_tasks SET status='running', phase='准备执行', updated_at=? WHERE id=? AND status='queued'",
                (now(), task_id),
            ).rowcount
            if changed:
                self._event(conn, task_id, "task", {"id": task_id, "status": "running"})
            return bool(changed)

    def recover(self):
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id,kind,result FROM web_tasks WHERE status='running'"
            ).fetchall()
            for row in rows:
                status = "unknown" if row["kind"] == "publish" else "interrupted"
                if row["kind"] == "publish" and json.loads(row["result"]).get(
                    "confirmed"
                ):
                    status = "succeeded"
                phase = (
                    "发布成功"
                    if status == "succeeded"
                    else (
                        "结果待核实，请先到平台确认"
                        if status == "unknown"
                        else "执行已中断，可重新尝试"
                    )
                )
                conn.execute(
                    "UPDATE web_tasks SET status=?,phase=?,updated_at=? WHERE id=?",
                    (status, phase, now(), row["id"]),
                )
                self._event(
                    conn, row["id"], "task", {"id": row["id"], "status": status}
                )
                if status in {"succeeded", "unknown"}:
                    self._mark_retry_result(conn, row["id"], status)

    @staticmethod
    def _event(conn, task_id, event, data):
        conn.execute(
            "INSERT INTO web_events(task_id,event,data,created_at) VALUES(?,?,?,?)",
            (task_id, event, json.dumps(data, ensure_ascii=False), now()),
        )

    def event(self, task_id, event, data):
        with self.connect() as conn:
            self._event(conn, task_id, event, data)

    def events(self, after=0, task_id=None, limit=200):
        with self.connect() as conn:
            if task_id:
                rows = conn.execute(
                    "SELECT * FROM web_events WHERE task_id=? AND id>? ORDER BY id LIMIT ?",
                    (task_id, after, limit),
                )
            else:
                rows = conn.execute(
                    "SELECT * FROM web_events WHERE id>? ORDER BY id LIMIT ?",
                    (after, limit),
                )
            return [{**dict(row), "data": json.loads(row["data"])} for row in rows]

    def latest_event(self):
        with self.connect() as conn:
            return conn.execute(
                "SELECT coalesce(max(id),0) FROM web_events"
            ).fetchone()[0]

    def busy(self, resource, resource_id):
        column = {"account": "account_id", "material": "material_id"}[resource]
        with self.connect() as conn:
            return bool(
                conn.execute(
                    f"SELECT 1 FROM web_tasks WHERE {column}=? AND status IN ('queued','running')",
                    (resource_id,),
                ).fetchone()
            )

    def cancel(self, task_id):
        with self.connect() as conn:
            changed = conn.execute(
                "UPDATE web_tasks SET status='cancelled',phase='已取消',updated_at=? WHERE id=? AND status='queued'",
                (now(), task_id),
            ).rowcount
            if not changed:
                raise Conflict("只能取消尚未执行的任务")
            self._event(conn, task_id, "task", {"id": task_id, "status": "cancelled"})

    def retry_chain(self, task_id):
        with self.connect() as conn:
            rows = conn.execute(
                """
                WITH RECURSIVE descendants(id) AS (
                    SELECT id FROM web_tasks WHERE parent_id=?
                    UNION ALL
                    SELECT t.id FROM web_tasks t JOIN descendants d ON t.parent_id=d.id
                )
                SELECT t.* FROM web_tasks t JOIN descendants d ON t.id=d.id ORDER BY created_at DESC
            """,
                (task_id,),
            ).fetchall()
            return [self.decode(row) for row in rows]

    def delete(self, task_id):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status FROM web_tasks WHERE id=?", (task_id,)
            ).fetchone()
            if not row:
                raise KeyError("任务不存在")
            if row["status"] in ACTIVE:
                raise Conflict("请等待任务结束后再删除记录")
            conn.execute("DELETE FROM web_events WHERE task_id=?", (task_id,))
            conn.execute("DELETE FROM web_tasks WHERE id=?", (task_id,))
            self._event(conn, None, "refresh", {})
