# Scraping Portal Inmobiliario → Google Sheets → BigQuery → Power BI

Pipeline que scrapea Portal Inmobiliario (departamentos y casas, venta y arriendo) en
**Viña del Mar, Ñuñoa, Providencia y La Reina**, extrayendo por cada propiedad: precio,
características, **coordenadas reales (lat/long) para mapa**, y una **fecha de publicación
estimada**. Los resultados se consolidan en una Google Sheet y se cargan de forma
incremental a BigQuery para explotarlos en Power BI.

## Cómo funciona

1. `main.py` scrapea un combo comuna/tipo/operación con Selenium (la página se renderiza
   con JS y el sitio bloquea requests no-navegador con 403, por eso no se usa `requests`
   solo). Por cada propiedad visita también su página de detalle para sacar lat/long,
   dirección y atributos (dormitorios, baños, superficie, antigüedad, etc.).
2. GitHub Actions (`.github/workflows/scrape.yml`) corre las 16 combinaciones en paralelo
   (matrix) todos los días, y un job final las consolida, deduplica por `listing_id` y
   sube el resultado a Google Sheets y BigQuery.
3. BigQuery guarda una tabla particionada por día (`propiedades_raw`, histórico completo
   para análisis de tendencia de precios) y una vista `vw_propiedades_actual` con el
   último snapshot de cada propiedad — esa vista es la fuente recomendada para el mapa en
   Power BI.

### Nota sobre la fecha de publicación

El sitio no expone una fecha exacta de publicación en la página pública, solo texto
relativo ("Publicado hoy", "Publicado hace 3 días", etc.). Ese texto se guarda tal cual
en `fecha_publicacion_texto` y se convierte a una fecha aproximada en `fecha_publicacion`.
Para saber con certeza desde cuándo una propiedad aparece en tus datos, usa
`MIN(fecha_scraping)` agrupado por `listing_id` en `propiedades_raw` — eso sí es exacto,
porque lo determina tu propio historial de corridas.

## Uso local

```bash
python -m venv .venv
.venv/Scripts/activate      # Windows
pip install -r requirements.txt
cp .env.example .env        # completar tras el setup de GCP (ver abajo)

# Un combo, con navegador visible (recomendado para probar selectores nuevos)
python main.py --comuna providencia --tipo departamento --operacion venta --paginas 1

# Las 16 combinaciones en secuencia
python main.py --todos --paginas 3

# Consolidar todos los CSV generados y subir a Sheets + BigQuery
python main.py --agregar "data_*.csv" --sheets --bigquery
```

Localmente usa Edge (`--navegador edge`, default) porque es el navegador preinstalado en
Windows; en GitHub Actions (Ubuntu) usa Chrome (`--navegador chrome`).

## Setup de Google Cloud (una vez)

1. Crear un proyecto en [console.cloud.google.com](https://console.cloud.google.com).
2. Habilitar **Google Sheets API** y **BigQuery API** (APIs & Services → Library).
3. Crear una **Service Account** (IAM & Admin → Service Accounts) y generar una key JSON
   (Keys → Add Key → JSON). Guardarla como `credentials.json` en la raíz del repo (está en
   `.gitignore`, nunca se sube).
4. Crear una Google Sheet vacía y compartirla (botón Compartir) con el email de la service
   account (termina en `...gserviceaccount.com`), con permiso **Editor**.
5. En el proyecto de GCP, dar a la service account los roles **BigQuery Data Editor** y
   **BigQuery Job User** (IAM & Admin → IAM).
6. Completar `.env` con `GOOGLE_SHEET_ID` (de la URL de la Sheet), `GCP_PROJECT_ID` y
   `BQ_DATASET` (el dataset se crea solo en la primera carga, no hace falta crearlo a mano).

### Secrets de GitHub Actions

En el repo, Settings → Secrets and variables → Actions:

| Nombre | Tipo | Valor |
|---|---|---|
| `GCP_SA_KEY` | Secret | contenido completo del JSON de la service account |
| `GOOGLE_SHEET_ID` | Secret | id de la Google Sheet |
| `GCP_PROJECT_ID` | Secret | id del proyecto de GCP |
| `BQ_DATASET` | Variable | ej. `portal_inmobiliario` |

## Conectar Power BI

Power BI Desktop → Obtener datos → Google BigQuery (conector nativo) → autenticar con la
cuenta de Google → seleccionar el proyecto/dataset → tabla `vw_propiedades_actual` para el
mapa de propiedades actuales (usa `latitud`/`longitud` en un visual de mapa), y
`propiedades_raw` para análisis de tendencia de precios en el tiempo.

## Riesgo de bloqueo

Scrapear desde runners de GitHub Actions (IP de datacenter) tiene más riesgo de bloqueo o
captcha que desde una IP residencial. Si las corridas empiezan a fallar seguido, la
alternativa es correr un [runner self-hosted](https://docs.github.com/actions/hosting-your-own-runners)
en tu propio PC — mismo workflow, misma UI de Actions, pero con tu IP.
