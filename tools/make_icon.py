"""assets/logo.png ve assets/icon.ico dosyalarını üretir. Çalıştırmak için: python tools/make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024  # büyük çizip küçültüyoruz ki kenarlar yumuşak olsun
ASSETS = Path(__file__).resolve().parent.parent / "assets"


def gradient(size, top, bottom):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
    return img


def draw_logo():
    # Arka plan: köşeleri yuvarlak, çapraz renk geçişli kare
    bg = gradient(S, (44, 44, 44), (0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((32, 32, S - 32, S - 32), radius=220, fill=255)
    logo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    logo.paste(bg, (0, 0), mask)

    # "Basılı tutuluyor" halkası: soluk iz + parlak ilerleme yayı.
    # Saydam iz arka planla karışsın diye ayrı katmanda çiziliyor.
    ring = (150, 150, S - 150, S - 150)
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(layer).arc(ring, 0, 360, fill=(255, 255, 255, 60), width=56)
    logo.alpha_composite(layer)
    d = ImageDraw.Draw(logo)
    d.arc(ring, -90, 200, fill=(255, 255, 255, 255), width=56)

    # Tuş: alt gövde (gölge) ve üstte basılmış yüzey
    d.rounded_rectangle((330, 370, 694, 704), radius=70, fill=(90, 90, 90))
    d.rounded_rectangle((330, 342, 694, 668), radius=70, fill=(255, 255, 255))
    d.rounded_rectangle((372, 376, 652, 626), radius=48, fill=(240, 240, 240))

    # Tuşun üstünde aşağı ok: "bas"
    d.polygon([(512, 580), (432, 470), (592, 470)], fill=(17, 17, 17))
    d.rounded_rectangle((482, 404, 542, 480), radius=14, fill=(17, 17, 17))
    return logo


def main():
    ASSETS.mkdir(exist_ok=True)
    logo = draw_logo()
    logo.resize((512, 512), Image.LANCZOS).save(ASSETS / "logo.png")
    logo.resize((256, 256), Image.LANCZOS).save(
        ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("assets/logo.png ve assets/icon.ico oluşturuldu")


if __name__ == "__main__":
    main()
