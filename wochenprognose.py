# -*- coding: utf-8 -*-
"""
7-Tage-Vorschau: lohnt sich das Laden mit PV?

Je Stunde der eigenen PV-Prognose (inkl. Morgentau):
  Ueberschuss = PV - typischer Hausverbrauch dieser Uhrzeit (Mittel der letzten Wochen)
  davon zuerst der Hausakku, bis er seinen typischen Tagesbedarf (mittlere Entladung je Tag)
  wieder hat – das Add-on gibt dem Hausakku Vorrang –, der Rest geht ans Auto,
  aber nur, wenn er die kleinste Ladeleistung erreicht (6 A einphasig = 1,4 kW).
Bewertung je Tag nach den kWh fuers Auto.
"""
from datetime import date, datetime, timedelta

LADE_MIN_KW = 1.4                 # 6 A einphasig: darunter kann das Auto nicht mit PV laden
LOHNT_KWH, MAESSIG_KWH = 6.0, 2.0  # Ampel: ab 6 kWh "lohnt sich", ab 2 kWh "mäßig"
TAGE = 7
LOHNT, MAESSIG, KAUM = "lohnt sich", "mäßig", "kaum"


def haus_profil(stunden_w: dict[datetime, float], tz) -> dict[int, float]:
    """Stundenmittel des Hausverbrauchs (W, Stundenbeginn UTC) -> {Uhrzeit lokal: kW}."""
    summe: dict[int, float] = {}
    anzahl: dict[int, int] = {}
    for t, w in stunden_w.items():
        if w is None:
            continue
        h = t.astimezone(tz).hour
        summe[h] = summe.get(h, 0.0) + max(w, 0.0) / 1000
        anzahl[h] = anzahl.get(h, 0) + 1
    return {h: round(summe[h] / anzahl[h], 3) for h in summe}


def bewertung(auto_kwh: float) -> str:
    return LOHNT if auto_kwh >= LOHNT_KWH else MAESSIG if auto_kwh >= MAESSIG_KWH else KAUM


def berechnen(werte: list[tuple[datetime, float]], profil: dict[int, float], akku_kwh: float,
              tz, heute: date, tage: int = TAGE) -> list[dict]:
    """werte: (Stundenbeginn UTC, PV kWh). profil: {Uhrzeit: kW Haus}. akku_kwh: typischer
    Tagesbedarf des Hausakkus. Gibt je Tag ab heute {datum, pv_kwh, akku_kwh, auto_kwh,
    bewertung} zurueck (heute als ganzer Tag)."""
    je_tag: dict[date, list[tuple[datetime, float]]] = {}
    for t, kwh in werte:
        tag = t.astimezone(tz).date()
        if heute <= tag < heute + timedelta(days=tage):
            je_tag.setdefault(tag, []).append((t, kwh))
    mittel = sum(profil.values()) / len(profil) if profil else 0.5
    aus = []
    for tag in sorted(je_tag):
        akku_rest, akku, auto, pv = akku_kwh, 0.0, 0.0, 0.0
        for t, kwh in sorted(je_tag[tag]):
            pv += kwh
            ueber = kwh - profil.get(t.astimezone(tz).hour, mittel)   # kWh in der Stunde = mittlere kW
            if ueber <= 0:
                continue
            nimm = min(ueber, akku_rest)
            akku_rest -= nimm
            akku += nimm
            ueber -= nimm
            if ueber >= LADE_MIN_KW:
                auto += ueber
        aus.append({"datum": tag.isoformat(), "pv_kwh": round(pv, 1), "akku_kwh": round(akku, 1),
                    "auto_kwh": round(auto, 1), "bewertung": bewertung(auto)})
    return aus
