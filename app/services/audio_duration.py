"""服务端音频时长解析（跟进录音等上传场景的兜底）。

历史上 ``voice_duration_sec`` 完全取自前端表单，客户端不传或传错时落库为空/错误值。
这里按容器头自行计算时长：解析失败返回 ``None``，由调用方回退前端传入值，保证
「读不出来」不会把整条跟进写失败。

支持的容器：wav / mp3(Layer III) / aac(ADTS) / m4a(mp4) / ogg(vorbis|opus) /
amr / webm(matroska)。不做完整解码，只读头信息与帧计数，纯字节解析无第三方依赖。
"""

from __future__ import annotations

import struct

__all__ = ["parse_audio_duration"]

_MP3_BITRATE_V1_L3 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
_MP3_BITRATE_V2_L3 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0)
_MP3_SAMPLE_RATE = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}
_AAC_SAMPLE_RATE = (96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350)
_AMR_FRAME_BYTES = (12, 13, 15, 17, 19, 20, 26, 31, 5, 6, 5, 5, 0, 0, 0, 0)


def parse_audio_duration(data: bytes) -> int | None:
    """返回音频时长（秒，四舍五入，最小 1）；无法识别容器或数据损坏时返回 None。"""
    if not data:
        return None
    seconds: float | None = None
    try:
        if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            seconds = _wav_duration(data)
        elif data[:4] == b"OggS":
            seconds = _ogg_duration(data)
        elif data[:5] == b"#!AMR":
            seconds = _amr_duration(data)
        elif data[4:8] == b"ftyp":
            seconds = _mp4_duration(data)
        elif data[:4] == b"\x1a\x45\xdf\xa3":
            seconds = _webm_duration(data)
        else:
            pos = _skip_id3(data)
            if pos + 2 <= len(data) and data[pos] == 0xFF and (data[pos + 1] & 0xF0) == 0xF0:
                # layer 位为 00 是 ADTS(AAC)，否则按 MP3 Layer III 处理。
                seconds = _adts_duration(data, pos) if (data[pos + 1] & 0x06) == 0 else _mp3_duration(data, pos)
    except (IndexError, ValueError, struct.error, ZeroDivisionError):
        return None
    if seconds is None or seconds <= 0:
        return None
    return max(1, round(seconds))


# ── WAV ──────────────────────────────────────────────────────────


def _wav_duration(data: bytes) -> float | None:
    pos = 12
    byte_rate = 0
    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        size = int.from_bytes(data[pos + 4:pos + 8], "little")
        body = pos + 8
        if chunk_id == b"fmt " and body + 16 <= len(data):
            byte_rate = int.from_bytes(data[body + 8:body + 12], "little")
        elif chunk_id == b"data" and byte_rate:
            # 截断文件按实际字节数算，比按头信誉更贴近可播放时长。
            available = min(size, len(data) - body)
            return available / byte_rate
        pos = body + size if size else len(data)
    return None


# ── MP3 ─────────────────────────────────────────────────────────


def _skip_id3(data: bytes) -> int:
    """跳过 ID3v2 头（含 footer / 扩展头），返回首个音频字节位置。"""
    pos = 0
    while data[pos:pos + 3] == b"ID3" and pos + 10 <= len(data):
        size = ((data[pos + 6] & 0x7F) << 21) | ((data[pos + 7] & 0x7F) << 14) \
            | ((data[pos + 8] & 0x7F) << 7) | (data[pos + 9] & 0x7F)
        has_footer = bool(data[pos + 5] & 0x10)
        pos += 10 + size + (10 if has_footer else 0)
    return pos


def _mp3_duration(data: bytes, pos: int) -> float | None:
    if pos + 4 > len(data) or data[pos] != 0xFF or (data[pos + 1] & 0xE0) != 0xE0:
        return None
    version = (data[pos + 1] >> 3) & 0x03  # 3=MPEG1, 2=MPEG2, 0=MPEG2.5, 1=保留
    layer = (data[pos + 1] >> 1) & 0x03  # 1=Layer III
    if version == 1 or layer != 1:
        return None
    bitrate_index = (data[pos + 2] >> 4) & 0x0F
    rate_index = (data[pos + 2] >> 2) & 0x03
    mono = ((data[pos + 3] >> 6) & 0x03) == 3
    if bitrate_index in (0, 15) or rate_index == 3:
        return None
    bitrate = (_MP3_BITRATE_V1_L3 if version == 3 else _MP3_BITRATE_V2_L3)[bitrate_index]
    sample_rate = _MP3_SAMPLE_RATE[version][rate_index]
    samples_per_frame = 1152 if version == 3 else 576
    # 帧头之后是 side info：MPEG1 单声道 17 字节、双声道 32 字节；MPEG2/2.5 单声道 9、双声道 17。
    side_info = (17 if mono else 32) if version == 3 else (9 if mono else 17)
    xing = pos + 4 + side_info
    if data[xing:xing + 4] in (b"Xing", b"Info") and xing + 12 <= len(data):
        flags = int.from_bytes(data[xing + 4:xing + 8], "big")
        if flags & 0x01:
            frames = int.from_bytes(data[xing + 8:xing + 12], "big")
            if frames:
                return frames * samples_per_frame / sample_rate
    # 无 Xing/VBRI：按 CBR 估算总时长（VBR 无头文件会有偏差，仅作兜底）。
    audio_bytes = max(0, len(data) - pos)
    if audio_bytes > 128 and data[-128:-125] == b"TAG":  # ID3v1
        audio_bytes -= 128
    return audio_bytes / (bitrate * 1000 / 8)


