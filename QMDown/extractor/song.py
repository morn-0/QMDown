from qqmusic_api import song
from typing_extensions import override

from QMDown.extractor._abc import SingleExtractor
from QMDown.model import Song


class SongExtractor(SingleExtractor):
    _VALID_URL = (
        r"https?://y\.qq\.com/n/ryqq/songDetail/(?P<id>[0-9A-Za-z]+)",
        r"https?://i\.y\.qq\.com/v8/playsong\.html\?.*songmid=(?P<id>[0-9A-Za-z]+)",
    )

    @override
    async def extract(self, url: str):
        id = self._match_id(url)
        data = await song.query_song([id])
        if data:
            self.report_info(f"获取成功: {id}")
            return Song.model_validate(data[0])
        self.report_error(f"获取失败: {url}")
        return None
