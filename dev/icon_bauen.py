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


def logo_bauen(s: Image.Image, breite: int, hoehe: int) -> Image.Image:
    """Logo im Format 2,5:1: Symbol links, Schriftzug zweizeilig rechts (4-fach gezeichnet)."""
    f = 4 * breite / 250            # Masse unten fuer 250x100, skaliert
    logo = Image.new("RGBA", (round(250 * f), round(100 * f)), (0, 0, 0, 0))
    gross = s.resize((round(84 * f), round(84 * f)), Image.LANCZOS)
    logo.paste(gross, (round(4 * f), round(8 * f)), gross)
    zeichnen = ImageDraw.Draw(logo)
    schrift = schriftart(round(30 * f))
    zeichnen.text((98 * f, 16 * f), "EV PV-", font=schrift, fill=SCHRIFT)
    zeichnen.text((98 * f, 52 * f), "Laden", font=schrift, fill=SCHRIFT)
    return logo.resize((breite, hoehe), Image.LANCZOS)


def main():
    s = symbol()
    # Add-on (Store) und Oberflaeche
    s.resize((128, 128), Image.LANCZOS).save(os.path.join(WURZEL, "icon.png"))
    s.resize((96, 96), Image.LANCZOS).save(os.path.join(WURZEL, "webapp", "static", "icon.png"))
    logo_bauen(s, 250, 100).save(os.path.join(WURZEL, "logo.png"))

    # HA-Integration (ab HA 2026.3: custom_components/<domain>/brand/ statt brands-Repo)
    # Groessen wie im brands-Repo: icon 256x256 (@2x 512), logo kuerzere Seite 128–256 (@2x 256–512)
    brand = os.path.join(WURZEL, "custom_components", "ev_pv_laden_prognose", "brand")
    os.makedirs(brand, exist_ok=True)
    s.resize((256, 256), Image.LANCZOS).save(os.path.join(brand, "icon.png"))
    s.resize((512, 512), Image.LANCZOS).save(os.path.join(brand, "icon@2x.png"))
    logo_bauen(s, 320, 128).save(os.path.join(brand, "logo.png"))
    logo_bauen(s, 640, 256).save(os.path.join(brand, "logo@2x.png"))
    print("icon.png, logo.png, webapp/static/icon.png und brand/ der Integration geschrieben")


if __name__ == "__main__":
    main()
