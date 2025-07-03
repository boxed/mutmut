from __future__ import annotations

from typing import Generic, Union, Any, Callable, Iterable, TypeVar
from typing_extensions import ParamSpec
from dataclasses import dataclass

import multiprocessing.connection
from multiprocessing import Queue, Process
import queue
import os


TaskArgs = ParamSpec('TaskArgs')
TaskResult = TypeVar('TaskResult')

@dataclass
class Task:
    id: str
    args: tuple[Any, ...]
    # this timeout is real time, not process cpu time
    timeout_seconds: int

@dataclass
class TaskError:
    id: str
    error: Exception

@dataclass
class FinishedTask(Generic[TaskResult]):
    id: str
    result: Union[TaskResult, None]
    error: Union[Exception, None]

class JobTimeoutException(Exception):
    pass

class CustomProcessPool(Generic[TaskArgs, TaskResult]):
    def __init__(self, tasks: list[Task], job: Callable[TaskArgs, TaskResult], max_workers: int):
        self._tasks = tasks
        self._job = job
        self._remaining_tasks_queue: Queue[Task] = Queue()
        self._remaining_tasks_count = len(tasks)
        self._results: Queue[FinishedTask[TaskResult]] = Queue()
        self._max_workers = max_workers
        self._workers: set[Process] = set()
        self._killed_workers = 0
        self._shutdown = False

    def run(self) -> Iterable[FinishedTask]:
        for task in self._tasks:
            self._remaining_tasks_queue.put(task)

        self._start_missing_workers()

        while not self.done() and not self._shutdown:
            self._remove_stopped_workers()
            self._start_missing_workers()

            yield from self._get_new_results(timeout=1)

        self.shutdown()

    def shutdown(self):
        # TODO: is this a good way to shutdown processes?
        for p in self._workers:
            if p.is_alive():
                p.kill()
        for p in self._workers:
            p.join()
        self._remaining_tasks_queue.close()
        self._results.close()
        self._shutdown = True

    def _start_missing_workers(self):
        self._workers = {p for p in self._workers if p.is_alive()}

        desired_workers = min(self._max_workers, self._remaining_tasks_count)
        missing_workers = desired_workers - len(self._workers)

        for _ in range(missing_workers):
            self._start_worker()

    def _remove_stopped_workers(self):
        """Start a new worker for all stopped workers. We kill workers for timeouts."""
        killed_workers = {p for p in self._workers if not p.is_alive()}
        self._workers -= killed_workers

        for worker in killed_workers:
            print(f'Worker {worker.pid} stopped with exitcode {worker.exitcode}')

    def _get_new_results(self, timeout: int) -> Iterable[FinishedTask]:
        try:
            result = self._results.get(timeout=timeout)
            self._remaining_tasks_count -= 1
            yield result
        except queue.Empty:
            pass

    def _start_worker(self):
        p = Process(target=CustomProcessPool._pool_job_executor, args=(self._job, self._remaining_tasks_queue, self._results))
        p.start()
        self._workers.add(p)

    def done(self) -> bool:
        return self._remaining_tasks_count == 0

    @staticmethod
    def _pool_job_executor(job: Callable[..., TaskResult], task_queue: Queue[Task], results: Queue[FinishedTask[TaskResult]]):
        while True:
            try:
                task = task_queue.get(timeout=1)
                # f = open(f'logs/log-{task.id}.txt', 'w')
                # pid = os.getpid()
            except queue.Empty:
                os._exit(0)

            try:
                result = job(task)
                finished_task: FinishedTask[TaskResult] = FinishedTask(id=task.id, result=result, error=None)
            except Exception as e:
                finished_task = FinishedTask(id=task.id, result=None, error=e)
            finally:
                # f.write(f'Finished job: {finished_task}\n')
                # f.flush()
                results.put(finished_task)
                # f.write(f'Added job to queue\n')
                # f.write(f'Finished qsize: {results.qsize()}\n')
                # f.flush()



