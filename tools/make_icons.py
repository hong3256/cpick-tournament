#!/usr/bin/env python3
"""C-PICK 대진표 앱 아이콘 생성 (PIL).
네이비 그라데이션 배경 + 흰 패들(엣지 테이프) + 'C' 모노그램 + 노란 피클볼.
"""
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 2048  # 작업 캔버스(1024 설계 좌표의 2배 렌더 후 축소)
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"


def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def gradient(size, c0, c1):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(0, size, 4):
            t = x / size * 0.45 + y / size * 0.55
            c = lerp(c0, c1, min(1.0, t))
            for dx in range(4):
                if x + dx < size:
                    px[x + dx, y] = c
    return img


def paddle_layer(size):
    lay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    k = size / 1024.0

    def sc(*v):
        return tuple(int(round(x * k)) for x in v)

    # 부드러운 그림자
    sh = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle(sc(290, 150, 760, 950), radius=int(170 * k), fill=(3, 14, 30, 125))
    sh = sh.filter(ImageFilter.GaussianBlur(int(34 * k)))
    lay.alpha_composite(sh, (int(16 * k), int(26 * k)))

    d = ImageDraw.Draw(lay)
    # 목 + 손잡이
    d.rounded_rectangle(sc(470, 540, 570, 760), radius=int(40 * k), fill=(238, 244, 252, 255))
    d.rounded_rectangle(sc(452, 690, 588, 930), radius=int(68 * k), fill=(233, 240, 250, 255))
    for y in range(742, 900, 44):
        d.rounded_rectangle(sc(470, y, 570, y + 16), radius=int(8 * k), fill=(190, 203, 220, 255))
    d.rounded_rectangle(sc(452, 862, 588, 930), radius=int(34 * k), fill=(31, 95, 208, 255))

    # 헤드
    d.rounded_rectangle(sc(296, 160, 744, 612), radius=int(166 * k), fill=(255, 255, 255, 255))
    d.rounded_rectangle(sc(296, 160, 744, 612), radius=int(166 * k), outline=(198, 212, 230, 255), width=int(18 * k))
    d.rounded_rectangle(sc(334, 198, 706, 574), radius=int(132 * k), outline=(226, 234, 244, 255), width=int(7 * k))

    # 'C' 모노그램
    font = ImageFont.truetype(FONT, int(320 * k))
    txt = "C"
    bbox = d.textbbox((0, 0), txt, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx, cy = 516 * k, 392 * k
    d.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), txt, font=font, fill=(23, 80, 184, 255))

    return lay.rotate(-14, resample=Image.BICUBIC, center=(520 * k, 560 * k))


def ball_layer(size):
    lay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    k = size / 1024.0
    cx, cy, r = 802 * k, 762 * k, 126 * k
    sh = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((cx - r, cy - r + 14 * k, cx + r, cy + r + 14 * k), fill=(3, 14, 30, 130))
    sh = sh.filter(ImageFilter.GaussianBlur(18 * k))
    lay.alpha_composite(sh)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(233, 245, 104, 255), outline=(255, 255, 255, 255), width=int(13 * k))
    for hx, hy in [(-0.40, -0.36), (0.24, -0.44), (0.46, 0.04), (0.08, 0.40), (-0.42, 0.24), (-0.04, -0.02)]:
        rr = 22 * k
        x, y = cx + hx * r, cy + hy * r
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=(184, 200, 40, 255))
    return lay


def build(final=1024, maskable=False):
    inner = int(S * (0.76 if maskable else 1.0))
    canvas = gradient(S, (38, 98, 190), (8, 28, 54)).convert("RGBA")

    art = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    hl = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse((-S * 0.55, -S * 0.7, S * 0.85, S * 0.45), fill=(132, 197, 255, 70))
    hl = hl.filter(ImageFilter.GaussianBlur(int(S * 0.06)))
    art.alpha_composite(hl)

    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    base.alpha_composite(paddle_layer(S))
    base.alpha_composite(ball_layer(S))

    if maskable:
        base = base.resize((inner, inner), Image.LANCZOS)
        off = (S - inner) // 2
        art.alpha_composite(base, (off, off))
    else:
        art.alpha_composite(base)

    canvas = Image.alpha_composite(canvas, art)

    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.22), fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(canvas, (0, 0), m)
    return out.resize((final, final), Image.LANCZOS)


def preview():
    bg = Image.new("RGB", (980, 400), (238, 242, 247))
    a = build(192)
    bg.paste(a, (40, 40), a)
    b = build(240)
    bg.paste(b, (280, 40), b)
    c = build(360)
    bg.paste(c, (560, 20), c)
    bg.save(os.path.join(OUT, "tools", "icon-preview.png"))


if __name__ == "__main__":
    build(512).save(os.path.join(OUT, "icon-512.png"), optimize=True)
    build(192).save(os.path.join(OUT, "icon-192.png"), optimize=True)
    build(512, maskable=True).save(os.path.join(OUT, "icon-maskable-512.png"), optimize=True)
    build(180).save(os.path.join(OUT, "apple-touch-icon.png"), optimize=True)
    build(256).convert("RGB").save(os.path.join(OUT, "favicon.ico"), sizes=[(16, 16), (32, 32), (48, 48)])
    build(1024).save(os.path.join(OUT, "icon-1024.png"), optimize=True)
    preview()
    print("icons written")
