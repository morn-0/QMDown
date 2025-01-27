from qqmusic_api import Credential, album, song, songlist

from QMDown.model import AlbumDetial, Song, SongDetail, SonglistDetail, SongUrl
from QMDown.utils.cache import cached


@cached(args_to_cache_key=lambda args: ",".join(args.arguments["value"]))
async def query(value: list[str] | list[int]) -> list[Song]:
    return [Song.model_validate(song) for song in await song.query_song(value)]


@cached(args_to_cache_key=lambda args: args.arguments["mid"])
async def get_song_detail(mid: str) -> SongDetail:
    return SongDetail.model_validate(await song.Song(mid=mid).get_detail())


async def get_download_url(
    mids: list[str], quality: song.SongFileType, credential: Credential | None = None
) -> list[SongUrl]:
    urls = await song.get_song_urls(mids, quality, credential)
    return [SongUrl(mid=mid, url=url, type=quality) for mid, url in urls.items()]


@cached(args_to_cache_key=lambda args: args.arguments["mid"] or args.arguments["id"])
async def get_album_detail(mid: str | None = None, id: int | None = None):
    if mid:
        model = album.Album(mid=mid)
    elif id:
        model = album.Album(id=id)
    else:
        raise ValueError("mid 和 id 不能同时为空")

    data = await model.get_detail()
    songs = await model.get_song()
    data.update(
        {
            "company": data["company"]["name"],
            "singer": data["singer"]["singerList"],
            "songs": songs,
        }
    )
    return AlbumDetial.model_validate(data)


@cached(args_to_cache_key=lambda args: str(args.arguments["id"]))
async def get_songlist_detail(id: int):
    model = songlist.Songlist(id=id)
    data = await model.get_detail()
    data["songs"] = await model.get_song()
    return SonglistDetail.model_validate(data)
