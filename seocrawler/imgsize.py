"""Реальные размеры картинки (ширина × высота) по первым байтам файла — без скачивания целиком.
Поддерживаются PNG, GIF, JPEG, WebP, AVIF и SVG (у SVG размеров в пикселях может не быть)."""
import re
import struct


def image_info(data: bytes, content_type: str = ""):
    """Возвращает (формат, ширина, высота). Если не распознали — (формат или '', None, None)."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
            w, h = struct.unpack(">II", data[16:24])
            return "PNG", w, h
        if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
            w, h = struct.unpack("<HH", data[6:10])
            return "GIF", w, h
        if data[:2] == b"\xff\xd8":
            return ("JPEG",) + _jpeg(data)
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ("WebP",) + _webp(data)
        if data[4:12] in (b"ftypavif", b"ftypavis") or b"ftypavif" in data[:32]:
            return ("AVIF",) + _avif(data)
        head = data[:2048].lstrip().lower()
        if head.startswith(b"<svg") or head.startswith(b"<?xml") and b"<svg" in head:
            return ("SVG",) + _svg(data)
    except Exception:
        pass
    ct = (content_type or "").lower()
    fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/gif": "GIF", "image/webp": "WebP",
           "image/avif": "AVIF", "image/svg+xml": "SVG"}.get(ct.split(";")[0].strip(), "")
    return fmt, None, None


def _jpeg(d):
    i = 2
    while i + 9 < len(d):
        if d[i] != 0xFF:
            i += 1
            continue
        marker = d[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = struct.unpack(">H", d[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", d[i + 5:i + 9])
            return w, h
        i += 2 + seg_len
    return None, None


def _webp(d):
    chunk = d[12:16]
    if chunk == b"VP8 " and len(d) >= 30:
        w, h = struct.unpack("<HH", d[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L" and len(d) >= 25:
        b = d[21:25]
        w = 1 + (((b[1] & 0x3F) << 8) | b[0])
        h = 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
        return w, h
    if chunk == b"VP8X" and len(d) >= 30:
        w = 1 + int.from_bytes(d[24:27], "little")
        h = 1 + int.from_bytes(d[27:30], "little")
        return w, h
    return None, None


def _avif(d):
    i = d.find(b"ispe")
    if i > 0 and len(d) >= i + 16:
        w, h = struct.unpack(">II", d[i + 8:i + 16])
        return w, h
    return None, None


def _svg(d):
    head = d[:4096].decode("utf-8", "ignore")
    m = re.search(r"<svg[^>]*>", head, re.S | re.I)
    if not m:
        return None, None
    tag = m.group(0)

    def num(attr):
        mm = re.search(attr + r'\s*=\s*["\']\s*([\d.]+)\s*(px)?\s*["\']', tag)
        return int(float(mm.group(1))) if mm else None
    w, h = num("width"), num("height")
    if w and h:
        return w, h
    vb = re.search(r'viewBox\s*=\s*["\']\s*[\d.\-]+[\s,]+[\d.\-]+[\s,]+([\d.]+)[\s,]+([\d.]+)', tag)
    if vb:
        return int(float(vb.group(1))), int(float(vb.group(2)))
    return None, None
