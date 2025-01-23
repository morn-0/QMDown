import asyncio
import logging
from pathlib import Path

import anyio
import httpx
from rich.progress import TaskID

from QMDown.utils.progressbar import progressManager


class AsyncDownloader:
    """异步文件下载器。

    支持动态任务管理、下载过程中添加 Hook 回调、并发控制。
    """

    def __init__(
        self,
        save_dir: str | Path = ".",
        num_workers: int = 8,
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
        self.progress = progressManager
        self.no_progress = no_progress

    async def _fetch_file_size(self, client: httpx.AsyncClient, url: str) -> int:
        response = await client.head(url, timeout=self.timeout)
        if response.status_code != 200:
            raise httpx.RequestError(f"HTTP {response.status_code}")
        return int(response.headers.get("Content-Length", 0))

    async def download_file(self, task_id: TaskID, url: str, full_path: Path):
        """
        下载文件

        Args:
            task_id: 任务 ID
            urls: 文件 URL
            full_path: 保存路径
        """
        async with self.semaphore:
            self.save_dir.mkdir(parents=True, exist_ok=True)

            async with httpx.AsyncClient() as client:
                content_length = await self._fetch_file_size(client, url)
                if content_length == 0:
                    await self.progress.update(
                        task_id,
                        description="[  丢失  ]:",
                        state="error",
                    )
                async with client.stream("GET", url, timeout=self.timeout) as response:
                    if response.status_code != 200:
                        raise httpx.RequestError(f"HTTP {response.status_code}")
                    async with await anyio.open_file(full_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 5):
                            await f.write(chunk)
                            await self.progress.update(
                                task_id,
                                advance=len(chunk),
                                total=content_length,
                            )

                        await self.progress.update(
                            task_id,
                            description="[  完成  ]:",
                            state="completed",
                        )

    async def add_task(self, url: str, file_name: str, file_suffix: str):
        """添加下载任务.

        Args:
            url: 文件 URL.
            file_name: 文件名称.
            file_suffix: 文件后缀.
        """
        # 文件路径
        file_path = f"{file_name}{file_suffix}"
        # 文件全路径
        full_path = self.save_dir / file_path

        if full_path.exists():
            task_id = await self.progress.add_task(
                description="[  跳过  ]:",
                filename=file_name,
                start=True,
                total=1,
                completed=1,
            )
            await self.progress.update(task_id, state="completed")
        else:
            task_id = await self.progress.add_task(
                description=f"[  {file_suffix}  ]:",
                filename=file_name,
                start=True,
                visible=not self.no_progress,
            )
            await self.progress.update(task_id, state="starting")
            download_task = asyncio.create_task(self.download_file(task_id, url, full_path))
            self.download_tasks.append(download_task)

    async def execute_tasks(self):
        """执行所有下载任务"""
        logging.info(f"开始下载歌曲 总共:{len(self.download_tasks)}")
        await asyncio.gather(*self.download_tasks)
        logging.info("下载完成")
        self.download_tasks.clear()
