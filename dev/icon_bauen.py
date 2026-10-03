# -*- coding: utf-8 -*-
"""
Erzeugt icon.png (128x128), logo.png (250x100) und webapp/static/icon.png aus der
Vorlage dev/icon_vorlage.jpg (ChatGPT-Bild, 1024x1024, Hintergrund-Schachbrett
eingebrannt). Ausgeschnitten wird das abgerundete Quadrat mit dem tuerkisen Rahmen,
ausserhalb wird es echt transparent.

    python dev/icon_bauen.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

HIER = os.path.dirname(os.path.abspath(__file__))
WURZEL = os.path.dirname(HIER)
VORLAGE = os.path.join(HIER, "icon_vorlage.jpg")

# Rahmen in der Vorlage (gemessen an den tuerkisen Pixeln) und Eckenradius
LINKS, RECHTS, OBEN, UNTEN = 102, 921, 84, 921
RADIUS = 112
SCHRIFT = "#0D9488"   # Tuerkis wie der Rahmen – lesbar auf hellem und dunklem HA-Thema
SCHRIFTARTEN = ["C:/Windows/Fonts/segoeuib.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def symbol() -> Image.Image:
    """Abgerundetes Quadrat freigestellt, quadratisch mit etwas Rand (RGBA)."""
    bild = Image.open(VORLAGE).convert("RGBA")
    breite, hoehe = RECHTS - LINKS + 1, UNTEN - OBEN + 1
    teil = bild.crop((LINKS, OBEN, RECHTS + 1, UNTEN + 1))
    # Maske 4-fach gross zeichnen und verkleinern = weiche Kanten
    f = 4
    maske = Image.new("L", (breite * f, hoehe * f), 0)
    ImageDraw.Draw(maske).rounded_rectangle((0, 0, breite * f - 1, hoehe * f - 1), RADIUS * f, fill=255)
    teil.putalpha(maske.resize((breite, hoehe), Image.LANCZOS))
    seite = max(breite, hoehe) + 24
    quadrat = Image.new("RGBA", (seite, seite), (0, 0, 0, 0))
    quadrat.paste(teil, ((seite - breite) // 2, (seite - hoehe) // 2), teil)
    return quadrat


def schriftart(groesse):
    for pfad in SCHRIFTARTEN:
        if os.path.exists(pfad):
            return ImageFont.truetype(pfad, groesse)
    return ImageFont.load_default()


def main():
    s = symbol()
    s.resize((128, 128), Image.LANCZOS).save(os.path.join(WURZEL, "icon.png"))
    s.resize((96, 96), Image.LANCZOS).save(os.path.join(WURZEL, "webapp", "static", "icon.png"))

    # Logo 250x100: Symbol links, Schriftzug zweizeilig rechts (4-fach gezeichnet)
    f = 4
    logo = Image.new("RGBA", (250 * f, 100 * f), (0, 0, 0, 0))
    gross = s.resize((84 * f, 84 * f), Image.LANCZOS)
    logo.paste(gross, (4 * f, 8 * f), gross)
    zeichnen = ImageDraw.Draw(logo)
    schrift = schriftart(30 * f)
    zeichnen.text((98 * f, 16 * f), "EV PV-", font=schrift, fill=SCHRIFT)
    zeichnen.text((98 * f, 52 * f), "Laden", font=schrift, fill=SCHRIFT)
    logo.resize((250, 100), Image.LANCZOS).save(os.path.join(WURZEL, "logo.png"))
    print("icon.png, logo.png, webapp/static/icon.png geschrieben")


if __name__ == "__main__":
    main()