def _adts_duration(data: bytes, pos: int) -> float | None:
    frames = 0
    sample_rate: int | None = None
    while pos + 7 <= len(data):
        if data[pos] != 0xFF or (data[pos + 1] & 0xF6) != 0xF0:
            break
        rate_index = (data[pos + 2] >> 2) & 0x0F
        if rate_index >= len(_AAC_SAMPLE_RATE):
            return None
        frame_length = ((data[pos + 3] & 0x03) << 11) | (data[pos + 4] << 3) | (data[pos + 5] >> 5)
        if frame_length <= 0:
            return None
        if sample_rate is None:
            sample_rate = _AAC_SAMPLE_RATE[rate_index]
        frames += 1
        pos += frame_length
    if not frames or not sample_rate:
        return None
    return frames * 1024 / sample_rate


# ── MP4 / M4A ───────────────────────────────────────────────────


def _mp4_duration(data: bytes) -> float | None:
    for box, body, size in _iter_boxes(data, 0, len(data)):
        if box == b"moov":
            moov = data[body:body + size]
            for inner, inner_body, inner_size in _iter_boxes(moov, 0, len(moov)):
                if inner != b"mvhd":
                    continue
                head = moov[inner_body:inner_body + inner_size]
                version = head[0]
                if version == 1:
                    timescale = int.from_bytes(head[20:24], "big")
                    duration = int.from_bytes(head[24:32], "big")
                else:
                    timescale = int.from_bytes(head[12:16], "big")
                    duration = int.from_bytes(head[16:20], "big")
                if timescale:
                    return duration / timescale
    return None


def _iter_boxes(data: bytes, start: int, end: int):
    """遍历 mp4 box：yield (类型, 负载起点, 负载长度)。"""
    pos = start
    while pos + 8 <= end:
        size = int.from_bytes(data[pos:pos + 4], "big")
        box = data[pos + 4:pos + 8]
        header = 8
        if size == 1:
            if pos + 16 > end:
                return
            size = int.from_bytes(data[pos + 8:pos + 16], "big")
            header = 16
        elif size == 0:
            size = end - pos
        if size < header:
            return
        yield box, pos + header, min(size - header, end - pos - header)
        pos += size


# ── OGG（vorbis / opus） ─────────────────────────────────────────


def _ogg_duration(data: bytes) -> float | None:
    pos = 0
    serial: int | None = None
    sample_rate: int | None = None
    pre_skip = 0
    last_granule = 0
    while pos + 27 <= len(data):
        if data[pos:pos + 4] != b"OggS":
            break
        granule = int.from_bytes(data[pos + 6:pos + 14], "little")
        page_serial = int.from_bytes(data[pos + 14:pos + 18], "little")
        segments = data[pos + 26]
        body_start = pos + 27 + segments
        if body_start > len(data):
            break
        body_len = sum(data[pos + 27:body_start])
        body = data[body_start:body_start + body_len]
        if serial is None:
            serial = page_serial
            if body[:8] == b"OpusHead" and len(body) >= 12:
                # Opus 的 granulepos 恒按 48kHz 计，与输入采样率无关。
                sample_rate = 48000
                pre_skip = int.from_bytes(body[10:12], "little")
            elif b"\x01vorbis" in body[:8]:
                idx = body.find(b"\x01vorbis")
                if len(body) >= idx + 16:
                    sample_rate = int.from_bytes(body[idx + 12:idx + 16], "little")
        if page_serial == serial and granule != 0xFFFFFFFFFFFFFFFF:
            last_granule = max(last_granule, granule)
        pos = body_start + body_len
    if not sample_rate or last_granule <= 0:
        return None
    return max(0, last_granule - pre_skip) / sample_rate


# ── AMR ─────────────────────────────────────────────────────────


def _amr_duration(data: bytes) -> float | None:
    pos = 6 if data[:6] == b"#!AMR\n" else 9 if data[:9] == b"#!AMR-WB\n" else 0
    if not pos:
        return None
    frames = 0
    while pos < len(data):
        mode = (data[pos] >> 3) & 0x0F
        frame = 1 + _AMR_FRAME_BYTES[mode]
        if frame == 1:
            break
        pos += frame
        frames += 1
    # AMR-NB/WB 均为每帧 20ms。
    return frames * 0.02 if frames else None


