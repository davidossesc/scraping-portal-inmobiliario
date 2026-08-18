"""Configuración central: comunas, tipos de propiedad, operaciones y límites del scraper."""

# slug usado por portalinmobiliario.com en la URL de búsqueda.
# Providencia fue verificado en el script original; el resto se valida en la
# corrida de descubrimiento (main.py --verificar-comunas) antes de scrapear en serio.
COMUNAS = {
    "vina-del-mar": "vina-del-mar-valparaiso",
    "nunoa": "nunoa-metropolitana",
    "providencia": "providencia-metropolitana",
    "la-reina": "la-reina-metropolitana",
}

TIPOS_PROPIEDAD = ["departamento", "casa"]
OPERACIONES = ["venta", "arriendo"]

ITEMS_POR_PAGINA = 50
PAGINAS_POR_COMBO_DEFAULT = 10

BASE_URL = "https://www.portalinmobiliario.com"

ESPERA_MIN_SEG = 4.5
ESPERA_MAX_SEG = 7.0
PAUSA_ENTRE_PAGINAS_MIN_SEG = 2.0
PAUSA_ENTRE_PAGINAS_MAX_SEG = 4.0
PAUSA_ENTRE_DETALLES_MIN_SEG = 2.5
PAUSA_ENTRE_DETALLES_MAX_SEG = 5.0

COLUMNAS_SALIDA = [
    "listing_id",
    "titulo",
    "precio_valor",
    "precio_moneda",
    "operacion",
    "tipo_propiedad",
    "comuna",
    "direccion_texto",
    "barrio",
    "dormitorios",
    "banos",
    "superficie_util_m2",
    "superficie_total_m2",
    "latitud",
    "longitud",
    "fecha_publicacion",
    "fecha_publicacion_texto",
    "fecha_scraping",
    "link",
]


def construir_url_busqueda(comuna_slug: str, tipo: str, operacion: str, pagina: int = 1) -> str:
    base = f"{BASE_URL}/{operacion}/{tipo}/{comuna_slug}/_OrderId_BEGINS*DESC_NoIndex_True"
    if pagina <= 1:
        return base
    desde_item = ((pagina - 1) * ITEMS_POR_PAGINA) + 1
    return (
        f"{BASE_URL}/{operacion}/{tipo}/{comuna_slug}"
        f"/_Desde_{desde_item}_OrderId_BEGINS*DESC_NoIndex_True"
    )
