"""Carga incremental a BigQuery: tabla nativa particionada por día de scraping + vista
con el último snapshot por propiedad (fuente para Power BI).

Cada corrida escribe (WRITE_TRUNCATE) sobre la partición del día -> reintentar el mismo
día es idempotente, no duplica filas. El histórico completo queda en la tabla para
análisis de tendencia de precios.

Autentica vía Application Default Credentials (ADC), sin JSON key: local corre
como tu propia cuenta (`gcloud auth application-default login`), en GitHub
Actions corre como la service account vía Workload Identity Federation.

Variables de entorno:
    GCP_PROJECT_ID
    BQ_DATASET   (ej. "portal_inmobiliario")
"""
import os
from datetime import datetime, timezone

import pandas as pd
from google.cloud import bigquery

TABLA_RAW = "propiedades_raw"
VISTA_ACTUAL = "vw_propiedades_actual"

ESQUEMA = [
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


def _tabla_ref() -> str:
    return f"{os.environ['GCP_PROJECT_ID']}.{os.environ['BQ_DATASET']}.{TABLA_RAW}"


def _asegurar_dataset_y_tabla(cliente: bigquery.Client):
    dataset_id = f"{os.environ['GCP_PROJECT_ID']}.{os.environ['BQ_DATASET']}"
    cliente.create_dataset(dataset_id, exists_ok=True)

    tabla = bigquery.Table(_tabla_ref(), schema=ESQUEMA)
    tabla.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY, field="fecha_scraping_dia"
    )
    cliente.create_table(tabla, exists_ok=True)


def cargar_incremental(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    cliente = _cliente()
    _asegurar_dataset_y_tabla(cliente)

    df = df.copy()
    dia = datetime.now(timezone.utc).date()
    df["fecha_scraping_dia"] = dia

    destino = f"{_tabla_ref()}${dia.strftime('%Y%m%d')}"
    job_config = bigquery.LoadJobConfig(
        schema=ESQUEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = cliente.load_table_from_dataframe(df, destino, job_config=job_config)
    job.result()

    _actualizar_vista_actual(cliente)
    return job.output_rows


def _actualizar_vista_actual(cliente: bigquery.Client):
    vista_ref = f"{os.environ['GCP_PROJECT_ID']}.{os.environ['BQ_DATASET']}.{VISTA_ACTUAL}"
    sql = f"""
    CREATE OR REPLACE VIEW `{vista_ref}` AS
    SELECT * EXCEPT(rn) FROM (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY listing_id ORDER BY fecha_scraping DESC) AS rn
        FROM `{_tabla_ref()}`
    )
    WHERE rn = 1
    """
    cliente.query(sql).result()
