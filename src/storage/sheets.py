"""Upsert de propiedades a una Google Sheet (hoja maestra, capa de revisión humana).

Requiere una service account de Google Cloud con la Sheets API habilitada y con
el Sheet destino compartido con su email (permiso Editor). Variables de entorno:
    GOOGLE_APPLICATION_CREDENTIALS  ruta al JSON de la service account
    GOOGLE_SHEET_ID                 id de la spreadsheet (de su URL)
"""
import os

import gspread
import pandas as pd

from config import COLUMNAS_SALIDA

NOMBRE_HOJA = "propiedades"


def _conectar():
    ruta_creds = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    sheet_id = os.environ["GOOGLE_SHEET_ID"]
    cliente = gspread.service_account(filename=ruta_creds)
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
