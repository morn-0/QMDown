from qqmusic_api import songlist
from typing_extensions import override

from QMDown.extractor._abc import BatchExtractor
from QMDown.model import Song


class SonglistExtractor(BatchExtractor):
    _VALID_URL = (
        r"https?://y\.qq\.com/n/ryqq/playlist/(?P<id>[0-9]+)",
        r"https?://i\.y\.qq\.com/n2/m/share/details/taoge\.html\?.*id=(?P<id>[0-9]+)",
    )

    @override
    async def extract(self, url: str):
        id = self._match_id(url)
        _songlist = songlist.Songlist(int(id))
        data = await _songlist.get_song()
        info = await _songlist.get_detail()
        if data:
            self.report_info(f"获取成功: {id} {info['title']} - {info['creator']['nick']}")
            return [Song.model_validate(song) for song in data]
        self.report_error(f"获取失败:{url}")
        return None
