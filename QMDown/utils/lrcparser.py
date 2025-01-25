import re
from bisect import bisect_left
from collections import defaultdict


class LrcRegexes:
    """包含用于解析 LRC 文件的正则表达式集合."""

    LIDTag_Type = re.compile(r"[a-z]{2,}(?=:)")
    LIDTag_Content = re.compile(r"(?<=[a-z]{2}:).*")
    LIDTag = re.compile(r"(?<=^\[)[^\[\]]*(?=\])")
    LLyrics = re.compile(r"[^\[\]]*$")
    LBrackets = re.compile(r"(?<=\[).*(?=\])")
    LTimestamp = re.compile(r"\d*[\.,:]\d*[\.,:]\d*")


def stamp2tag(timestamp: float) -> str:
    """
    将时间戳(以秒为单位)转换为 LRC 时间标签格式(如 `00:01.23`).

    Args:
        timestamp: 时间戳,单位为秒.

    Returns:
        格式化的 LRC 时间标签.
    """
    mm = int(timestamp // 60)  # 分钟部分
    ss = int(timestamp % 60)  # 秒部分
    xx = int((timestamp - mm * 60 - ss) * 100)  # 百分之一秒部分
    return f"{mm:02}:{ss:02}.{xx:02}"


def tag2stamp(IDTag: str) -> float | None:
    """
    将 LRC 时间标签转换为时间戳(以秒为单位).

    Args:
        IDTag: LRC 时间标签(如 `00:01.23`).

    Returns:
        转换后的时间戳,单位为秒;如果标签无效,则返回 None.
    """
    IDTag = "".join(LrcRegexes.LTimestamp.findall(IDTag))
    if not IDTag:
        return None

    div = IDTag.split(":")
    try:
        if len(div) == 2:  # 格式:mm:ss.xx
            mm, ss = div
            ss, xx = ss.split(".")
        else:  # 格式:mm:ss:xx
            mm, ss, xx = div
        return int(mm) * 60 + int(ss) + int(xx) * (0.1 ** len(xx))
    except ValueError:
        return None


class LrcParser:
    """用于解析 LRC 的解析器."""

    def __init__(self, lrc: str | None = None) -> None:
        """
        初始化 LrcParser 实例.

        Args:
            lrc: LRC 文件内容的字符串表示形式.默认为空字符串.
        """
        self.metadata: dict[str, str] = {}
        self.lyrics: dict[float, list[tuple[str, str]]] = defaultdict(list)
        self._lyrics_sorted: tuple[int | None, dict[float, list[tuple[str, str]]] | None] = (None, None)
        self.offset: float = 0.0
        if lrc:
            self.parse_lrc(lrc)

    @property
    def lyrics_sorted(self) -> dict[float, list[tuple[str, str]]]:
        """
        获取按时间戳排序的歌词字典.

        Returns:
            按时间戳排序的歌词字典.
        """
        last_id, last_dict = self._lyrics_sorted
        if last_id != id(self.lyrics):
            sorted_lyrics = dict(sorted(self.lyrics.items()))
            self._lyrics_sorted = (id(self.lyrics), sorted_lyrics)
        return self._lyrics_sorted[1] if self._lyrics_sorted[1] is not None else {}

    def parse_lrc(self, lrc: str) -> None:
        """
        解析 LRC 文件内容.

        Args:
            lrc: LRC 文件内容的字符串表示形式.
        """
        for line in lrc.splitlines():
            IDTags = LrcRegexes.LIDTag.findall(line)
            if not IDTags:
                continue
            IDTagType = "".join(LrcRegexes.LIDTag_Type.findall("".join(IDTags)))
            IDTagContent = "".join(LrcRegexes.LIDTag_Content.findall("".join(IDTags)))
            lyrics = "".join(LrcRegexes.LLyrics.findall(line))
            if IDTagType:
                self.metadata[IDTagType] = IDTagContent
            else:
                for _IDTag in IDTags:
                    timestamp = tag2stamp(_IDTag)
                    if timestamp is not None and timestamp >= 0:
                        timestamp += self.offset
                        if lyrics:
                            self.lyrics[timestamp].append((_IDTag, lyrics))
        self._lyrics_sorted = (None, None)  # 重置已排序的歌词缓存

    def add(self, timestamp: float, value: str | list[str]) -> None:
        """
        添加一行或多行具有相同时间戳的歌词.

        Args:
            timestamp: 时间戳,单位为秒.
            value: 要添加的歌词行,可以是字符串或字符串列表
        """
        if isinstance(value, str):
            value = [value]
        for v in value:
            self.lyrics[timestamp].append((stamp2tag(timestamp), v))
        self._lyrics_sorted = (None, None)  # 重置已排序的歌词缓存

    def clear(self) -> None:
        """清空歌词缓存."""
        self.lyrics.clear()
        self._lyrics_sorted = (None, None)  # 重置已排序的歌词缓存

    def dump(self) -> str:
        """格式化当前歌词缓冲区并返回一个 LRC 格式的字符串。"""
        lrc = ""

        # 添加标签
        for attr, value in self.metadata.items():
            lrc += f"[{attr}:{value}]\n"

        # 添加歌词
        for timestamp, lyrics in sorted(self.lyrics.items()):  # 确保时间戳排序
            for tag, _lyric in lyrics:
                lrc += f"\n[{stamp2tag(timestamp)}]{_lyric}"

        return lrc

    def find(self, timestamp: float) -> tuple[float, list[tuple[str, str]], int] | None:
        """
        查找与给定时间戳最接近的歌词.

        Args:
            timestamp: 要查找的时间戳,单位为秒.

        Returns:
            与给定时间戳最接近的歌词信息,包括实际时间戳,对应的歌词列表和索引;如果未找到,则返回 None.
        """
        timestamps = list(self.lyrics.keys())
        if not timestamps:
            return None
        index = bisect_left(timestamps, timestamp)
        if index == 0:
            closest_timestamp = timestamps[0]
        elif index == len(timestamps):
            closest_timestamp = timestamps[-1]
        else:
            before = timestamps[index - 1]
            after = timestamps[index]
            closest_timestamp = before if (timestamp - before) <= (after - timestamp) else after
        return closest_timestamp, self.lyrics[closest_timestamp], index
