"""Рисует иконку программы: seocrawler/window/page/icon.ico (16-256 px) и icon.png (192 px).

Нужна библиотека Pillow (только для этого скрипта, программе она не нужна): python -m pip install pillow.
Рисунок: синий скруглённый квадрат, белая лупа, у которой кольцо разомкнуто справа - получается буква «C».
Каждый размер рисуется отдельно (с запасом в 8 раз и уменьшением), чтобы в 16 px линии не расплывались.
"""
import math
import os
import sys

from PIL import Image, ImageDraw

BLUE = (37, 99, 235, 255)      # тот же синий, что в иконка.png для Яндекса
WHITE = (255, 255, 255, 255)
PAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seocrawler", "window", "page")


def draw(size):
    k = 8
    S = size * k
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = 0 if size <= 16 else S * 0.03
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=S * 0.22, fill=BLUE)
    # толщина линий: в маленьких размерах - ровно 2-3 пикселя, в больших - доля размера
    w = {16: 2.2, 20: 2.6, 24: 3, 32: 3.6}.get(size, size * 0.11) * k
    cx, cy, r = S * 0.43, S * 0.43, S * 0.25          # центр и радиус кольца лупы (по середине линии)
    gap, mid = 70, -25                                 # разрыв кольца справа (ширина и середина, в градусах): буква «C»
    box = [cx - r - w / 2, cy - r - w / 2, cx + r + w / 2, cy + r + w / 2]
    d.arc(box, start=mid + gap / 2, end=mid + 360 - gap / 2, fill=WHITE, width=int(w))
    for a in (mid + gap / 2, mid - gap / 2):                      # круглые концы у разрыва
        x, y = cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=WHITE)
    # ручка лупы вниз-вправо, толще кольца
    hw = w * 1.35
    a = math.radians(45)
    x0, y0 = cx + (r + w * 0.3) * math.cos(a), cy + (r + w * 0.3) * math.sin(a)
    x1, y1 = S * 0.80, S * 0.80
    d.line([x0, y0, x1, y1], fill=WHITE, width=int(hw))
    d.ellipse([x1 - hw / 2, y1 - hw / 2, x1 + hw / 2, y1 + hw / 2], fill=WHITE)
    return im.resize((size, size), Image.LANCZOS)


def main():
    sizes = [16, 20, 24, 32, 48, 64, 128, 256]
    imgs = [draw(s) for s in sizes]
    imgs[-1].save(os.path.join(PAGE, "icon.ico"), sizes=[(s, s) for s in sizes], append_images=imgs[:-1])
    draw(192).save(os.path.join(PAGE, "icon.png"))
    if len(sys.argv) > 1:                              # образец для просмотра: все размеры в ряд, крупно
        row = Image.new("RGBA", (sum(max(s, 16) * 4 + 20 for s in sizes[:5]) + 300, 300), (240, 240, 240, 255))
        x = 10
        for s, im in zip(sizes[:5], imgs[:5]):
            row.paste(im.resize((s * 4, s * 4), Image.NEAREST), (x, 10))
            row.paste(im, (x, 10 + s * 4 + 10))
            x += s * 4 + 20
        row.paste(draw(128), (x, 10))
        row.save(sys.argv[1])
    print("ok")


if __name__ == "__main__":
    main()
