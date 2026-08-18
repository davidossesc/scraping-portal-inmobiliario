"""Carga a BigQuery con arquitectura medallón (Bronze → Silver → Gold).

Bronze  (portal_inmobiliario_bronze.propiedades_raw)
    Tabla nativa particionada por día de scraping, tal cual la entrega el
    scraper — sin transformar. Cada corrida escribe (WRITE_TRUNCATE) sobre la
    partición del día -> reintentar el mismo día es idempotente, no duplica.
    Es el único lugar donde se escriben datos; todo lo demás son vistas.

Silver  (portal_inmobiliario_silver.propiedades_limpias)
    Vista sobre Bronze: nombres de comuna legibles, UF/m² calculado, y
    columnas booleanas que *marcan* outliers en vez de descartarlos
    silenciosamente (superficie fuera de rango, dormitorios fuera de rango).

Gold  (portal_inmobiliario_gold.*)
    Vistas de consumo para Power BI, construidas sobre Silver:
      - propiedades_actuales      último snapshot por listing_id (mapa/detalle)
      - metricas_comuna           KPIs agregados por comuna/tipo/operación
      - historico_precios_comuna  serie de tiempo por comuna/operación/día

Autentica vía Application Default Credentials (ADC), sin JSON key: local corre
como tu propia cuenta (`gcloud auth application-default login`), en GitHub
Actions corre como la service account vía Workload Identity Federation.

Variables de entorno:
    GCP_PROJECT_ID
    BQ_DATASET   (ej. "portal_inmobiliario" — se le agregan los sufijos
                 _bronze / _silver / _gold para cada capa)
"""
import os
from datetime import datetime, timezone

import pandas as pd
from google.cloud import bigquery

TABLA_BRONZE = "propiedades_raw"
VISTA_SILVER = "propiedades_limpias"
VISTA_GOLD_ACTUALES = "propiedades_actuales"
VISTA_GOLD_METRICAS = "metricas_comuna"
VISTA_GOLD_HISTORICO = "historico_precios_comuna"

ESQUEMA_BRONZE = [
    bigquery.SchemaField("listing_id", "STRING"),
    bigquery.SchemaField("titulo", "STRING"),
    bigquery.SchemaField("precio_valor", "FLOAT64"),
    bigquery.SchemaField("precio_moneda", "STRING"),
    bigquery.SchemaField("operacion", "STRING"),
    bigquery.SchemaField("tipo_propiedad", "STRING"),
    bigquery.SchemaField("comuna", "STRING"),
    bigquery.SchemaField("direccion_texto", "STRING"),
    bigquery.SchemaField("barrio", "STRING"),
    bigquery.SchemaField("dormitorios", "FLOAT64"),
    bigquery.SchemaField("banos", "FLOAT64"),
    bigquery.SchemaField("superficie_util_m2", "FLOAT64"),
    bigquery.SchemaField("superficie_total_m2", "FLOAT64"),
    bigquery.SchemaField("latitud", "FLOAT64"),
    bigquery.SchemaField("longitud", "FLOAT64"),
    bigquery.SchemaField("fecha_publicacion", "DATE"),
    bigquery.SchemaField("fecha_publicacion_texto", "STRING"),
    bigquery.SchemaField("fecha_scraping", "TIMESTAMP"),
    bigquery.SchemaField("fecha_scraping_dia", "DATE"),
    bigquery.SchemaField("link", "STRING"),
]


def _cliente() -> bigquery.Client:
    return bigquery.Client(project=os.environ["GCP_PROJECT_ID"])


def _proyecto() -> str:
    return os.environ["GCP_PROJECT_ID"]


def _dataset_bronze() -> str:
    return f"{os.environ['BQ_DATASET']}_bronze"


def _dataset_silver() -> str:
    return f"{os.environ['BQ_DATASET']}_silver"


def _dataset_gold() -> str:
    return f"{os.environ['BQ_DATASET']}_gold"


def _tabla_bronze_ref() -> str:
    return f"{_proyecto()}.{_dataset_bronze()}.{TABLA_BRONZE}"


def _asegurar_dataset_y_tabla_bronze(cliente: bigquery.Client):
    cliente.create_dataset(f"{_proyecto()}.{_dataset_bronze()}", exists_ok=True)

    tabla = bigquery.Table(_tabla_bronze_ref(), schema=ESQUEMA_BRONZE)
    tabla.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY, field="fecha_scraping_dia"
    )
    cliente.create_table(tabla, exists_ok=True)


