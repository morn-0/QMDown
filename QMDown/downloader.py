import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from QMDown import console


@dataclass()
class DownloadTask:
    """
    下载任务数据类

    Args:
        url: 文件 URL。
        filename: 保存的文件名。
    """

    url: str
    filename: str
    filepath: Path


class AsyncDownloader:
    """异步文件下载器。

    支持动态任务管理、下载过程中添加 Hook 回调、并发控制。

    Args:
        save_dir: 文件保存目录。
        max_concurrent: 最大并发下载任务数。
        retries: 每个任务的最大重试次数。
        timeout: 每个请求的超时时间（秒）。
        on_start: 下载开始时的回调函数。
        on_complete: 下载完成时的回调函数。
        on_error: 下载失败时的回调函数。
    """

    def __init__(
        self,
        save_dir: str = "downloads",
        max_concurrent: int = 5,
        retries: int = 3,
        timeout: int = 10,
        on_start: Optional[Callable[[DownloadTask], None]] = None,
        on_complete: Optional[Callable[[DownloadTask], None]] = None,
        on_error: Optional[Callable[[DownloadTask, Exception], None]] = None,
    ):
        self.save_dir = Path(save_dir)
        self.max_concurrent = max_concurrent
        self.retries = retries
        self.timeout = timeout
        self.task_queue = asyncio.Queue()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.progress = Progress(
            TextColumn(
                "[bold blue]{task.fields[filename]}[/] {task.description}",
                justify="right",
            ),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )

        # Hook 回调函数
        self.on_start = on_start
        self.on_complete = on_complete
        self.on_error = on_error

    async def add_task(self, url: str, filename: str):
        """向队列中添加一个下载任务。

        Args:
            url: 文件 URL。
            filename: 保存的文件名。
        """
        task = DownloadTask(url, filename, self.save_dir / filename)
        await self.task_queue.put(task)
        logging.info(f"Task added: {url} -> {task.filename}")

    async def worker(self, client: httpx.AsyncClient):
        """队列工作者，从任务队列中提取并执行下载任务。

        Args:
            client: 用于发送请求的 HTTP 客户端。
        """
        while True:
            task = await self.task_queue.get()
            if task is None:  # 停止信号
                break
            await self.download(client, task)
            self.task_queue.task_done()

    async def download(self, client: httpx.AsyncClient, task: DownloadTask):
        """下载单个文件任务。

        Args:
            client: 用于发送请求的 HTTP 客户端。
            task: 下载任务对象。
        """
        task_id = self.progress.add_task(
            description="",
            filename=task.filename,
            start=False,
        )

        if task.filepath.exists():
            logging.info(f"Skipped: {task.url} -> {task.filename}")
            self.progress.update(task_id, description="已存在")
            return

        for attempt in range(1, self.retries + 1):
            async with self.semaphore:
                try:
                    self.progress.start_task(task_id)

                    self.progress.update(
                        task_id,
                        description="",
                    )

                    # 获取文件大小
                    response = await client.head(task.url, timeout=self.timeout)
                    if response.status_code != 200:
                        raise httpx.RequestError(f"HTTP {response.status_code}")

                    total = int(response.headers.get("Content-Length", 0))

                    self.progress.update(task_id, total=total)

                    # Hook: 开始下载
                    if self.on_start:
                        self.on_start(task)

                    # 确保保存目录存在
                    self.save_dir.mkdir(parents=True, exist_ok=True)

                    async with client.stream(
                        "GET", task.url, timeout=self.timeout
                    ) as response:
                        if response.status_code != 200:
                            raise httpx.RequestError(f"HTTP {response.status_code}")

                        with open(task.filepath, "wb") as f:
                            async for chunk in response.aiter_bytes(
                                chunk_size=1024 * 5
                            ):
                                f.write(chunk)
                                self.progress.update(task_id, advance=len(chunk))

                    logging.debug(f"Downloaded: {task.url} -> {task.filename}")

                    # Hook: 下载完成
                    if self.on_complete:
                        self.on_complete(task)
                    return
                except Exception as e:
                    self.progress.update(
                        task_id,
                        description=f"[yellow]Retry {attempt}/{self.retries}...",
                    )
                    logging.warning(f"Failed attempt {attempt} for {task.url}: {e}")
                    if attempt == self.retries:
                        self.progress.update(task_id, description="[red]Failed")
                        logging.error(f"Failed: {task.url} -> {task.filename}: {e}")

                        # Hook: 下载失败
                        if self.on_error:
                            self.on_error(task, e)

    async def run(self, headers=None):
        """启动下载器，处理队列中的任务。

        Args:
            headers: 自定义请求头（如 User-Agent）。
        """
        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            with self.progress:
                workers = [
                    asyncio.create_task(self.worker(client))
                    for _ in range(self.max_concurrent)
                ]

                # 持续运行直到手动停止或任务完成
                await self.task_queue.join()

                # 停止所有工作者
                for _ in range(self.max_concurrent):
                    await self.task_queue.put(None)
                await asyncio.gather(*workers)

