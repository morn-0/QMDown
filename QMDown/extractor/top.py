from typing_extensions import override

from QMDown import api
from QMDown.extractor._abc import BatchExtractor


class ToplistExtractor(BatchExtractor):
    _VALID_URL = (
        r"https?://y\.qq\.com/n/ryqq/toplist/(?P<id>[0-9]+)",
        r"https?://i\.y\.qq\.com/n2/m/share/details/toplist\.html\?.*id=(?P<id>[0-9]+)",
    )

    @override
    async def extract(self, url: str):
        id = self._match_id(url)
        toplist = await api.get_toplist_detail(int(id))
        self.report_info(f"获取成功: {id} {toplist.title}")
        return toplist.songs
