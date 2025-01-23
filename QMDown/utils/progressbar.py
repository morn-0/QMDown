from asyncio import Lock
from typing import ClassVar

from rich.progress import (
    BarColumn,
    DownloadColumn,
    ProgressColumn,
    Task,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.progress import (
    Progress as RichProgress,
)
from rich.spinner import Spinner

from QMDown import console


class CustomSpinnerColumn(ProgressColumn):
    """
    自定义的指示器列 (Custom spinner columns)
    查看示例 (show expamle): python -m rich.spinner
    """

    DEFAULT_SPINNERS: ClassVar = {
        "waiting": "dots8",
        "starting": "arrow",
        "downloading": "moon",
        "paused": "smiley",
        "error": "star2",
        "completed": "hearts",
    }

    def __init__(
        self,
        spinner_styles: dict[str, str] | None = None,
        style: str = "progress.spinner",
        speed: float = 1.0,
    ):
        spinner_styles = spinner_styles or {}
        spinner_names = {state: spinner_styles.get(state, default) for state, default in self.DEFAULT_SPINNERS.items()}
        self.spinners = {
            state: Spinner(spinner_name, style=style, speed=speed) for state, spinner_name in spinner_names.items()
        }
        super().__init__()

    def render(self, task: Task):
        t = task.get_time()
        state = task.fields.get("state", "starting")
        spinner = self.spinners.get(state, self.spinners["starting"])
        return spinner.render(t)


class ProgressManager:
    """
    进度管理器 (Progress Manager)
    """

    DEFAULT_COLUMNS: ClassVar = {
        "spinner": CustomSpinnerColumn(),
        "description": TextColumn("{task.description}[bold blue]{task.fields[filename]}"),
        "bar": BarColumn(bar_width=None),
        "percentage": TextColumn("[progress.percentage]{task.percentage:>4.1f}%"),
        "•": "•",
        "filesize": DownloadColumn(),
        "speed": TransferSpeedColumn(),
        "ETA": "[bold blue]ETA",
        "remaining": TimeRemainingColumn(),
    }

    def __init__(
        self,
        spinner_column: CustomSpinnerColumn | None = None,
        custom_columns: dict[str, ProgressColumn] | None = None,
        bar_width: int | None = None,
        expand: bool = False,
    ):
        chosen_columns_dict = custom_columns or self.DEFAULT_COLUMNS.copy()
        if spinner_column:
            chosen_columns_dict = {"spinner": spinner_column, **chosen_columns_dict}
        if "bar" in chosen_columns_dict and isinstance(chosen_columns_dict["bar"], BarColumn):
            bar_column = chosen_columns_dict["bar"]
            bar_column.bar_width = bar_width or 40
        self._progress = RichProgress(*chosen_columns_dict.values(), transient=False, expand=expand, console=console)
        self._progress_lock = Lock()
        self._active_tasks = set()

    def start(self):
        self._progress.start()

    def start_task(self, task_id):
        self._progress.start_task(task_id)

    def stop(self):
        self._progress.stop()

    def stop_task(self, task_id):
        self._progress.stop_task(task_id)

    @property
    def tasks(self):
        return self._progress.tasks

    async def add_task(
        self,
        description: str,
        start: bool = True,
        total: float | None = None,
        completed: int = 0,
        visible: bool = True,
        state: str = "starting",
        filename: str = "",
    ) -> TaskID:
        async with self._progress_lock:
            task_id = self._progress.add_task(
                description=description,
                start=start,
                total=total,
                completed=completed,
                visible=visible,
                filename=filename,
                state=state,
            )
            self._active_tasks.add(task_id)
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
        state: str | None = None,
    ) -> None:
        async with self._progress_lock:
            update_params = {
                key: value
                for key, value in [
                    ("advance", advance),
                    ("description", description),
                    ("state", state),
                    ("filename", filename),
                ]
                if value
            }

            self._progress.update(
                task_id,
                total=total,
                completed=completed,
                visible=visible,
                refresh=refresh,
                **update_params,
            )

            if self._progress.tasks[task_id].finished and task_id in self._active_tasks:
                self._active_tasks.remove(task_id)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


progressManager = ProgressManager()
