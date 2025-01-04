<div align="center">
    <a>
        <img src="https://socialify.git.ci/luren-dc/QMDown/image?description=1&font=Source%20Code%20Pro&language=1&logo=https%3A%2F%2Fy.qq.com%2Fmediastyle%2Fmod%2Fmobile%2Fimg%2Flogo.svg&name=1&pattern=Overlapping%20Hexagons&theme=Auto"/>
    </a>
    <a href="https://www.python.org">
        <img src="https://img.shields.io/badge/Python-3.10|3.11|3.12-blue" alt="Python"/>
    </a>
    <a href="https://github.com/luren-dc/QMDown?tab=MIT-1-ov-file">
        <img src="https://img.shields.io/github/license/luren-dc/QMDown" alt="GitHub license"/>
    </a>
    <a href="https://github.com/luren-dc/QMDown/stargazers">
        <img src="https://img.shields.io/github/stars/luren-dc/QMDown?color=yellow&label=Github%20Stars" alt="STARS"/>
    </a>
    <a href="https://github.com/astral-sh/uv">
      <img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv"/>
    </a>
</div>

---

> [!IMPORTANT]
> 本仓库的所有内容仅供学习和参考之用，禁止用于商业用途
>
> **音乐平台不易，请尊重版权，支持正版。**

## 特色

- 支持下载
  - [ ] 歌手
  - [x] 专辑
  - [x] 歌单
  - [x] 歌曲
  - [ ] 排行榜
- 支持下载高品质
  - [x] 臻品母带 (24Bit 192kHz)
  - [x] 臻品音质 (16Bit 44.1kHz)
  - [x] 臻品全景声 (16Bit 44.1kHz)
  - [x] flac (16Bit 44.1kHz~24Bit 48kHz)
  - OGG
    - [x] 640kbps
    - [x] 320kbps
    - [x] 192kbps
    - [x] 96kbps
  - MP3
    - [x] 320kbps
    - [x] 128kbps
  - AAC(M4A)
    - [x] 192kbps
    - [x] 96kbps
    - [x] 48kbps

### 已支持下载类型

| 类型 | 示例链接                                                                                                                       |
| ---- | ------------------------------------------------------------------------------------------------------------------------------ |
| base | `https://c6.y.qq.com/base/fcgi-bin/u?__=jXIuFz8tBzpA`                                                                          |
| 歌曲 | `https://y.qq.com/n/ryqq/songDetail/004Ti8rT003TaZ` <br/> `https://i.y.qq.com/v8/playsong.html?songmid=004UMhHW33BWSk`         |
| 歌单 | `https://y.qq.com/n/ryqq/playlist/1374105607` <br/> `https://i.y.qq.com/n2/m/share/details/taoge.html?id=7524170477`           |
| 专辑 | `https://y.qq.com/n/ryqq/albumDetail/003dYC933CfoSi` <br/> `https://i.y.qq.com/n2/m/share/details/album.html?albumId=50967596` |

## 基本使用

```console
Usage: QMDown [OPTIONS] URLS...

  QQ 音乐解析/下载工具

Arguments:
  URLS...  链接  [required]

Options:
  -o, --output PATH               歌曲保存路径  [default:...]
  --quality [130|120|110|100|90|80|70|60|50|40|30|20|10] 最大下载音质  [default: 50]
  -n, --num-workers INTEGER       最大并发下载数  [default: 8]
  --no-progress                   不显示进度条
  --no-color                      不显示颜色
  --debug                         启用调试模式
  -v, --version                   显示版本信息
  --install-completion            Install completion for the current shell.
  --show-completion               Show completion for the current shell, to copy it or customize the installation.
  -h, --help                      Show this message and exit.
```

## Licence

本项目基于 **[MIT License](https://github.com/luren-dc/QMDown?tab=MIT-1-ov-file)** 许可证发行。

## 免责声明

由于使用本项目产生的包括由于本协议或由于使用或无法使用本项目而引起的任何性质的任何直接、间接、特殊、偶然或结果性损害（包括但不限于因商誉损失、停工、计算机故障或故障引起的损害赔偿，或任何及所有其他商业损害或损失）由使用者负责

## 贡献者

[![Contributor](https://contrib.rocks/image?repo=luren-dc/QMDown)](https://github.com/luren-dc/QMDown/graphs/contributors)