def cargar_incremental(df: pd.DataFrame) -> int:
    """Carga el DataFrame a Bronze (partición del día) y reconstruye Silver + Gold."""
    if df.empty:
        return 0

    cliente = _cliente()
    _asegurar_dataset_y_tabla_bronze(cliente)

    df = df.copy()
    dia = datetime.now(timezone.utc).date()
    df["fecha_scraping_dia"] = dia

    destino = f"{_tabla_bronze_ref()}${dia.strftime('%Y%m%d')}"
    job_config = bigquery.LoadJobConfig(
        schema=ESQUEMA_BRONZE,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = cliente.load_table_from_dataframe(df, destino, job_config=job_config)
    job.result()

    construir_capas_silver_y_gold(cliente)
    return job.output_rows


def construir_capas_silver_y_gold(cliente: bigquery.Client | None = None):
    """(Re)crea las vistas Silver y Gold sobre Bronze. Idempotente y barato —
    son solo definiciones de vista, no vuelve a mover datos."""
    cliente = cliente or _cliente()
    cliente.create_dataset(f"{_proyecto()}.{_dataset_silver()}", exists_ok=True)
    cliente.create_dataset(f"{_proyecto()}.{_dataset_gold()}", exists_ok=True)

    _crear_vista_silver(cliente)
    _crear_vista_gold_actuales(cliente)
    _crear_vista_gold_metricas(cliente)
    _crear_vista_gold_historico(cliente)


def _crear_vista_silver(cliente: bigquery.Client):
    ref = f"{_proyecto()}.{_dataset_silver()}.{VISTA_SILVER}"
    sql = f"""
    CREATE OR REPLACE VIEW `{ref}` AS
    SELECT
        *,
        CASE comuna
            WHEN 'vina-del-mar' THEN 'Viña del Mar'
            WHEN 'nunoa' THEN 'Ñuñoa'
            WHEN 'providencia' THEN 'Providencia'
            WHEN 'la-reina' THEN 'La Reina'
            ELSE comuna
        END AS comuna_nombre,
        SAFE_DIVIDE(precio_valor, NULLIF(superficie_util_m2, 0)) AS precio_uf_m2,
        (superficie_util_m2 IS NOT NULL AND (superficie_util_m2 <= 0 OR superficie_util_m2 > 1000)) AS es_outlier_superficie,
        (dormitorios IS NOT NULL AND (dormitorios < 0 OR dormitorios > 15)) AS es_outlier_dormitorios,
        (latitud IS NOT NULL AND longitud IS NOT NULL) AS tiene_coordenadas
    FROM `{_tabla_bronze_ref()}`
    WHERE listing_id IS NOT NULL
    """
    cliente.query(sql).result()


def _vista_silver_ref() -> str:
    return f"{_proyecto()}.{_dataset_silver()}.{VISTA_SILVER}"


def _crear_vista_gold_actuales(cliente: bigquery.Client):
    ref = f"{_proyecto()}.{_dataset_gold()}.{VISTA_GOLD_ACTUALES}"
    sql = f"""
    CREATE OR REPLACE VIEW `{ref}` AS
    SELECT * EXCEPT(rn) FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY listing_id ORDER BY fecha_scraping DESC) AS rn
        FROM `{_vista_silver_ref()}`
    )
    WHERE rn = 1
    """
    cliente.query(sql).result()


def _crear_vista_gold_metricas(cliente: bigquery.Client):
    ref_gold_actuales = f"{_proyecto()}.{_dataset_gold()}.{VISTA_GOLD_ACTUALES}"
    ref = f"{_proyecto()}.{_dataset_gold()}.{VISTA_GOLD_METRICAS}"
    sql = f"""
    CREATE OR REPLACE VIEW `{ref}` AS
    SELECT
        comuna,
        comuna_nombre,
        tipo_propiedad,
        operacion,
        COUNT(*) AS total_propiedades,
        ROUND(AVG(precio_valor), 0) AS precio_promedio,
        ROUND(AVG(IF(NOT es_outlier_superficie, precio_uf_m2, NULL)), 1) AS uf_m2_promedio,
        ROUND(AVG(superficie_util_m2), 0) AS superficie_promedio,
        ROUND(AVG(dormitorios), 1) AS dormitorios_promedio,
        ROUND(AVG(banos), 1) AS banos_promedio
    FROM `{ref_gold_actuales}`
    WHERE precio_moneda = 'UF'
    GROUP BY 1, 2, 3, 4
    """
    cliente.query(sql).result()


def _crear_vista_gold_historico(cliente: bigquery.Client):
    ref = f"{_proyecto()}.{_dataset_gold()}.{VISTA_GOLD_HISTORICO}"
    sql = f"""
    CREATE OR REPLACE VIEW `{ref}` AS
    SELECT
        fecha_scraping_dia,
        comuna,
        comuna_nombre,
        operacion,
        COUNT(*) AS total_propiedades,
        ROUND(AVG(precio_valor), 0) AS precio_promedio
    FROM `{_vista_silver_ref()}`
    WHERE precio_moneda = 'UF' AND NOT es_outlier_superficie
    GROUP BY 1, 2, 3, 4
    """
    cliente.query(sql).result()
