from io import BytesIO
from pathlib import Path
from hashlib import sha256

from PIL import Image, ImageDraw, ImageFont, ImageFilter

WIDTH, HEIGHT = 1080, 720
BG = (7, 13, 24)
PANEL = (13, 25, 43)
INK = (239, 246, 255)
MUTED = (137, 160, 190)
LIME = (139, 190, 255)
GOOD = (104, 220, 180)
BAD = (255, 128, 145)


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


def base_image(variant="account"):
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((620, -300, 1320, 400), fill=(104, 165, 244, 42))
    gd.ellipse((-300, 430, 420, 1080), fill=(48, 111, 190, 27))
    glow = glow.filter(ImageFilter.GaussianBlur(100))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    draw = ImageDraw.Draw(image, "RGBA")

    # Editorial frame: no coin, neon outline, or generic crypto badge.
    draw.rounded_rectangle((38, 38, 1042, 682), radius=30, fill=(*PANEL, 248), outline=(255, 255, 255, 18), width=2)
    draw.rectangle((38, 38, 50, 682), fill=(*LIME, 255))
    draw.text((92, 83), "TNC  /  PRIVATE ACCOUNT", font=get_font(21, True), fill=INK)
    draw.text((92, 119), "DIGITAL FINANCE INTERFACE", font=get_font(13, True), fill=MUTED)
    draw.line((92, 164, 986, 164), fill=(255, 255, 255, 28), width=2)

    # Cinematic glass architecture instead of the previous flat geometric emblem.
    seed = sha256(str(variant).encode("utf-8")).digest()
    slab = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sd = ImageDraw.Draw(slab)
    shift = seed[0] % 34
    points = [(735+shift, 250), (948, 294+shift), (1004, 542), (790-shift, 590), (700, 465)]
    sd.polygon([(x+15,y+20) for x,y in points], fill=(0,0,0,100))
    sd.polygon(points, fill=(110,157,210,42), outline=(190,220,255,125))
    sd.line([points[0],points[1],points[2]], fill=(224,239,255,190), width=5)
    sd.line([points[2],points[3],points[4]], fill=(91,145,210,110), width=3)
    sd.polygon([(770,284),(931,319),(965,500),(812,537)], fill=(185,216,252,22))
    slab = slab.filter(ImageFilter.GaussianBlur(1.2))
    image = Image.alpha_composite(image, slab)
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text((92, 625), "TNC  /  INTERNAL ACCOUNT RECORD", font=get_font(14, True), fill=MUTED)
    return image


def finish(image):
    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def create_section_image(section, title, subtitle, detail=""):
    image = base_image(section)
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
    image = base_image(operation)
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
