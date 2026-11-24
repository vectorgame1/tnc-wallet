
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter


WIDTH = 1080
HEIGHT = 720

GOLD = (239, 190, 85)
WHITE = (250, 249, 246)
MUTED = (163, 165, 175)
GREEN = (66, 205, 137)
RED = (238, 100, 105)


def get_font(size, bold=False):
    names = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)

    return ImageFont.load_default()


def money(value):
    return f"{float(value):,.2f}".replace(",", " ").rstrip("0").rstrip(".")


def base_image():
    image = Image.new("RGB", (WIDTH, HEIGHT), (8, 10, 16))
    draw = ImageDraw.Draw(image, "RGBA")

    # Фоновое золотое свечение
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)

    gd.ellipse(
        (650, -250, 1350, 450),
        fill=(191, 137, 48, 48),
    )
    gd.ellipse(
        (-300, 450, 400, 1100),
        fill=(125, 82, 30, 22),
    )

    glow = glow.filter(ImageFilter.GaussianBlur(85))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    draw = ImageDraw.Draw(image, "RGBA")

    # Основная панель
    draw.rounded_rectangle(
        (48, 42, 1032, 678),
        radius=42,
        fill=(16, 19, 27, 248),
        outline=(191, 145, 63, 175),
        width=2,
    )

    # Декоративная рамка
    draw.rounded_rectangle(
        (67, 61, 1013, 659),
        radius=32,
        outline=(255, 255, 255, 16),
        width=1,
    )

    # Монета TNC
    draw.ellipse(
        (870, 78, 972, 180),
        fill=(94, 64, 24, 255),
        outline=GOLD,
        width=4,
    )
    draw.ellipse(
        (880, 88, 962, 170),
        outline=(255, 221, 151, 220),
        width=2,
    )
    draw.text(
        (921, 129),
        "T",
        font=get_font(55, True),
        fill=GOLD,
        anchor="mm",
    )

    draw.text(
        (100, 94),
        "TNC",
        font=get_font(49, True),
        fill=GOLD,
    )
    draw.text(
        (245, 112),
        "ECOSYSTEM  /  DIGITAL FINANCE",
        font=get_font(18, True),
        fill=MUTED,
    )

    draw.line(
        (100, 170, 980, 170),
        fill=(205, 163, 83, 75),
        width=2,
    )

    return image


def finish(image):
    output = BytesIO()
    image.convert("RGB").save(
        output,
        format="PNG",
        optimize=True,
    )
    output.seek(0)
    return output


def create_section_image(section, title, subtitle, detail=""):
    image = base_image()
    draw = ImageDraw.Draw(image, "RGBA")

    draw.text(
        (105, 225),
        section.upper(),
        font=get_font(23, True),
        fill=GOLD,
    )

    draw.text(
        (105, 310),
        title,
        font=get_font(55, True),
        fill=WHITE,
    )

    draw.text(
        (105, 395),
        subtitle,
        font=get_font(27),
        fill=MUTED,
    )

    if detail:
        draw.rounded_rectangle(
            (105, 485, 975, 565),
            radius=20,
            fill=(196, 148, 59, 25),
            outline=(220, 174, 91, 85),
            width=2,
        )
        draw.text(
            (140, 525),
            detail[:65],
            font=get_font(22, True),
            fill=GOLD,
            anchor="lm",
        )

    draw.text(
        (105, 610),
        "YOUR ACCOUNT. YOUR ECOSYSTEM.",
        font=get_font(18, True),
        fill=(139, 141, 151),
    )

    return finish(image)


def create_transaction_image(
    amount,
    operation="deposit",
    username="TNC USER",
    operation_id="",
):
    styles = {
        "deposit": ("ПОПОЛНЕНИЕ", "+", GREEN, "Средства зачислены"),
        "withdraw": ("СПИСАНИЕ", "−", RED, "Средства списаны"),
        "received": ("ПЕРЕВОД ПОЛУЧЕН", "+", GREEN, "Входящий перевод"),
        "sent": ("ПЕРЕВОД ОТПРАВЛЕН", "−", RED, "Исходящий перевод"),
        "bonus": ("БОНУС TNC", "+", GOLD, "Награда зачислена"),
        "reward": ("НАГРАДА", "+", GOLD, "Поздравляем с достижением"),
        "refund": ("ВОЗВРАТ", "+", GREEN, "Средства возвращены"),
    }

    title, sign, color, subtitle = styles.get(
        operation,
        styles["deposit"],
    )

    image = base_image()
    draw = ImageDraw.Draw(image, "RGBA")

    draw.rounded_rectangle(
        (105, 205, 975, 278),
        radius=20,
        fill=(*color, 27),
        outline=(*color, 125),
        width=2,
    )

    draw.text(
        (540, 241),
        title,
        font=get_font(29, True),
        fill=color,
        anchor="mm",
    )

    draw.text(
        (540, 365),
        f"{sign}{money(amount)}",
        font=get_font(91, True),
        fill=WHITE,
        anchor="mm",
    )

    draw.text(
        (540, 445),
        "TNC",
        font=get_font(38, True),
        fill=GOLD,
        anchor="mm",
    )

    draw.text(
        (540, 505),
        subtitle,
        font=get_font(25),
        fill=MUTED,
        anchor="mm",
    )

    draw.line(
        (105, 565, 975, 565),
        fill=(205, 163, 83, 80),
        width=2,
    )

    draw.text(
        (105, 600),
        str(username)[:35],
        font=get_font(20, True),
        fill=WHITE,
    )

    draw.text(
        (975, 600),
        "TNC WALLET",
        font=get_font(19, True),
        fill=GOLD,
        anchor="ra",
    )

    if operation_id:
        draw.text(
            (105, 632),
            f"ID: {str(operation_id)[:30]}",
            font=get_font(13),
            fill=MUTED,
        )

    return finish(image)
