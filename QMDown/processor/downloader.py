import asyncio
import logging
from pathlib import Path
from typing import ClassVar

import anyio
import httpx
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TaskID,
    TextColumn,
    TransferSpeedColumn,
)
from rich.table import Column
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from QMDown import console


class AsyncDownloader:
    """异步文件下载器。

    支持动态任务管理、下载过程中添加 Hook 回调、并发控制。
    """

    DEFAULT_COLUMNS: ClassVar = {
        "description": TextColumn(
            "{task.description}[bold blue]{task.fields[filename]}", table_column=Column(ratio=2, min_width=10)
        ),
        "bar": BarColumn(bar_width=None, table_column=Column(ratio=3)),
        "percentage": TextColumn("[progress.percentage]{task.percentage:>4.1f}%"),
        "•": "•",
        "filesize": DownloadColumn(),
        "speed": TransferSpeedColumn(),
    }

    def __init__(
        self,
        save_dir: str | Path = ".",
        num_workers: int = 3,
        no_progress: bool = False,
        timeout: int = 10,
    ):
        """
        Args:
            save_dir: 文件保存目录.
            max_concurrent: 最大并发下载任务数.
            timeout: 每个请求的超时时间(秒).
            no_progress: 是否显示进度.
        """
        self.save_dir = Path(save_dir)
        self.max_concurrent = num_workers
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(num_workers)
        self.download_tasks = []
        self.progress = Progress(
            *self.DEFAULT_COLUMNS.values(),
            transient=False,
            expand=True,
            console=console,
        )
        self.overall_progress = Progress(
            TextColumn("[green]{task.description} [blue]{task.completed}[/]/[blue]{task.total}"),
            BarColumn(bar_width=None),
            expand=True,
        )
        self.overall_task_id = self.overall_progress.add_task("下载中", visible=False)
        self.no_progress = no_progress

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def _fetch_file_size(self, client: httpx.AsyncClient, url: str) -> int:
        try:
            response = await client.head(url)
            response.raise_for_status()
            return int(response.headers.get("Content-Length", 0))
        except httpx.RequestError:
            raise
        except Exception:
            return 0

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(httpx.RequestError),
    )
    async def download_file(self, task_id: TaskID, url: str, full_path: Path):
        async with self.semaphore:
            self.save_dir.mkdir(parents=True, exist_ok=True)

            async with httpx.AsyncClient() as client:
                content_length = await self._fetch_file_size(client, url)
                if content_length == 0:
                    logging.warning(f"[yellow]获取 [blue]{full_path.name} [yellow]大小失败")

                async with client.stream("GET", url, timeout=self.timeout) as response:
                    response.raise_for_status()
                    async with await anyio.open_file(full_path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)
                            self.progress.update(
                                task_id,
                                advance=len(chunk),
                                total=content_length,
                                visible=True,
                            )
                    self.progress.update(task_id, visible=False)
                    self.overall_progress.update(self.overall_task_id, advance=1)
                    logging.info(f"[green][ 完成 ] [blue]{full_path.name}")

    async def add_task(self, url: str, file_name: str, file_suffix: str):
        """添加下载任务.

        Args:
            url: 文件 URL.
            file_name: 文件名称.
            file_suffix: 文件后缀.
        """
        async with self.semaphore:
            # 文件路径
            file_path = f"{file_name}{file_suffix}"
            # 文件全路径
            full_path = self.save_dir / file_path

            if full_path.exists():
                logging.info(f"[green][ 跳过 ] [blue]{file_name}")
            else:
                task_id = self.progress.add_task(
                    description=f"[  {file_suffix.replace('.', '')}  ]:",
                    filename=file_name,
                    visible=False,
                )
                download_task = asyncio.create_task(self.download_file(task_id, url, full_path))
                self.download_tasks.append(download_task)

    async def execute_tasks(self):
        """执行所有下载任务"""
        logging.info(f"开始下载歌曲 总共:{len(self.download_tasks)}")
        if self.no_progress:
            with console.status("下载歌曲中..."):
                await asyncio.gather(*self.download_tasks)
            logging.info("下载完成")
        else:
            self.overall_progress.update(self.overall_task_id, total=len(self.download_tasks), visible=True)
            with Live(Group(self.overall_progress, Panel(self.progress)), console=console):
                await asyncio.gather(*self.download_tasks)
            self.overall_progress.update(self.overall_task_id, description="下载完成")
        self.download_tasks.clear()
