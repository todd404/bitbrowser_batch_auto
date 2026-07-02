from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bitbrowser_auto.observability.artifacts import utc_now_iso
from bitbrowser_auto.runner.task import Task


class Storage:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("pragma journal_mode = wal")
        self.conn.execute("pragma foreign_keys = on")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Storage:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            create table if not exists tasks (
              id text primary key,
              browser_id text not null,
              flow_type text not null,
              flow text not null,
              goal text,
              inputs_json text not null default '{}',
              status text not null,
              retry_count integer not null default 0,
              last_error text,
              created_at text not null,
              updated_at text not null,
              started_at text,
              finished_at text
            );

            create table if not exists task_runs (
              id text primary key,
              task_id text not null,
              browser_id text not null,
              status text not null,
              ws text,
              pid integer,
              port text,
              started_at text not null,
              finished_at text,
              error text,
              artifact_dir text,
              trace_path text
            );

            create table if not exists browser_runtime (
              browser_id text primary key,
              status text not null,
              current_task_id text,
              ws text,
              pid integer,
              port text,
              updated_at text not null
            );
            """
        )

    def import_tasks(self, tasks: list[Task], *, replace: bool = False) -> dict[str, int]:
        created = 0
        updated = 0
        skipped = 0
        now = utc_now_iso()
        with self.conn:
            for task in tasks:
                existing = self.conn.execute("select id from tasks where id = ?", (task.id,)).fetchone()
                if existing and not replace:
                    skipped += 1
                    continue
                payload = (
                    task.id,
                    task.browser_id,
                    task.flow_type,
                    task.flow,
                    task.goal,
                    json.dumps(task.inputs, ensure_ascii=False),
                    "pending",
                    0,
                    None,
                    now,
                    now,
                    None,
                    None,
                )
                if existing:
                    self.conn.execute(
                        """
                        update tasks
                        set browser_id = ?, flow_type = ?, flow = ?, goal = ?, inputs_json = ?,
                            status = ?, retry_count = ?, last_error = ?, updated_at = ?,
                            started_at = ?, finished_at = ?
                        where id = ?
                        """,
                        (
                            task.browser_id,
                            task.flow_type,
                            task.flow,
                            task.goal,
                            json.dumps(task.inputs, ensure_ascii=False),
                            "pending",
                            0,
                            None,
                            now,
                            None,
                            None,
                            task.id,
                        ),
                    )
                    updated += 1
                else:
                    self.conn.execute(
                        """
                        insert into tasks (
                          id, browser_id, flow_type, flow, goal, inputs_json, status,
                          retry_count, last_error, created_at, updated_at, started_at, finished_at
                        )
                        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        payload,
                    )
                    created += 1
        return {"created": created, "updated": updated, "skipped": skipped}

    def list_tasks(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        sql = "select * from tasks"
        params: list[Any] = []
        if status:
            sql += " where status = ?"
            params.append(status)
        sql += " order by created_at asc limit ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def task_status_counts(self) -> dict[str, int]:
        rows = self.conn.execute("select status, count(*) as count from tasks group by status").fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}

    def recent_errors(self, *, limit: int = 5) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            select id, browser_id, flow_type, flow, last_error, updated_at
            from tasks
            where last_error is not null
            order by updated_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_task_runs(self, *, task_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        sql = "select * from task_runs"
        params: list[Any] = []
        if task_id:
            sql += " where task_id = ?"
            params.append(task_id)
        sql += " order by started_at desc limit ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def list_browser_runtime(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("select * from browser_runtime order by updated_at desc").fetchall()
        return [dict(row) for row in rows]

    def count_tasks(self, *, status: str | None = None) -> int:
        if status:
            row = self.conn.execute("select count(*) as count from tasks where status = ?", (status,)).fetchone()
        else:
            row = self.conn.execute("select count(*) as count from tasks").fetchone()
        return int(row["count"])

    def count_running_tasks(self) -> int:
        return self.count_tasks(status="running")

    def claim_pending_tasks(self, *, limit: int, busy_browser_ids: set[str] | None = None) -> list[Task]:
        if limit <= 0:
            return []
        busy_browser_ids = busy_browser_ids or set()
        now = utc_now_iso()
        claimed: list[Task] = []
        with self.conn:
            rows = self.conn.execute(
                """
                select * from tasks
                where status = 'pending'
                order by created_at asc
                limit ?
                """,
                (max(limit * 4, limit),),
            ).fetchall()
            for row in rows:
                if len(claimed) >= limit:
                    break
                if row["browser_id"] in busy_browser_ids:
                    continue
                updated = self.conn.execute(
                    """
                    update tasks
                    set status = 'running', updated_at = ?, started_at = coalesce(started_at, ?)
                    where id = ? and status = 'pending'
                    """,
                    (now, now, row["id"]),
                ).rowcount
                if updated:
                    claimed.append(_task_from_row(row))
        return claimed

    def release_to_pending(self, task_id: str) -> None:
        now = utc_now_iso()
        with self.conn:
            self.conn.execute(
                "update tasks set status = 'pending', updated_at = ? where id = ? and status = 'running'",
                (now, task_id),
            )

    def reset_running(self, *, status: str = "pending") -> int:
        if status not in {"pending", "failed"}:
            raise ValueError("reset status must be pending or failed")
        now = utc_now_iso()
        with self.conn:
            count = self.conn.execute(
                """
                update tasks
                set status = ?, updated_at = ?, finished_at = case when ? = 'failed' then ? else finished_at end,
                    last_error = case when ? = 'failed' then 'reset from running' else last_error end
                where status = 'running'
                """,
                (status, now, status, now, status),
            ).rowcount
            self.conn.execute(
                """
                update browser_runtime
                set status = 'idle', current_task_id = null, updated_at = ?
                where status in ('opening', 'running', 'closing')
                """,
                (now,),
            )
        return int(count)

    def create_task_run(self, task: Task, opened: dict[str, Any] | None = None) -> str:
        run_id = str(uuid.uuid4())
        now = utc_now_iso()
        opened = opened or {}
        with self.conn:
            self.conn.execute(
                """
                insert into task_runs (
                  id, task_id, browser_id, status, ws, pid, port, started_at,
                  finished_at, error, artifact_dir, trace_path
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task.id,
                    task.browser_id,
                    "running",
                    opened.get("ws"),
                    opened.get("pid"),
                    opened.get("http"),
                    now,
                    None,
                    None,
                    None,
                    None,
                ),
            )
        return run_id

    def finish_task_run(self, run_id: str, result: dict[str, Any]) -> None:
        now = utc_now_iso()
        opened = result.get("opened") or {}
        with self.conn:
            self.conn.execute(
                """
                update task_runs
                set status = ?, ws = coalesce(?, ws), pid = coalesce(?, pid), port = coalesce(?, port),
                    finished_at = ?, error = ?, artifact_dir = ?, trace_path = ?
                where id = ?
                """,
                (
                    result.get("status", "failed"),
                    opened.get("ws"),
                    opened.get("pid"),
                    opened.get("http"),
                    now,
                    result.get("error"),
                    result.get("artifact_dir"),
                    result.get("trace_path"),
                    run_id,
                ),
            )

    def mark_task_success(self, task_id: str) -> None:
        now = utc_now_iso()
        with self.conn:
            self.conn.execute(
                """
                update tasks
                set status = 'success', last_error = null, updated_at = ?, finished_at = ?
                where id = ?
                """,
                (now, now, task_id),
            )

    def mark_task_failed(self, task_id: str, error: str, *, retry: bool, increment_retry: bool = True) -> None:
        now = utc_now_iso()
        status = "pending" if retry else "failed"
        finished_at = None if retry else now
        retry_expr = "retry_count + 1" if increment_retry else "retry_count"
        with self.conn:
            self.conn.execute(
                f"""
                update tasks
                set status = ?, retry_count = {retry_expr}, last_error = ?, updated_at = ?, finished_at = ?
                where id = ?
                """,
                (status, error[:2000], now, finished_at, task_id),
            )

    def get_retry_count(self, task_id: str) -> int:
        row = self.conn.execute("select retry_count from tasks where id = ?", (task_id,)).fetchone()
        return int(row["retry_count"]) if row else 0

    def update_browser_runtime(
        self,
        browser_id: str,
        *,
        status: str,
        current_task_id: str | None = None,
        opened: dict[str, Any] | None = None,
    ) -> None:
        opened = opened or {}
        now = utc_now_iso()
        with self.conn:
            self.conn.execute(
                """
                insert into browser_runtime (browser_id, status, current_task_id, ws, pid, port, updated_at)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(browser_id) do update set
                  status = excluded.status,
                  current_task_id = excluded.current_task_id,
                  ws = excluded.ws,
                  pid = excluded.pid,
                  port = excluded.port,
                  updated_at = excluded.updated_at
                """,
                (
                    browser_id,
                    status,
                    current_task_id,
                    opened.get("ws"),
                    opened.get("pid"),
                    opened.get("http"),
                    now,
                ),
            )

    def task_to_json(self, task: Task) -> str:
        return json.dumps(asdict(task), ensure_ascii=False)


def _task_from_row(row: sqlite3.Row) -> Task:
    return Task(
        id=str(row["id"]),
        browser_id=str(row["browser_id"]),
        flow_type=str(row["flow_type"]),
        flow=str(row["flow"]),
        goal=str(row["goal"]) if row["goal"] else None,
        inputs=json.loads(row["inputs_json"] or "{}"),
    )
