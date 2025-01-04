from qqmusic_api import album
from typing_extensions import override

from QMDown.extractor._abc import BatchExtractor
from QMDown.model import Song


class AlbumExtractor(BatchExtractor):
    _VALID_URL = (
        r"https?://y\.qq\.com/n/ryqq/albumDetail/(?P<id>[0-9A-Za-z]+)",
        r"https?://i\.y\.qq\.com/n2/m/share/details/album\.html\?.*albumId=(?P<id>[0-9]+)",
    )

    @override
    async def extract(self, url: str):
        id = self._match_id(url)
        try:
            _album = album.Album(id=int(id))
        except ValueError:
            _album = album.Album(mid=id)

        data = await _album.get_song()
        info = await _album.get_detail()
        if data:
            self.report_info(f"获取成功: {id} {info['basicInfo']['albumName']}")
            return [Song.model_validate(song) for song in data]
        return None
