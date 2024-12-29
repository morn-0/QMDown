from pydantic import HttpUrl
from qqmusic_api.song import SongFileType, get_song_urls
from typing_extensions import override

from QMDown.fetcher._abc import BatchFetcher
from QMDown.model import Song, SongUrl
from QMDown.quality import get_priority
from QMDown.utils import find_by_attribute


class UrlFetcher(BatchFetcher[Song, SongUrl]):
    def __init__(self, priority: SongFileType | int) -> None:
        self.priority = priority

    @override
    async def fetch(self, data):
        try:
            qualities = get_priority(self.priority)
            mids = [song.mid for song in data]
            song_urls: list[SongUrl] = []
            for _quality in qualities:
                if len(mids) == 0:
                    break

                _urls = await get_song_urls(mids, _quality)
                mids = list(filter(lambda mid: not _urls[mid], _urls))
                [_urls.pop(mid, None) for mid in mids]
                self.report_info(f"[blue][{_quality.name}]:[/] 获取成功 {len(_urls)}")
                song_urls.extend(
                    [
                        SongUrl(id=find_by_attribute(data, "mid", mid).id, mid=mid, url=HttpUrl(url), quality=_quality)
                        for mid, url in _urls.items()
                        if url
                    ]
                )

            self.report_info(f"[red]获取歌曲链接成功: {len(data) -len(mids)}/{len(data)}")

            if len(mids) > 0:
                self.report_error(
                    f"[red]获取歌曲链接失败: {[find_by_attribute(data, 'mid', mid).get_full_name() for mid in mids]}"
                )
            return song_urls
        except ValueError:
            return []
