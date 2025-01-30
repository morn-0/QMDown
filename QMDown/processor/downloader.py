import asyncio
import logging
from pathlib import Path

import anyio
import httpx
from pydantic import BaseModel
from rich.progress import TaskID
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from QMDown import console
from QMDown.utils.progress import DownloadProgress
from QMDown.utils.utils import safe_filename


class DownloadTask(BaseModel):
    """下载任务"""

    id: TaskID
    url: str
    file_name: str
    file_suffix: str
    full_path: Path


class AsyncDownloader:
    """异步文件下载器"""

    def __init__(
        self,
        save_dir: str | Path = ".",
        num_workers: int = 3,
        no_progress: bool = False,
        retries: int = 3,
        timeout: int = 15,
        overwrite: bool = False,
    ):
        """
        Args:
            save_dir: 文件保存目录.
            max_concurrent: 最大并发下载任务数.
            timeout: 每个请求的超时时间(秒).
            retries: 重试次数.
            no_progress: 是否显示进度.
            overwrite: 是否强制覆盖已下载文件.
        """
        self.save_dir = Path(save_dir)
        self.max_concurrent = num_workers
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(num_workers)
        self.download_tasks: list[DownloadTask] = []
        self.progress = DownloadProgress()
        self.no_progress = no_progress
        self.retries = retries
        self.overwrite = overwrite

    async def _fetch_file_size(self, client: httpx.AsyncClient, url: str) -> int:
        try:
            response = await client.head(url)
            response.raise_for_status()
            return int(response.headers.get("Content-Length", 0))
        except httpx.RequestError:
            raise
        except Exception:
            return 0

    async def download_file(self, client: httpx.AsyncClient, task_id: TaskID, url: str, full_path: Path):
        async with self.semaphore:
            await self.progress.update(task_id, visible=True)
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.retries),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception_type((httpx.RequestError, httpx.ReadTimeout, httpx.ConnectTimeout)),
            ):
                with attempt:
                    self.save_dir.mkdir(parents=True, exist_ok=True)

                    content_length = await self._fetch_file_size(client, url)
                    if content_length == 0:
                        logging.warning(f"[blue][下载][yellow]获取文件大小失败: [cyan]{full_path.name}")

                    await self.progress.update(
                        task_id,
                        description=f"[blue]\[{full_path.suffix.replace('.', '')}]",
                        completed=0,
                        total=content_length,
                    )

                    async with client.stream("GET", url, timeout=self.timeout) as response:
                        response.raise_for_status()
                        async with await anyio.open_file(full_path, "wb") as f:
                            chunk_size = 64 * 1024
                            async for chunk in response.aiter_bytes(chunk_size):
                                chunk_size = min(chunk_size * 2, 1024 * 1024)
                                await f.write(chunk)
                                await self.progress.update(
                                    task_id,
                                    advance=len(chunk),
                                    visible=True,
                                )
                        await self.progress.update(task_id, visible=False)
                        logging.info(f"[blue][下载][/] [green]完成[/] [cyan]{full_path.name}")

    async def add_task(self, url: str, file_name: str, file_suffix: str) -> Path | None:
        """添加下载任务.

        Args:
            url: 文件 URL.
            file_name: 文件名称.
            file_suffix: 文件后缀.

        Returns:
            文件存储位置
        """
        async with self.semaphore:
            # 文件路径
            file_path = safe_filename(f"{file_name}{file_suffix}")
            # 文件全路径
            full_path = self.save_dir / file_path

            if not self.overwrite and full_path.exists():
                logging.info(f"[blue][下载][/] [red]跳过[/] [cyan]{file_path}")
            else:
                # 检查是否有相同路径的任务正在进行
                if _ := next((task for task in self.download_tasks if task.full_path == full_path), None):
                    logging.info(f"[blue][下载][/] [red]发现相同路径任务:[/] [cyan]{file_path}")
                    return None

                task_id = await self.progress.add_task(
                    description="[blue][等待]:[/]",
                    filename=file_name,
                    visible=False,
                )

                self.download_tasks.append(
                    DownloadTask(
                        id=task_id,
                        url=url,
                        file_name=file_name,
                        file_suffix=file_suffix,
                        full_path=full_path,
                    )
                )
            return full_path

    async def start(self):
        async with httpx.AsyncClient() as client:
            await asyncio.gather(
                *[self.download_file(client, task.id, task.url, task.full_path) for task in self.download_tasks]
            )

    async def execute_tasks(self):
        """执行所有下载任务"""
        if len(self.download_tasks) == 0:
            return

        if self.no_progress:
            with console.status("下载中..."):
                await self.start()
        else:
            with self.progress:
                await self.start()
        self.download_tasks.clear()
