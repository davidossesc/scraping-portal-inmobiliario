"""Extracción desde la página de detalle de una propiedad: coordenadas, dirección,
atributos estructurados y fecha de publicación relativa.

La página no expone una fecha exacta de publicación (solo texto relativo tipo
"Publicado hoy" / "Publicado hace 3 días"), así que se guarda el texto crudo y
una fecha estimada a partir de él. La fuente confiable de "primera vez visto"
es el historial de corridas en BigQuery (fecha_scraping por partición).
"""
import re
import time
import random
from datetime import date, timedelta

from selenium.common.exceptions import TimeoutException

from config import PAUSA_ENTRE_DETALLES_MIN_SEG, PAUSA_ENTRE_DETALLES_MAX_SEG

CAMPOS_DETALLE_VACIOS = {
    "barrio": None,
    "dormitorios": None,
    "banos": None,
    "superficie_util_m2": None,
    "superficie_total_m2": None,
    "latitud": None,
    "longitud": None,
    "fecha_publicacion_texto": None,
    "fecha_publicacion": None,
}

RE_LISTING_ID = re.compile(r"(MLC-?\d+)", re.I)
RE_LATLONG = re.compile(
    r'"map_info":\{"icon":\{"id":"PIN_REAL_ESTATE"\},"location":\{'
    r'"latitude":"(?P<lat>-?[\d.]+)","longitude":"(?P<lon>-?[\d.]+)"'
)
RE_DIRECCION = re.compile(r'"target":"location_and_points".*?"text":"(?P<direccion>[^"]+)"')
RE_PUBLICADO = re.compile(r'"subtitle":"[^"]*Publicado (?P<rel>[^"\\]+)"')
RE_ATRIBUTOS_BLOQUE = re.compile(r'"attributes":\[(?P<bloque>.*?)\]')
RE_ATRIBUTO_PAR = re.compile(r'"id":"(?P<id>[^"]+)","text":"(?P<text>[^"]+)"')


def _extraer_listing_id(link: str) -> str | None:
    m = RE_LISTING_ID.search(link)
    return m.group(1).replace("-", "") if m else None


def _extraer_latlong(html: str) -> tuple[float | None, float | None]:
    m = RE_LATLONG.search(html)
    if not m:
        return None, None
    return float(m.group("lat")), float(m.group("lon"))


def _extraer_direccion(html: str) -> str | None:
    m = RE_DIRECCION.search(html)
    return m.group("direccion") if m else None


def _extraer_atributos(html: str) -> dict:
    atributos = {}
    for bloque_match in RE_ATRIBUTOS_BLOQUE.finditer(html):
        for par in RE_ATRIBUTO_PAR.finditer(bloque_match.group("bloque")):
            atributos[par.group("id")] = par.group("text")
    return atributos


def _parsear_publicado_relativo(texto: str | None, hoy: date) -> date | None:
    if not texto:
        return None
    texto = texto.strip().lower()
    texto = re.sub(r"\bun[oa]?\b", "1", texto)
    if texto == "hoy":
        return hoy
    if texto == "ayer":
        return hoy - timedelta(days=1)
    if texto == "esta semana":
        return hoy - timedelta(days=3)
    m = re.match(r"hace (\d+) d[ií]a", texto)
    if m:
        return hoy - timedelta(days=int(m.group(1)))
    m = re.match(r"hace (\d+) semana", texto)
    if m:
        return hoy - timedelta(weeks=int(m.group(1)))
    m = re.match(r"(?:hace |m[aá]s de )(\d+) mes", texto)
    if m:
        return hoy - timedelta(days=int(m.group(1)) * 30)
    m = re.match(r"(?:hace |m[aá]s de )(\d+) a[ñn]o", texto)
    if m:
        return hoy - timedelta(days=int(m.group(1)) * 365)
    return None


def _texto_a_float(texto: str | None) -> float | None:
    if not texto:
        return None
    m = re.search(r"[\d.,]+", texto)
    if not m:
        return None
    return float(m.group().replace(".", "").replace(",", "."))


def raspar_detalle(driver, link: str) -> dict:
    try:
        driver.get(link)
    except TimeoutException:
        print(f"Timeout cargando detalle, se salta: {link}")
        return {"listing_id": _extraer_listing_id(link), **CAMPOS_DETALLE_VACIOS}
    time.sleep(random.uniform(PAUSA_ENTRE_DETALLES_MIN_SEG, PAUSA_ENTRE_DETALLES_MAX_SEG))
    html = driver.page_source
    hoy = date.today()

    latitud, longitud = _extraer_latlong(html)
    atributos = _extraer_atributos(html)
    publicado_texto = None
    m = RE_PUBLICADO.search(html)
    if m:
        publicado_texto = m.group("rel")

    return {
        "listing_id": _extraer_listing_id(link),
        "barrio": _extraer_direccion(html),
        "dormitorios": _texto_a_float(atributos.get("Dormitorios")),
        "banos": _texto_a_float(atributos.get("Baños")),
        "superficie_util_m2": _texto_a_float(atributos.get("Superficie útil")),
        "superficie_total_m2": _texto_a_float(atributos.get("Superficie total")),
        "latitud": latitud,
        "longitud": longitud,
        "fecha_publicacion_texto": publicado_texto,
        "fecha_publicacion": _parsear_publicado_relativo(publicado_texto, hoy),
    }
