from __future__ import annotations

import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable

import os

from api.answer import Tiku
from api.base import Account, Chaoxing
from api.exceptions import LoginError
from api.logger import logger

from main import filter_courses, process_job
from api.config import GlobalConst as gc

from .ai_config import get_fixed_tiku_config
from .module_recorder import ModuleRecorder

from threading import Condition


class TaskCancelled(BaseException):
    pass


@dataclass
class TaskOptions:
    username: str
    password: str
    course_ids: list[str]
    speed: float = 1.0
    notopen_action: str = "continue"
    jobs: int = 4


class TaskControl:
    def __init__(self) -> None:
        self.paused = False
        self.cancelled = False
        self.condition = Condition()


class TaskStateStore:
    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._controls: dict[str, TaskControl] = {}
        self._lock = Lock()

    def create(self, task_id: str, payload: dict[str, Any]) -> None:
        with self._lock:
            self._tasks[task_id] = payload
            self._controls[task_id] = TaskControl()

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._tasks.get(task_id)

    def update(self, task_id: str, updates: dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            task.update(updates)

    def update_playback(self, task_id: str, key: str, payload: dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            playbacks = task.setdefault("current_playbacks", {})
            playbacks[key] = payload
            task["current_playback"] = payload

    def remove_playback(self, task_id: str, key: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            playbacks = task.setdefault("current_playbacks", {})
            playbacks.pop(key, None)

    def append_log(self, task_id: str, log_line: str) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            logs = task.setdefault("logs", [])
            logs.append(log_line)
            if len(logs) > 200:
                del logs[:-200]

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._tasks.values())

    def control(self, task_id: str) -> TaskControl | None:
        with self._lock:
            return self._controls.get(task_id)

    def set_paused(self, task_id: str, paused: bool) -> bool:
        control = self.control(task_id)
        if not control:
            return False
        with control.condition:
            control.paused = paused
            if not paused:
                control.condition.notify_all()
        return True

    def cancel(self, task_id: str) -> bool:
        control = self.control(task_id)
        if not control:
            return False
        with control.condition:
            control.cancelled = True
            control.paused = False
            control.condition.notify_all()
        return True

    def wait_if_paused(self, task_id: str) -> None:
        control = self.control(task_id)
        if not control:
            return
        with control.condition:
            while control.paused and not control.cancelled:
                control.condition.wait(timeout=0.5)
            if control.cancelled:
                raise TaskCancelled()


class ChaoxingTaskRunner:
    def __init__(
        self,
        store: TaskStateStore,
        recorder: ModuleRecorder,
        on_state_update: Callable[[str, dict[str, Any]], None] | None = None,
        on_log: Callable[[str, str], None] | None = None,
    ) -> None:
        self.store = store
        self.recorder = recorder
        self.on_state_update = on_state_update
        self.on_log = on_log

    def _log(self, task_id: str, message: str) -> None:
        self.store.append_log(task_id, message)
        if self.on_log:
            self.on_log(task_id, message)
        logger.info("[task:{}] {}", task_id, message)

    def _update(self, task_id: str, updates: dict[str, Any]) -> None:
        self.store.update(task_id, updates)
        if self.on_state_update:
            persisted = {
                "status",
                "done_courses",
                "total_courses",
                "done_modules",
                "total_modules",
                "error",
                "traceback",
            }
            db_updates = {key: value for key, value in updates.items() if key in persisted}
            if db_updates:
                self.on_state_update(task_id, db_updates)

    def _playback_key(self, payload: dict[str, Any]) -> str:
        return str(payload.get("jobid") or payload.get("objectid") or payload.get("task_name") or "current")

    def _update_playback(self, task_id: str, payload: dict[str, Any]) -> None:
        key = self._playback_key(payload)
        if payload.get("ephemeral") and payload.get("status") in {"completed", "failed", "cancelled"}:
            self.store.remove_playback(task_id, key)
            return
        self.store.update_playback(task_id, key, payload)

    def pause_task(self, task_id: str) -> bool:
        if not self.store.set_paused(task_id, True):
            return False
        self._update(task_id, {"status": "paused"})
        self._log(task_id, "task paused")
        return True

    def resume_task(self, task_id: str) -> bool:
        if not self.store.set_paused(task_id, False):
            return False
        self._update(task_id, {"status": "running"})
        self._log(task_id, "task resumed")
        return True

    def cancel_task(self, task_id: str) -> bool:
        if not self.store.cancel(task_id):
            return False
        self._update(task_id, {"status": "cancelling"})
        self._log(task_id, "task cancelling")
        return True

    def wait_if_paused(self, task_id: str) -> None:
        self.store.wait_if_paused(task_id)

    def _job_payload(
        self,
        status: str,
        course: dict[str, Any],
        point: dict[str, Any],
        job: dict[str, Any],
        play_time: int = 0,
        duration: int = 0,
    ) -> dict[str, Any]:
        percent = int(min(100, max(0, (float(play_time) / duration) * 100))) if duration else (100 if status == "completed" else 0)
        return {
            "status": status,
            "type": job.get("type", "task"),
            "task_name": job.get("name") or job.get("jobid") or point.get("title") or "task",
            "jobid": job.get("jobid"),
            "objectid": job.get("objectid"),
            "course_id": course.get("courseId"),
            "course_title": course.get("title", ""),
            "module_id": point.get("id"),
            "module_title": point.get("title", ""),
            "play_time": play_time,
            "duration": duration,
            "percent": percent,
        }

    def _new_chaoxing(self, opts: TaskOptions, task_id: str | None = None) -> Chaoxing:
        if task_id:
            runtime_dir = os.getenv("RUNTIME_DIR", "runtime")
            os.makedirs(runtime_dir, exist_ok=True)
            gc.COOKIES_PATH = os.path.join(runtime_dir, f"cookies_{task_id}.txt")
        account = Account(opts.username.strip(), opts.password.strip())
        tiku_config = get_fixed_tiku_config()
        tiku = Tiku()
        tiku.config_set(tiku_config)
        tiku = tiku.get_tiku_from_config()
        tiku.init_tiku()

        def progress_callback(payload: dict[str, Any]) -> None:
            if not task_id:
                return
            self.wait_if_paused(task_id)
            self._update_playback(task_id, payload)

        return Chaoxing(
            account=account,
            tiku=tiku,
            query_delay=float(tiku_config.get("delay", 0) or 0),
            progress_callback=progress_callback if task_id else None,
        )

    def fetch_courses(self, username: str, password: str) -> list[dict[str, Any]]:
        chaoxing = self._new_chaoxing(
            TaskOptions(
                username=username,
                password=password,
                course_ids=[],
            )
        )
        login_state = chaoxing.login(login_with_cookies=False)
        if not login_state.get("status", False):
            raise LoginError(login_state.get("msg", "login failed"))
        courses = chaoxing.get_course_list()
        return [
            {
                "courseId": c.get("courseId"),
                "title": c.get("title"),
                "clazzId": c.get("clazzId"),
                "cpi": c.get("cpi"),
            }
            for c in courses
        ]

    def run_task(self, task_id: str, opts: TaskOptions) -> None:
        try:
            self._update(task_id, {"status": "running"})
            self._log(task_id, "task started")

            chaoxing = self._new_chaoxing(opts, task_id=task_id)
            login_state = chaoxing.login(login_with_cookies=False)
            if not login_state.get("status", False):
                raise LoginError(login_state.get("msg", "login failed"))
            self._log(task_id, "login successful")

            all_courses = chaoxing.get_course_list()
            selected = filter_courses(all_courses, opts.course_ids)
            if opts.course_ids and not selected:
                raise ValueError("selected courses not found")
            total_courses = len(selected)
            self._update(task_id, {"total_courses": total_courses, "done_courses": 0})
            self._log(task_id, f"selected courses: {total_courses}")

            done_courses = 0
            task_failed = False
            for course in selected:
                self.wait_if_paused(task_id)
                course_title = str(course.get("title", ""))
                self._log(task_id, f"processing course: {course_title}")
                points = chaoxing.get_course_point(course["courseId"], course["clazzId"], course["cpi"]).get("points", [])
                previous_total_modules = int((self.store.get(task_id) or {}).get("total_modules", 0) or 0)
                self._update(task_id, {"total_modules": previous_total_modules + len(points)})

                done_modules = int((self.store.get(task_id) or {}).get("done_modules", 0) or 0)
                max_workers = max(1, min(int(opts.jobs or 1), 8))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [executor.submit(self._process_point, task_id, chaoxing, course, point, opts) for point in points]
                    for future in as_completed(futures):
                        self.wait_if_paused(task_id)
                        result = future.result()
                        done_modules += 1
                        self._update(task_id, {"done_modules": done_modules})
                        if result["status"] == "failed":
                            task_failed = True
                        self._log(task_id, f"module done: {result['module_title']} ({result['status']})")

                done_courses += 1
                self._update(task_id, {"done_courses": done_courses})

            final_status = "failed" if task_failed else "completed"
            self._update(task_id, {"status": final_status})
            self._log(task_id, f"task {final_status}")
        except TaskCancelled:
            self._update(task_id, {"status": "cancelled"})
            self._log(task_id, "task cancelled")
        except Exception as exc:
            self._update(
                task_id,
                {
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                },
            )
            self._log(task_id, f"task failed: {type(exc).__name__}: {exc}")

    def _process_point(
        self,
        task_id: str,
        chaoxing: Chaoxing,
        course: dict[str, Any],
        point: dict[str, Any],
        opts: TaskOptions,
    ) -> dict[str, Any]:
        course_title = str(course.get("title", ""))
        module_title = str(point.get("title", ""))
        module_id = str(point.get("id", ""))
        self.wait_if_paused(task_id)

        if point.get("has_finished"):
            payload = {
                "course_id": course["courseId"],
                "course_title": course_title,
                "module_id": module_id,
                "module_title": module_title,
                "status": "already_finished",
                "finished_jobs": 0,
                "total_jobs": 0,
                "message": "module already completed",
            }
            self.recorder.write(task_id, payload)
            return payload

        jobs, job_info = chaoxing.get_job_list(course, point)
        self.wait_if_paused(task_id)
        if job_info.get("notOpen", False):
            status = "skipped_not_open" if opts.notopen_action != "retry" else "waiting_not_open"
            payload = {
                "course_id": course["courseId"],
                "course_title": course_title,
                "module_id": module_id,
                "module_title": module_title,
                "status": status,
                "finished_jobs": 0,
                "total_jobs": len(jobs),
                "message": "module is not open",
            }
            self.recorder.write(task_id, payload)
            return payload

        finished_jobs = 0
        module_status = "success"
        module_message = "module finished"
        if jobs:
            with ThreadPoolExecutor(max_workers=max(1, min(5, len(jobs)))) as executor:
                futures = [executor.submit(self._process_job, task_id, chaoxing, course, point, job, job_info, opts.speed) for job in jobs]
                for future in as_completed(futures):
                    self.wait_if_paused(task_id)
                    result = future.result()
                    finished_jobs += 1
                    if result.is_failure():
                        module_status = "failed"
                        module_message = "at least one job failed"

        payload = {
            "course_id": course["courseId"],
            "course_title": course_title,
            "module_id": module_id,
            "module_title": module_title,
            "status": module_status,
            "finished_jobs": finished_jobs,
            "total_jobs": len(jobs),
            "message": module_message,
        }
        self.recorder.write(task_id, payload)
        return payload

    def _process_job(
        self,
        task_id: str,
        chaoxing: Chaoxing,
        course: dict[str, Any],
        point: dict[str, Any],
        job: dict[str, Any],
        job_info: dict[str, Any],
        speed: float,
    ):
        self.wait_if_paused(task_id)
        self._update_playback(task_id, self._job_payload("running", course, point, job))
        result = process_job(chaoxing, course, job, job_info, speed)
        self.wait_if_paused(task_id)
        if job.get("type") != "video":
            self._update_playback(task_id, self._job_payload("completed" if not result.is_failure() else "failed", course, point, job, 1, 1))
        return result
