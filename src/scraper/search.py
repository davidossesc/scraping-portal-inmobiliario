"""Extracción de tarjetas de resultados desde las páginas de listado (búsqueda paginada)."""
import time
import random
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException

from config import construir_url_busqueda, ESPERA_MIN_SEG, ESPERA_MAX_SEG


def raspar_pagina_listado(driver, url: str) -> list[dict]:
    try:
        driver.get(url)
    except TimeoutException:
        print(f"Timeout cargando página de listado, se salta: {url}")
        return []
    time.sleep(random.uniform(ESPERA_MIN_SEG, ESPERA_MAX_SEG))

    soup = BeautifulSoup(driver.page_source, "html.parser")
    cards = soup.find_all("li", class_="ui-search-layout__item")

    propiedades = []
    for card in cards:
        try:
            title_element = card.find("a", class_="poly-component__title")
            titulo = title_element.text.strip() if title_element else "Sin título"
            link = title_element["href"] if title_element else None
            if not link:
                continue

            price_element = card.find("span", class_="andes-money-amount__fraction")
            currency_element = card.find("span", class_="andes-money-amount__currency-symbol")
            precio_valor, precio_moneda = None, None
            if price_element and currency_element:
                precio_moneda = "UF" if "UF" in currency_element.text else "CLP"
                precio_valor = float(price_element.text.replace(".", "").replace(",", "."))

            location_element = card.find("span", class_="poly-component__location")
            ubicacion = location_element.text.strip() if location_element else None

            propiedades.append({
                "titulo": titulo,
                "precio_valor": precio_valor,
                "precio_moneda": precio_moneda,
                "direccion_texto": ubicacion,
                "link": link.split("#")[0],
            })
        except Exception:
            continue

    return propiedades


def raspar_combo(driver, comuna_slug: str, tipo: str, operacion: str, paginas: int) -> list[dict]:
    resultados = []
    for pagina in range(1, paginas + 1):
        url = construir_url_busqueda(comuna_slug, tipo, operacion, pagina)
        datos_pagina = raspar_pagina_listado(driver, url)
        if not datos_pagina:
            if pagina == 1:
                # una página 1 vacía casi nunca es "sin resultados" real (toda comuna
                # grande tiene inventario); lo más probable es un bloqueo/interstitial
                # transitorio, así que se reintenta una vez antes de rendirse.
                print(f"Página 1 sin resultados para {comuna_slug}/{tipo}/{operacion}, reintentando...")
                time.sleep(random.uniform(6.0, 10.0))
                datos_pagina = raspar_pagina_listado(driver, url)
                if not datos_pagina:
                    print(f"ALERTA: {comuna_slug}/{tipo}/{operacion} sigue sin resultados tras reintento, posible bloqueo")
                    break
            else:
                break
        resultados.extend(datos_pagina)
        time.sleep(random.uniform(2.0, 4.0))
    return resultados