# ── WebM / Matroska ─────────────────────────────────────────────

_EBML_SEGMENT = 0x18538067
_EBML_INFO = 0x1549A966
_EBML_TRACKS = 0x1654AE6B
_EBML_CLUSTER = 0x1F43B675
_EBML_DURATION = 0x4489
_EBML_TIMECODE_SCALE = 0x2AD7B1
_EBML_TRACK_ENTRY = 0xAE
_EBML_DEFAULT_DURATION = 0x23E383
_EBML_CLUSTER_TIMECODE = 0xE7
_EBML_SIMPLE_BLOCK = 0xA3
_EBML_BLOCK_GROUP = 0xA0
_EBML_BLOCK = 0xA1


def _ebml_id(data: bytes, pos: int) -> tuple[int, int]:
    first = data[pos]
    length = 1
    mask = 0x80
    while length <= 4 and not (first & mask):
        mask >>= 1
        length += 1
    if length > 4 or pos + length > len(data):
        raise ValueError("ebml id")
    return int.from_bytes(data[pos:pos + length], "big"), pos + length


def _ebml_size(data: bytes, pos: int) -> tuple[int, int]:
    first = data[pos]
    length = 1
    mask = 0x80
    while length <= 8 and not (first & mask):
        mask >>= 1
        length += 1
    if length > 8 or pos + length > len(data):
        raise ValueError("ebml size")
    value = first & (mask - 1)
    for byte in data[pos + 1:pos + length]:
        value = (value << 8) | byte
    return value, pos + length


def _iter_ebml(data: bytes, start: int, end: int):
    """遍历 EBML 子元素：yield (id, 负载起点, 负载长度)。"""
    pos = start
    while pos < end:
        element_id, pos = _ebml_id(data, pos)
        size, pos = _ebml_size(data, pos)
        if size < 0 or pos + size > end:
            return
        yield element_id, pos, size
        pos += size


def _webm_duration(data: bytes) -> float | None:
    segment = None
    for element_id, body, size in _iter_ebml(data, 0, len(data)):
        if element_id == _EBML_SEGMENT:
            segment = (body, body + size)
            break
    if segment is None:
        return None
    scale_ns = 1_000_000
    duration: float | None = None
    default_duration_ns = 0
    last_ms = 0
    last_block_ms = 0
    for element_id, body, size in _iter_ebml(data, segment[0], segment[1]):
        if element_id == _EBML_INFO:
            for sub_id, sub_body, sub_size in _iter_ebml(data, body, body + size):
                if sub_id == _EBML_DURATION and sub_size in (4, 8):
                    fmt = ">f" if sub_size == 4 else ">d"
                    duration = struct.unpack(fmt, data[sub_body:sub_body + sub_size])[0]
                elif sub_id == _EBML_TIMECODE_SCALE:
                    scale_ns = int.from_bytes(data[sub_body:sub_body + sub_size], "big") or scale_ns
        elif element_id == _EBML_TRACKS:
            for sub_id, sub_body, sub_size in _iter_ebml(data, body, body + size):
                if sub_id != _EBML_TRACK_ENTRY:
                    continue
                for entry_id, entry_body, entry_size in _iter_ebml(data, sub_body, sub_body + sub_size):
                    if entry_id == _EBML_DEFAULT_DURATION:
                        default_duration_ns = int.from_bytes(data[entry_body:entry_body + entry_size], "big")
        elif element_id == _EBML_CLUSTER:
            for sub_id, sub_body, sub_size in _iter_ebml(data, body, body + size):
                if sub_id == _EBML_CLUSTER_TIMECODE:
                    last_ms = int.from_bytes(data[sub_body:sub_body + sub_size], "big")
                elif sub_id in (_EBML_SIMPLE_BLOCK, _EBML_BLOCK_GROUP):
                    block = sub_body if sub_id == _EBML_SIMPLE_BLOCK else None
                    if block is None:
                        for inner_id, inner_body, inner_size in _iter_ebml(data, sub_body, sub_body + sub_size):
                            if inner_id == _EBML_BLOCK:
                                block = inner_body
                                break
                    if block is None:
                        continue
                    _, block_pos = _ebml_size(data, block)  # 跳过 track number vint
                    if block_pos + 2 <= len(data):
                        last_block_ms = int.from_bytes(data[block_pos:block_pos + 2], "big", signed=True)
    if duration:
        # Duration 以 TimecodeScale 为单位（默认 1ms）。
        return duration * scale_ns / 1_000_000_000
    if last_ms or last_block_ms:
        # 流式录音（MediaRecorder）常缺 Duration：用末簇时间码 + 末块偏移 + 帧时长近似。
        tail_ms = last_ms + max(0, last_block_ms) + (default_duration_ns / 1_000_000 if default_duration_ns else 0)
        return tail_ms * scale_ns / 1_000_000_000 if tail_ms else None
    return None
