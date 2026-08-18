"""Upsert de propiedades a una Google Sheet (hoja maestra, capa de revisión humana).

Autentica vía Application Default Credentials (ADC) — no usa un JSON key de
service account (la organización de GCP tiene bloqueada la creación de keys,
así que en su lugar: local corre como tu propia cuenta vía
`gcloud auth application-default login`; en GitHub Actions corre como la
service account vía Workload Identity Federation. En ambos casos el Sheet debe
estar compartido (Editor) con la identidad que esté autenticada.

Variable de entorno:
    GOOGLE_SHEET_ID   id de la spreadsheet (de su URL)
"""
import os

import gspread
import google.auth
import pandas as pd

from config import COLUMNAS_SALIDA

NOMBRE_HOJA = "propiedades"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _conectar():
    credenciales, _ = google.auth.default(scopes=SCOPES)
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    cliente = gspread.authorize(credenciales)
    return cliente.open_by_key(sheet_id)


def _obtener_worksheet(spreadsheet):
    try:
        return spreadsheet.worksheet(NOMBRE_HOJA)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=NOMBRE_HOJA, rows=1000, cols=len(COLUMNAS_SALIDA))
        ws.update([COLUMNAS_SALIDA])
        return ws


def upsert_propiedades(df_nuevo: pd.DataFrame) -> int:
    """Agrega listing_id nuevos y actualiza (precio, fecha_scraping, etc.) los existentes.
    Devuelve el total de filas en la hoja después del upsert."""
    if df_nuevo.empty:
        return 0

    spreadsheet = _conectar()
    ws = _obtener_worksheet(spreadsheet)

    valores_existentes = ws.get_all_values()
    if valores_existentes and valores_existentes[0] == COLUMNAS_SALIDA:
        df_actual = pd.DataFrame(valores_existentes[1:], columns=COLUMNAS_SALIDA)
    else:
        df_actual = pd.DataFrame(columns=COLUMNAS_SALIDA)

    df_nuevo = df_nuevo.astype(str)
    df_actual = df_actual.astype(str)

    combinado = pd.concat([df_actual, df_nuevo])
    combinado = combinado.drop_duplicates(subset=["listing_id"], keep="last")
    combinado = combinado.fillna("")

    ws.clear()
    ws.update([COLUMNAS_SALIDA] + combinado.values.tolist())
    return len(combinado)
