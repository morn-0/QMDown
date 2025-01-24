import asyncio
import logging
from pathlib import Path

import anyio
import httpx
from rich.progress import (
    TaskID,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from QMDown import console
from QMDown.utils.progress import ProgressManager


class AsyncDownloader:
    """异步文件下载器"""

    def __init__(
        self,
        save_dir: str | Path = ".",
        num_workers: int = 3,
        no_progress: bool = False,
        timeout: int = 10,
        overwrite: bool = False,
    ):
        """
        Args:
            save_dir: 文件保存目录.
            max_concurrent: 最大并发下载任务数.
            timeout: 每个请求的超时时间(秒).
            no_progress: 是否显示进度.
            overwrite: 是否强制覆盖已下载文件.
        """
        self.save_dir = Path(save_dir)
        self.max_concurrent = num_workers
        self.timeout = timeout
        self.semaphore = asyncio.Semaphore(num_workers)
        self.download_tasks = []
        self.progress = ProgressManager()
        self.no_progress = no_progress
        self.overwrite = overwrite

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.ReadTimeout, httpx.ConnectTimeout)),
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
        retry=retry_if_exception_type((httpx.RequestError, httpx.ReadTimeout, httpx.ConnectTimeout)),
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
                            await self.progress.update(
                                task_id,
                                advance=len(chunk),
                                total=content_length,
                                visible=True,
                            )
                    await self.progress.update(task_id, visible=False)
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

            if not self.overwrite and full_path.exists():
                logging.info(f"[green][ 跳过 ] [blue]{file_name}")
            else:
                task_id = await self.progress.add_task(
                    description=f"[  {file_suffix.replace('.', '')}  ]:",
                    filename=file_name,
                    visible=False,
                )
                download_task = asyncio.create_task(self.download_file(task_id, url, full_path))
                self.download_tasks.append(download_task)

    async def execute_tasks(self):
        """执行所有下载任务"""
        if len(self.download_tasks) == 0:
            return
        logging.info(f"开始下载歌曲 总共:{len(self.download_tasks)}")
        if self.no_progress:
            with console.status("下载歌曲中..."):
                await asyncio.gather(*self.download_tasks)
            logging.info("完成")
        else:
            with self.progress:
                await asyncio.gather(*self.download_tasks)
        self.download_tasks.clear()
