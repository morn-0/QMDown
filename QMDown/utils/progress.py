from asyncio import Lock
from typing import ClassVar

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, DownloadColumn, Progress, SpinnerColumn, TaskID, TextColumn, TransferSpeedColumn
from rich.table import Column

from QMDown import console
from QMDown.utils.singleton import Singleton


class ProgressManager(metaclass=Singleton):
    """
    进度条管理
    """

    DEFAULT_COLUMNS: ClassVar = {
        "description": TextColumn(
            "{task.description}[bold blue]{task.fields[filename]}",
            table_column=Column(ratio=2),
        ),
        "bar": BarColumn(bar_width=None, table_column=Column(ratio=3)),
        "percentage": TextColumn("[progress.percentage]{task.percentage:>4.1f}%"),
        "•": "•",
        "filesize": DownloadColumn(),
        "speed": TransferSpeedColumn(),
    }

    def __init__(self) -> None:
        self._download_progress = Progress(
            *self.DEFAULT_COLUMNS.values(),
            expand=True,
            console=console,
        )
        self._overall_progress = Progress(
            SpinnerColumn("moon"),
            TextColumn("[green]{task.description} [blue]{task.completed}[/]/[blue]{task.total}"),
            BarColumn(bar_width=None),
            expand=True,
            console=console,
        )
        self._overall_task_id = self._overall_progress.add_task(
            "下载中",
            visible=False,
        )
        self._live = Live(
            Group(
                self._overall_progress,
                Panel(self._download_progress),
            ),
            console=console,
            transient=True,
        )

        self._progress_lock = Lock()
        self._active_tasks = set()

    @property
    def tasks(self):
        return self._download_progress.tasks

    def start(self):
        self._live.start()

    def start_task(self, task_id):
        self._download_progress.start_task(task_id)

    def stop(self):
        self._live.stop()

    def stop_task(self, task_id):
        self._download_progress.stop_task(task_id)

    async def add_task(
        self,
        description: str,
        start: bool = True,
        total: float | None = 100.0,
        completed: int = 0,
        visible: bool = True,
        filename: str = "",
    ) -> TaskID:
        async with self._progress_lock:
            task_id = self._download_progress.add_task(
                description=description,
                start=start,
                total=total,
                completed=completed,
                visible=visible,
                filename=filename,
            )
            self._active_tasks.add(task_id)
            self._overall_progress.update(
                self._overall_task_id,
                total=len(self.tasks),
                visible=True,
            )
        return task_id

    async def update(
        self,
        task_id: TaskID,
        total: float | None = None,
        completed: float | None = None,
        advance: float | None = None,
        description: str | None = None,
        visible: bool = True,
        refresh: bool = False,
        filename: str | None = None,
    ) -> None:
        async with self._progress_lock:
            update_params = {
                "total": total,
                "completed": completed,
                "visible": visible,
                "refresh": refresh,
                "advance": advance,
                "description": description,
            }
            if filename:
                update_params["filename"] = filename

            self._download_progress.update(task_id, **update_params)

            if self._download_progress.tasks[task_id].finished and task_id in self._active_tasks:
                self._active_tasks.remove(task_id)
                self._overall_progress.advance(self._overall_task_id)

                if len(self._active_tasks) == 0:
                    self._overall_progress.update(self._overall_task_id, description="[green]下载完成")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
