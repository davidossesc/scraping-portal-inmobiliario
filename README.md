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
3. BigQuery organiza los datos en 3 capas (arquitectura medallón, ver abajo): Bronze
   (tabla particionada, tal cual la entrega el scraper), Silver (limpieza) y Gold
   (vistas listas para Power BI).

## Arquitectura de datos en BigQuery (medallón)

```
Bronze   portal_inmobiliario_bronze.propiedades_raw
         Tabla nativa particionada por fecha_scraping_dia. Carga con WRITE_TRUNCATE
         por partición -> reintentar el mismo día es idempotente. Es la única tabla
         donde se escriben datos; todo lo demás son vistas encima.
              │
              ▼
Silver   portal_inmobiliario_silver.propiedades_limpias
         Vista: nombres de comuna legibles, UF/m² calculado (precio_uf_m2), y
         columnas booleanas que marcan outliers en vez de descartarlos
         (es_outlier_superficie, es_outlier_dormitorios, tiene_coordenadas).
              │
              ▼
Gold     portal_inmobiliario_gold.*
         Vistas de consumo directo para Power BI:
           - propiedades_actuales      último snapshot por listing_id (mapa/detalle)
           - metricas_comuna           KPIs agregados por comuna/tipo/operación
           - historico_precios_comuna  serie de tiempo por comuna/operación/día
```

Silver y Gold son **vistas**, no tablas materializadas — no hace falta ningún job de
transformación aparte; se recalculan solas cada vez que se consultan, siempre reflejan
el Bronze más reciente. `construir_capas_silver_y_gold()` en `src/storage/bigquery.py`
solo (re)define esas vistas — es barato y se corre después de cada carga.

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

Esta organización de GCP tiene bloqueada la creación de JSON keys de service account
(`iam.disableServiceAccountKeyCreation`), así que todo el pipeline autentica vía
**Application Default Credentials (ADC)** sin keys: localmente como tu propia cuenta,
en GitHub Actions como la service account vía **Workload Identity Federation (WIF)**.

1. Crear un proyecto en [console.cloud.google.com](https://console.cloud.google.com).
2. Habilitar **Google Sheets API** y **BigQuery API** (APIs & Services → Library).
3. Crear una **Service Account** (IAM & Admin → Service Accounts) — sin generar key.
4. Crear una Google Sheet vacía y compartirla (botón Compartir) con el email de la service
   account (termina en `...gserviceaccount.com`), con permiso **Editor**.
5. En IAM & Admin → IAM, dar los roles **BigQuery Data Editor** y **BigQuery Job User**
   a la service account (tu propia cuenta ya cubre BigQuery si es Owner/Editor del proyecto).
6. Completar `.env` con `GOOGLE_SHEET_ID`, `GCP_PROJECT_ID`, `BQ_DATASET` y
   `GCP_IMPERSONATE_SERVICE_ACCOUNT` (email de la service account).
7. Local: instalar el [Google Cloud SDK](https://cloud.google.com/sdk/docs/install), loguearte,
   y darte a vos mismo permiso para impersonar la service account (Google bloquea el
   consentimiento directo del scope de Sheets con el cliente OAuth de gcloud, así que Sheets
   se accede impersonando — ver `src/storage/sheets.py`):
   ```bash
   gcloud auth login
   gcloud auth application-default login

   gcloud iam service-accounts add-iam-policy-binding SA_EMAIL \
     --member="user:TU_EMAIL@gmail.com" \
     --role="roles/iam.serviceAccountTokenCreator"
   ```
8. GitHub Actions: configurar Workload Identity Federation (una vez) para que el workflow
   pueda actuar como la service account sin ningún secreto de larga duración:
   ```bash
   gcloud iam workload-identity-pools create "github-pool" --location="global" \
     --display-name="GitHub Actions"

   gcloud iam workload-identity-pools providers create-oidc "github-provider" \
     --location="global" --workload-identity-pool="github-pool" \
     --issuer-uri="https://token.actions.githubusercontent.com" \
     --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
     --attribute-condition="assertion.repository=='davidossesc/scraping-portal-inmobiliario'"

   gcloud iam service-accounts add-iam-policy-binding SA_EMAIL \
     --role="roles/iam.workloadIdentityUser" \
     --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/davidossesc/scraping-portal-inmobiliario"
   ```

### Variables de GitHub Actions

En el repo, Settings → Secrets and variables → Actions → pestaña **Variables** (no hace
falta ningún Secret — sin keys no hay nada de larga duración que guardar como secreto):

| Nombre | Valor |
|---|---|
| `GOOGLE_SHEET_ID` | id de la Google Sheet |
| `GCP_PROJECT_ID` | id del proyecto de GCP |
| `BQ_DATASET` | ej. `portal_inmobiliario` (base — se le agregan `_bronze`/`_silver`/`_gold`) |
| `WIF_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `WIF_SERVICE_ACCOUNT` | email de la service account |

## Conectar Power BI

Power BI Desktop → Obtener datos → Google BigQuery (conector nativo) → autenticar con la
cuenta de Google → dataset **`portal_inmobiliario_gold`** (no Bronze/Silver — Power BI
consume solo la capa Gold, ya curada):

- `propiedades_actuales` — mapa (`latitud`/`longitud`) y tabla de detalle.
- `metricas_comuna` — KPIs y gráficos de barra por comuna.
- `historico_precios_comuna` — gráfico de tendencia de precios en el tiempo.

El proyecto de Power BI (`00-Proyecto de prueba PBI/`) ya viene armado apuntando a estas
3 vistas.

## Riesgo de bloqueo

Scrapear desde runners de GitHub Actions (IP de datacenter) tiene más riesgo de bloqueo o
captcha que desde una IP residencial. Si las corridas empiezan a fallar seguido, la
alternativa es correr un [runner self-hosted](https://docs.github.com/actions/hosting-your-own-runners)
en tu propio PC — mismo workflow, misma UI de Actions, pero con tu IP.
