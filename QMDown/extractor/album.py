from typing_extensions import override

from QMDown import api
from QMDown.extractor._abc import BatchExtractor


class AlbumExtractor(BatchExtractor):
    _VALID_URL = (
        r"https?://y\.qq\.com/n/ryqq/albumDetail/(?P<id>[0-9A-Za-z]+)",
        r"https?://i\.y\.qq\.com/n2/m/share/details/album\.html\?.*albumId=(?P<id>[0-9]+)",
    )

    @override
    async def extract(self, url: str):
        id = self._match_id(url)
        try:
            detail = await api.get_album_detail(id=int(id))
        except ValueError:
            detail = await api.get_album_detail(mid=id)

        self.report_info(f"获取成功: {id} {detail.info.name}")
        return detail.songs
