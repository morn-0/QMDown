from pydantic import BaseModel


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

    def signer_to_str(self, sep: str = ","):
        return sep.join([s.title for s in self.singer])
