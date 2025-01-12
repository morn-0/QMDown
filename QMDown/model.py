from pydantic import BaseModel, HttpUrl
from qqmusic_api.song import SongFileType


class Singer(BaseModel):
    id: int
    mid: str
    name: str
    title: str


class Album(BaseModel):
    id: int
    mid: str
    name: str
    title: str


class Song(BaseModel):
    id: int
    mid: str
    name: str
    title: str
    singer: list[Singer]
    album: Album

    def singer_to_str(self, sep: str = ",") -> str:
        return sep.join([s.title for s in self.singer])

    def get_full_name(self, format: str = "{name} - {singer}", sep: str = ",") -> str:
        if "{name}" not in format:
            raise ValueError("format must contain {name}")
        if "{singer}" not in format:
            raise ValueError("format must contain {singer}")
        return format.format(name=self.name, singer=self.singer_to_str(sep=sep))


class SongUrl(BaseModel):
    id: int
    mid: str
    url: HttpUrl
    type: SongFileType
