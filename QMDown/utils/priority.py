from enum import Enum

from qqmusic_api.song import SongFileType


class SongFileTypePriority(Enum):
    MASTER = 130
    ATMOS_2 = 120
    ATMOS_51 = 110
    FLAC = 100
    OGG_640 = 90
    OGG_320 = 80
    MP3_320 = 70
    OGG_192 = 60
    MP3_128 = 50
    OGG_96 = 40
    ACC_192 = 30
    ACC_96 = 20
    ACC_48 = 10


def get_priority(file_type: SongFileType | int) -> list[SongFileType]:
    try:
        if isinstance(file_type, SongFileType):
            p = SongFileTypePriority[file_type.name].value
        else:
            p = file_type

        return [SongFileType[ft.name] for ft in SongFileTypePriority if ft.value <= p]
    except KeyError:
        return [SongFileType.MP3_128]
