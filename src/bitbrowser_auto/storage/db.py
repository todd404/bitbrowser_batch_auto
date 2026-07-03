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
              batch_id text,
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
              batch_id text,
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

            create table if not exists batch_runs (
              id text primary key,
              name text not null,
              source text not null,
              status text not null,
              flow_type text not null,
              flow text not null,
              window_count integer not null,
              options_json text not null default '{}',
              schedule_id text,
              last_error text,
              created_at text not null,
              updated_at text not null,
              started_at text,
              ended_at text
            );

            create table if not exists schedules (
              id text primary key,
              name text not null,
              enabled integer not null,
              flow_type text not null,
              flow text not null,
              browser_ids_json text not null default '[]',
              inputs_json text not null default '{}',
              per_window_inputs_json text not null default '{}',
              trigger_json text not null default '{}',
              run_options_json text not null default '{}',
              overlap_policy text not null default 'skip',
              missed_policy text not null default 'skip',
              last_run_at text,
              next_run_at text,
              created_at text not null,
              updated_at text not null
            );
            """
        )
        self._ensure_column("tasks", "batch_id", "text")
        self._ensure_column("task_runs", "batch_id", "text")
        self._ensure_column("batch_runs", "updated_at", "text")

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {
            str(row["name"])
            for row in self.conn.execute(f"pragma table_info({table})").fetchall()
        }
        if column not in columns:
            self.conn.execute(f"alter table {table} add column {column} {definition}")

    def import_tasks(
        self,
        tasks: list[Task],
        *,
        replace: bool = False,
        batch_id: str | None = None,
    ) -> dict[str, int]:
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
                    batch_id or task.batch_id,
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
                        set batch_id = ?, browser_id = ?, flow_type = ?, flow = ?, goal = ?, inputs_json = ?,
                            status = ?, retry_count = ?, last_error = ?, updated_at = ?,
                            started_at = ?, finished_at = ?
                        where id = ?
                        """,
                        (
                            batch_id or task.batch_id,
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
                          id, batch_id, browser_id, flow_type, flow, goal, inputs_json, status,
                          retry_count, last_error, created_at, updated_at, started_at, finished_at
                        )
                        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

    def list_tasks_for_batch(self, batch_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            select *
            from tasks
            where batch_id = ?
            order by created_at asc
            """,
            (batch_id,),
        ).fetchall()
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

    def list_task_runs_for_batch(self, batch_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            select *
            from task_runs
            where batch_id = ?
            order by started_at desc
            limit ?
            """,
            (batch_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_browser_runtime(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("select * from browser_runtime order by updated_at desc").fetchall()
        return [dict(row) for row in rows]

    def count_tasks(self, *, status: str | None = None, batch_id: str | None = None) -> int:
        sql = "select count(*) as count from tasks"
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if batch_id:
            clauses.append("batch_id = ?")
            params.append(batch_id)
        if clauses:
            sql += " where " + " and ".join(clauses)
        row = self.conn.execute(sql, params).fetchone()
        return int(row["count"])

    def count_running_tasks(self) -> int:
        return self.count_tasks(status="running")

    def claim_pending_tasks(
        self,
        *,
        limit: int,
        busy_browser_ids: set[str] | None = None,
        batch_id: str | None = None,
    ) -> list[Task]:
        if limit <= 0:
            return []
        busy_browser_ids = busy_browser_ids or set()
        now = utc_now_iso()
        claimed: list[Task] = []
        with self.conn:
            params: list[Any] = []
            where = "status = 'pending'"
            if batch_id:
                where += " and batch_id = ?"
                params.append(batch_id)
            params.append(max(limit * 4, limit))
            rows = self.conn.execute(
                f"""
                select * from tasks
                where {where}
                order by created_at asc
                limit ?
                """,
                params,
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
                  id, batch_id, task_id, browser_id, status, ws, pid, port, started_at,
                  finished_at, error, artifact_dir, trace_path
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task.batch_id,
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

    def create_batch_run(
        self,
        *,
        name: str,
        source: str,
        flow_type: str,
        flow: str,
        browser_ids: list[str],
        inputs: dict[str, Any],
        per_window_inputs: dict[str, dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        schedule_id: str | None = None,
    ) -> dict[str, Any]:
        if not browser_ids:
            raise ValueError("batch run must include at least one browser")
        batch_id = f"batch-{uuid.uuid4().hex[:12]}"
        now = utc_now_iso()
        options = dict(options or {})
        per_window_inputs = per_window_inputs or {}
        tasks = []
        for index, browser_id in enumerate(browser_ids, start=1):
            merged_inputs = dict(inputs)
            overrides = per_window_inputs.get(browser_id) or {}
            if not isinstance(overrides, dict):
                raise ValueError(f"per-window inputs for {browser_id} must be a mapping")
            merged_inputs.update(overrides)
            tasks.append(
                Task(
                    id=f"{batch_id}-{index:03d}",
                    batch_id=batch_id,
                    browser_id=browser_id,
                    flow_type=flow_type,
                    flow=flow,
                    inputs=merged_inputs,
                )
            )

        with self.conn:
            self.conn.execute(
                """
                insert into batch_runs (
                  id, name, source, status, flow_type, flow, window_count,
                  options_json, schedule_id, last_error, created_at, updated_at, started_at, ended_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    name,
                    source,
                    "pending",
                    flow_type,
                    flow,
                    len(browser_ids),
                    json.dumps(options, ensure_ascii=False),
                    schedule_id,
                    None,
                    now,
                    now,
                    None,
                    None,
                ),
            )
        imported = self.import_tasks(tasks, replace=False, batch_id=batch_id)
        return {"id": batch_id, "task_count": len(tasks), "imported": imported}

    def list_batch_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            select *
            from batch_runs
            order by created_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()
        return [self._batch_with_counts(dict(row)) for row in rows]

    def get_batch_run(self, batch_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("select * from batch_runs where id = ?", (batch_id,)).fetchone()
        if not row:
            return None
        return self._batch_with_counts(dict(row))

    def refresh_batch_status(self, batch_id: str) -> dict[str, Any] | None:
        batch = self.get_batch_run(batch_id)
        if not batch:
            return None
        status = _batch_status_from_counts(batch["counts"])
        now = utc_now_iso()
        started_at = batch.get("started_at")
        ended_at = batch.get("ended_at")
        if status == "running" and not started_at:
            started_at = now
        if status in {"success", "failed", "partial_failed", "cancelled"} and not ended_at:
            ended_at = now
        with self.conn:
            self.conn.execute(
                """
                update batch_runs
                set status = ?, started_at = ?, ended_at = ?, last_error = ?, updated_at = ?
                where id = ?
                """,
                (status, started_at, ended_at, batch.get("last_error"), now, batch_id),
            )
        refreshed = self.get_batch_run(batch_id)
        return refreshed

    def rerun_failed_tasks(self, batch_id: str) -> int:
        now = utc_now_iso()
        with self.conn:
            count = self.conn.execute(
                """
                update tasks
                set status = 'pending', retry_count = 0, last_error = null, updated_at = ?,
                    started_at = null, finished_at = null
                where batch_id = ? and status = 'failed'
                """,
                (now, batch_id),
            ).rowcount
            if count:
                self.conn.execute(
                    """
                    update batch_runs
                    set status = 'pending', ended_at = null, updated_at = ?
                    where id = ?
                    """,
                    (now, batch_id),
                )
        self.refresh_batch_status(batch_id)
        return int(count)

    def cancel_batch(self, batch_id: str) -> int:
        now = utc_now_iso()
        with self.conn:
            count = self.conn.execute(
                """
                update tasks
                set status = 'cancelled', updated_at = ?, finished_at = ?
                where batch_id = ? and status = 'pending'
                """,
                (now, now, batch_id),
            ).rowcount
            self.conn.execute(
                """
                update batch_runs
                set status = 'cancelled', ended_at = coalesce(ended_at, ?), updated_at = ?
                where id = ?
                """,
                (now, now, batch_id),
            )
        return int(count)

    def create_schedule(
        self,
        *,
        name: str,
        enabled: bool,
        flow_type: str,
        flow: str,
        browser_ids: list[str],
        inputs: dict[str, Any],
        per_window_inputs: dict[str, dict[str, Any]] | None,
        trigger: dict[str, Any],
        run_options: dict[str, Any],
        overlap_policy: str,
        missed_policy: str,
        next_run_at: str | None,
    ) -> dict[str, Any]:
        schedule_id = f"schedule-{uuid.uuid4().hex[:12]}"
        now = utc_now_iso()
        with self.conn:
            self.conn.execute(
                """
                insert into schedules (
                  id, name, enabled, flow_type, flow, browser_ids_json, inputs_json,
                  per_window_inputs_json, trigger_json, run_options_json, overlap_policy,
                  missed_policy, last_run_at, next_run_at, created_at, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    schedule_id,
                    name,
                    1 if enabled else 0,
                    flow_type,
                    flow,
                    json.dumps(browser_ids, ensure_ascii=False),
                    json.dumps(inputs, ensure_ascii=False),
                    json.dumps(per_window_inputs or {}, ensure_ascii=False),
                    json.dumps(trigger, ensure_ascii=False),
                    json.dumps(run_options, ensure_ascii=False),
                    overlap_policy,
                    missed_policy,
                    None,
                    next_run_at,
                    now,
                    now,
                ),
            )
        return {"id": schedule_id}

    def list_schedules(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("select * from schedules order by created_at desc").fetchall()
        return [_decode_schedule(dict(row)) for row in rows]

    def get_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("select * from schedules where id = ?", (schedule_id,)).fetchone()
        return _decode_schedule(dict(row)) if row else None

    def due_schedules(self, now_iso: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            select *
            from schedules
            where enabled = 1 and next_run_at is not null and next_run_at <= ?
            order by next_run_at asc
            """,
            (now_iso,),
        ).fetchall()
        return [_decode_schedule(dict(row)) for row in rows]

    def update_schedule_after_run(
        self,
        schedule_id: str,
        *,
        last_run_at: str,
        next_run_at: str | None,
        enabled: bool | None = None,
    ) -> None:
        now = utc_now_iso()
        enabled_sql = "enabled" if enabled is None else "?"
        params: list[Any] = []
        if enabled is not None:
            params.append(1 if enabled else 0)
        params.extend([last_run_at, next_run_at, now, schedule_id])
        with self.conn:
            self.conn.execute(
                f"""
                update schedules
                set enabled = {enabled_sql}, last_run_at = ?, next_run_at = ?, updated_at = ?
                where id = ?
                """,
                params,
            )

    def set_schedule_enabled(self, schedule_id: str, enabled: bool, next_run_at: str | None = None) -> None:
        now = utc_now_iso()
        with self.conn:
            self.conn.execute(
                """
                update schedules
                set enabled = ?, next_run_at = ?, updated_at = ?
                where id = ?
                """,
                (1 if enabled else 0, next_run_at, now, schedule_id),
            )

    def delete_schedule(self, schedule_id: str) -> int:
        with self.conn:
            return int(self.conn.execute("delete from schedules where id = ?", (schedule_id,)).rowcount)

    def _batch_with_counts(self, batch: dict[str, Any]) -> dict[str, Any]:
        rows = self.conn.execute(
            """
            select status, count(*) as count
            from tasks
            where batch_id = ?
            group by status
            """,
            (batch["id"],),
        ).fetchall()
        counts = {str(row["status"]): int(row["count"]) for row in rows}
        batch["counts"] = counts
        batch["status"] = _batch_status_from_counts(counts) if counts else batch.get("status", "pending")
        try:
            batch["options"] = json.loads(batch.get("options_json") or "{}")
        except Exception:
            batch["options"] = {}
        return batch

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
        batch_id=str(row["batch_id"]) if "batch_id" in row.keys() and row["batch_id"] else None,
        browser_id=str(row["browser_id"]),
        flow_type=str(row["flow_type"]),
        flow=str(row["flow"]),
        goal=str(row["goal"]) if row["goal"] else None,
        inputs=json.loads(row["inputs_json"] or "{}"),
    )


def _batch_status_from_counts(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    if total <= 0:
        return "pending"
    if counts.get("running", 0) > 0:
        return "running"
    if counts.get("pending", 0) > 0:
        return "pending"
    if counts.get("cancelled", 0) == total:
        return "cancelled"
    failed = counts.get("failed", 0)
    success = counts.get("success", 0)
    if failed and success:
        return "partial_failed"
    if failed:
        return "failed"
    if success == total:
        return "success"
    return "pending"


def _decode_schedule(row: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(row)
    decoded["enabled"] = bool(decoded.get("enabled"))
    for source, target, fallback in [
        ("browser_ids_json", "browser_ids", []),
        ("inputs_json", "inputs", {}),
        ("per_window_inputs_json", "per_window_inputs", {}),
        ("trigger_json", "trigger", {}),
        ("run_options_json", "run_options", {}),
    ]:
        try:
            decoded[target] = json.loads(decoded.get(source) or json.dumps(fallback))
        except Exception:
            decoded[target] = fallback
    return decoded
