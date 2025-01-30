from typing_extensions import override

from QMDown import api
from QMDown.extractor._abc import BatchExtractor


class SingerExtractor(BatchExtractor):
    _VALID_URL = (
        r"https?://y\.qq\.com/n/ryqq/singer/(?P<id>[0-9A-Za-z]+)",
        r"https?://i\.y\.qq\.com/n2/m/share/profile_v2/index\.html\?.*singermid=(?P<id>[0-9A-Za-z]+)",
    )

    @override
    async def extract(self, url: str):
        id = self._match_id(url)
        singer = await api.get_singer_detail(id)
        self.report_info(f"获取成功: {id} {singer.name}")
        return singer.songs
