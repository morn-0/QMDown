import logging
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from QMDown import console

logger = logging.getLogger("QMDown.fetcher")

T = TypeVar("T")
Y = TypeVar("Y")


class Fetcher(ABC, Generic[T, Y]):
    _console = console

    @abstractmethod
    async def fetch(self, data):
        raise NotImplementedError

    def report_info(self, msg: str):
        logger.info(
            f"[blue bold][{self.__class__.__name__}][/] {msg}",
        )

    def report_error(self, msg: str):
        logger.error(
            f"[blue bold][{self.__class__.__name__}][/] {msg}",
        )


class SingleFetcher(Fetcher[T, Y]):
    @abstractmethod
    async def fetch(self, data: T) -> Y:
        raise NotImplementedError


class BatchFetcher(Fetcher[T, Y]):
    @abstractmethod
    async def fetch(self, data: list[T]) -> list[Y]:
        raise NotImplementedError
