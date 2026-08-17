"""Orquesta: listado -> detalle -> DataFrame para un combo comuna/tipo/operación."""
from datetime import datetime, timezone

import pandas as pd

from config import COLUMNAS_SALIDA
from scraper.search import raspar_combo
from scraper.detail import raspar_detalle, _extraer_listing_id


def scrapear_combo(driver, comuna_nombre: str, comuna_slug: str, tipo: str, operacion: str, paginas: int) -> pd.DataFrame:
    listados = raspar_combo(driver, comuna_slug, tipo, operacion, paginas)

    filas = []
    fecha_scraping = datetime.now(timezone.utc).isoformat()
    vistos = set()
    for item in listados:
        listing_id = _extraer_listing_id(item["link"])
        if not listing_id or listing_id in vistos:
            continue
        vistos.add(listing_id)

        detalle = raspar_detalle(driver, item["link"])

        fila = {
            "listing_id": listing_id,
            "titulo": item["titulo"],
            "precio_valor": item["precio_valor"],
            "precio_moneda": item["precio_moneda"],
            "operacion": operacion,
            "tipo_propiedad": tipo,
            "comuna": comuna_nombre,
            "direccion_texto": item["direccion_texto"],
            "barrio": detalle["barrio"],
            "dormitorios": detalle["dormitorios"],
            "banos": detalle["banos"],
            "superficie_util_m2": detalle["superficie_util_m2"],
            "superficie_total_m2": detalle["superficie_total_m2"],
            "latitud": detalle["latitud"],
            "longitud": detalle["longitud"],
            "fecha_publicacion": detalle["fecha_publicacion"],
            "fecha_publicacion_texto": detalle["fecha_publicacion_texto"],
            "fecha_scraping": fecha_scraping,
            "link": item["link"],
        }
        filas.append(fila)

    if not filas:
        return pd.DataFrame(columns=COLUMNAS_SALIDA)

    df = pd.DataFrame(filas)
    df = df.drop_duplicates(subset=["listing_id"])
    return df[COLUMNAS_SALIDA]
