"""Upsert de propiedades a una Google Sheet (hoja maestra, capa de revisión humana).

Autentica vía Application Default Credentials (ADC) — no usa un JSON key de
service account (la organización de GCP tiene bloqueada la creación de keys).
El scope de Sheets es "sensible" y Google bloquea el consentimiento directo
para el cliente OAuth genérico de gcloud, así que localmente se impersona la
service account (variable GCP_IMPERSONATE_SERVICE_ACCOUNT) usando tu propia
identidad como fuente. En GitHub Actions corre directamente como la service
account vía Workload Identity Federation, sin necesidad de impersonar en
código (no seteés esa variable ahí). En ambos casos el Sheet debe estar
compartido (Editor) con la identidad que quede autenticada.

Variables de entorno:
    GOOGLE_SHEET_ID                    id de la spreadsheet (de su URL)
    GCP_IMPERSONATE_SERVICE_ACCOUNT    (solo local) email de la service account a impersonar
"""
import os

import gspread
import google.auth
from google.auth import impersonated_credentials
import pandas as pd

from config import COLUMNAS_SALIDA

NOMBRE_HOJA = "propiedades"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _credenciales():
    sa_a_impersonar = os.environ.get("GCP_IMPERSONATE_SERVICE_ACCOUNT")
    if sa_a_impersonar:
        base, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        return impersonated_credentials.Credentials(
            source_credentials=base,
            target_principal=sa_a_impersonar,
            target_scopes=SCOPES,
        )
    credenciales, _ = google.auth.default(scopes=SCOPES)
    return credenciales


def _conectar():
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    cliente = gspread.authorize(_credenciales())
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
