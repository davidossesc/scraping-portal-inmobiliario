import time
import random
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from webdriver_manager.microsoft import EdgeChromiumDriverManager

def configurar_navegador():
    print("Iniciando Edge WebDriver...")
    options = Options()
    # User-Agent real y moderno para mitigar bloqueos de Cloudflare/MercadoLibre
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-blink-features=AutomationControlled")
    # Se recomienda no usar headless al principio para evitar detecciones agresivas antibot,
    # pero puedes descomentar la siguiente línea si prefieres que corra en segundo plano:
    # options.add_argument("--headless") 
    
    driver = webdriver.Edge(service=Service(EdgeChromiumDriverManager().install()), options=options)
    return driver

def raspar_pagina(driver, url):
    print(f"Abriendo: {url}")
    driver.get(url)
    
    # Espera aleatoria para simular comportamiento humano y dar tiempo a que cargue el JS dinámico
    tiempo_espera = random.uniform(4.5, 7.0)
    time.sleep(tiempo_espera)
    
    html = driver.page_source
    soup = BeautifulSoup(html, 'html.parser')
    
    # Lista contenedora de esta página
    propiedades_pagina = []
    
    # Las publicaciones en PortalInmobiliario/MercadoLibre típicamente usan esta clase en listas
    cards = soup.find_all('li', class_='ui-search-layout__item')
    
    for card in cards:
        try:
            # 1. Título de la propiedad
            title_element = card.find('a', class_='poly-component__title')
            titulo = title_element.text.strip() if title_element else "Sin título"
            
            # 2. Precio (Monto y Símbolo/Divisa)
            price_element = card.find('span', class_='andes-money-amount__fraction')
            currency_element = card.find('span', class_='andes-money-amount__currency-symbol')
            precio = f"{currency_element.text} {price_element.text}" if price_element and currency_element else "Sin precio"
            
            # 3. Enlace directo a la publicación
            link_element = card.find('a', class_='poly-component__title')
            link = link_element['href'] if link_element else "Sin link"
            
            # 4. Características (m² útiles, dormitorios, baños, etc.)
            attributes = card.find_all('li', class_='poly-attributes_list__item')
            atributos_texto = [attr.text.strip() for attr in attributes]
            caracteristicas = " | ".join(atributos_texto)
            
            # 5. Ubicación o barrio (si está disponible en la tarjeta)
            location_element = card.find('span', class_='poly-component__location')
            ubicacion = location_element.text.strip() if location_element else "Providencia"
            
            propiedades_pagina.append({
                'Título': titulo,
                'Precio': precio,
                'Características': caracteristicas,
                'Ubicación': ubicacion,
                'Enlace': link
            })
        except Exception as e:
            # Si una tarjeta en particular falla por estructura inusual, continúa con la siguiente
            continue
            
    return propiedades_pagina

def scraping_masivo_providencia(paginas_totales=3):
    driver = configurar_navegador()
    todas_propiedades = []
    
    # URL Base limpia de departamentos en venta en Providencia
    url_base = "https://www.portalinmobiliario.com/venta/departamento/providencia-metropolitana/_OrderId_BEGINS*DESC_NoIndex_True"
    
    try:
        for pagina in range(1, paginas_totales + 1):
            print(f"\n--- Procesando Página {pagina} de {paginas_totales} ---")
            
            if pagina == 1:
                url_actual = url_base
            else:
                # El sistema de paginación de MercadoLibre/PortalInmobiliario funciona saltando de 50 en 50 items.
                # Página 1: item 1 al 50. Página 2: desde el 51. Página 3: desde el 101, etc.
                desde_item = ((pagina - 1) * 50) + 1
                url_actual = f"https://www.portalinmobiliario.com/venta/departamento/providencia-metropolitana/_Desde_{desde_item}_OrderId_BEGINS*DESC_NoIndex_True"
            
            # Ejecutar el raspado de la página actual
            datos_pagina = raspar_pagina(driver, url_actual)
            
            if not datos_pagina:
                print("No se encontraron más propiedades o se activó un bloqueo/captcha. Deteniendo preventivamente.")
                break
                
            print(f"Se encontraron {len(datos_pagina)} propiedades en esta página.")
            todas_propiedades.extend(datos_pagina)
            
            # Pausa extra de cortesía entre páginas para no saturar el servidor
            time.sleep(random.uniform(2.0, 4.0))
            
    finally:
        # Garantizar que el navegador se cierre pase lo que pase
        driver.quit()
        print("\nNavegador cerrado.")
        
    # --- PROCESAMIENTO CON PANDAS ---
    if todas_propiedades:
        # Convertir la lista de diccionarios a un DataFrame de Pandas
        df = pd.DataFrame(todas_propiedades)
        
        # Eliminar duplicados si es que se llegó a repetir alguna propiedad entre transiciones
        df = df.drop_duplicates(subset=['Enlace'])
        
        # Guardar en archivo CSV con codificación adecuada para tildes y caracteres en español
        nombre_archivo = 'departamentos_providencia_masivo.csv'
        df.to_csv(nombre_archivo, index=False, encoding='utf-8-sig')
        
        print(f"\n¡Proceso Finalizado con Éxito!")
        print(f"Total de registros únicos guardados: {len(df)}")
        print(f"Archivo guardados como: '{nombre_archivo}'")
    else:
        print("\nNo se recopilaron datos. Verifica la conexión o las clases CSS del portal.")

if __name__ == "__main__":
    # Puedes modificar el número aquí si quieres probar con menos (ej. 3) antes de lanzar las 20 páginas completas
    NUMERO_PAGINAS = 20
    scraping_masivo_providencia(paginas_totales=NUMERO_PAGINAS)
