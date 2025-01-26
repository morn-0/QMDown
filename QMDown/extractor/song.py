from typing_extensions import override

from QMDown import api
from QMDown.extractor._abc import SingleExtractor


class SongExtractor(SingleExtractor):
    _VALID_URL = (
        r"https?://y\.qq\.com/n/ryqq/songDetail/(?P<id>[0-9A-Za-z]+)",
        r"https?://i\.y\.qq\.com/v8/playsong\.html\?.*songmid=(?P<id>[0-9A-Za-z]+)",
    )

    @override
    async def extract(self, url: str):
        id = self._match_id(url)
        song = (await api.query([id]))[0]
        self.report_info(f"获取成功: {id} {song.get_full_name()}")
        return song
