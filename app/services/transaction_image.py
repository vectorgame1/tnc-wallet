from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

WIDTH, HEIGHT = 1080, 720
BG = (17, 19, 16)
PANEL = (27, 30, 25)
INK = (242, 241, 232)
MUTED = (157, 162, 145)
LIME = (200, 241, 105)
GOOD = (184, 233, 134)
BAD = (255, 140, 130)


def get_font(size, bold=False):
    names = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def money(value):
    return f"{float(value):,.2f}".replace(",", " ").rstrip("0").rstrip(".")


def base_image():
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((620, -300, 1320, 400), fill=(200, 241, 105, 30))
    gd.ellipse((-300, 430, 420, 1080), fill=(200, 241, 105, 15))
    glow = glow.filter(ImageFilter.GaussianBlur(100))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    draw = ImageDraw.Draw(image, "RGBA")

    # Editorial frame: no coin, neon outline, or generic crypto badge.
    draw.rounded_rectangle((38, 38, 1042, 682), radius=30, fill=(*PANEL, 248), outline=(255, 255, 255, 18), width=2)
    draw.rectangle((38, 38, 50, 682), fill=(*LIME, 255))
    draw.text((92, 83), "TNC  /  ACCOUNT SYSTEMS", font=get_font(21, True), fill=INK)
    draw.text((92, 119), "PERSONAL FINANCE INTERFACE", font=get_font(13, True), fill=MUTED)
    draw.line((92, 164, 986, 164), fill=(255, 255, 255, 28), width=2)

    # Abstract architectural motif on the right.
    draw.polygon([(790, 205), (982, 205), (982, 397), (888, 350)], fill=(200, 241, 105, 230))
    draw.polygon([(790, 205), (888, 350), (790, 495), (694, 350)], fill=(68, 76, 57, 255))
    draw.polygon([(888, 350), (982, 397), (888, 542), (790, 495)], fill=(38, 43, 34, 255))
    draw.line((790, 205, 888, 350, 982, 397), fill=(242, 241, 232, 100), width=2)
    draw.text((92, 625), "TNC  •  INTERNAL ACCOUNT RECORD", font=get_font(14, True), fill=MUTED)
    return image


def finish(image):
    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def create_section_image(section, title, subtitle, detail=""):
    image = base_image()
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text((94, 218), str(section).upper()[:48], font=get_font(18, True), fill=LIME)
    draw.text((90, 285), str(title)[:28], font=get_font(51, True), fill=INK)
    draw.text((94, 366), str(subtitle)[:54], font=get_font(24), fill=MUTED)
    if detail:
        draw.rounded_rectangle((92, 445, 690, 525), radius=13, fill=(200, 241, 105, 18), outline=(200, 241, 105, 90), width=2)
        draw.text((118, 485), str(detail)[:48], font=get_font(18, True), fill=LIME, anchor="lm")
    return finish(image)


def create_transaction_image(amount, operation="deposit", username="TNC USER", operation_id=""):
    styles = {
        "deposit": ("ACCOUNT CREDIT", "+", GOOD, "Funds added to your TNC account"),
        "withdraw": ("ACCOUNT DEBIT", "−", BAD, "Funds deducted from your TNC account"),
        "received": ("TRANSFER RECEIVED", "+", GOOD, "Incoming internal transfer"),
        "sent": ("TRANSFER SENT", "−", BAD, "Outgoing internal transfer"),
        "bonus": ("ACCOUNT BONUS", "+", LIME, "A bonus was credited"),
        "reward": ("REWARD", "+", LIME, "An achievement reward was credited"),
        "refund": ("REFUND", "+", GOOD, "Funds returned to your account"),
    }
    title, sign, color, subtitle = styles.get(operation, styles["deposit"])
    image = base_image()
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text((94, 214), title, font=get_font(19, True), fill=color)
    draw.text((88, 285), f"{sign}{money(amount)}", font=get_font(78, True), fill=INK)
    draw.text((96, 382), "TNC", font=get_font(22, True), fill=LIME)
    draw.text((96, 432), subtitle, font=get_font(19), fill=MUTED)
    draw.line((94, 510, 690, 510), fill=(255, 255, 255, 28), width=2)
    draw.text((96, 542), str(username)[:32], font=get_font(17, True), fill=INK)
    if operation_id:
        draw.text((96, 576), f"REFERENCE  /  {str(operation_id)[:26]}", font=get_font(12), fill=MUTED)
    return finish(image)
