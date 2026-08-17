"""Entrypoint del scraper. Dos modos:

1. Scraping de un combo comuna/tipo/operación (usado por el job matrix de GitHub Actions,
   o localmente con --todos para correr las 16 combinaciones en secuencia). Escribe CSV(s).
2. Agregación: junta los CSVs de todos los combos, deduplica y opcionalmente sube a
   Google Sheets y/o BigQuery (usado por el job "aggregate" de GitHub Actions).

Ejemplos:
    python main.py --comuna providencia --tipo departamento --operacion venta --paginas 1
    python main.py --todos --paginas 1
    python main.py --agregar "data_*.csv" --sheets --bigquery
"""
import argparse
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from config import COMUNAS, TIPOS_PROPIEDAD, OPERACIONES, PAGINAS_POR_COMBO_DEFAULT, COLUMNAS_SALIDA
from scraper.browser import crear_driver
from scraper.pipeline import scrapear_combo


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--comuna", choices=list(COMUNAS.keys()))
    p.add_argument("--tipo", choices=TIPOS_PROPIEDAD)
    p.add_argument("--operacion", choices=OPERACIONES)
    p.add_argument("--todos", action="store_true", help="corre las 16 combinaciones en secuencia")
    p.add_argument("--paginas", type=int, default=PAGINAS_POR_COMBO_DEFAULT)
    p.add_argument("--navegador", choices=["edge", "chrome"], default="edge")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--salida", default=None, help="ruta del CSV de salida")
    p.add_argument("--agregar", default=None, help="patrón glob de CSVs a consolidar (ej. 'data_*.csv')")
    p.add_argument("--sheets", action="store_true", help="subir el resultado agregado a Google Sheets")
    p.add_argument("--bigquery", action="store_true", help="cargar el resultado agregado a BigQuery")
    return p.parse_args()


def modo_scraping(args):
    if args.todos:
        combos = [
            (nombre, slug, tipo, operacion)
            for nombre, slug in COMUNAS.items()
            for tipo in TIPOS_PROPIEDAD
            for operacion in OPERACIONES
        ]
    else:
        if not (args.comuna and args.tipo and args.operacion):
            sys.exit("Debes pasar --comuna --tipo --operacion, --todos, o --agregar")
        combos = [(args.comuna, COMUNAS[args.comuna], args.tipo, args.operacion)]

    driver = crear_driver(args.navegador, headless=args.headless)
    try:
        for comuna_nombre, comuna_slug, tipo, operacion in combos:
            print(f"\n=== {comuna_nombre} / {tipo} / {operacion} ===")
            df = scrapear_combo(driver, comuna_nombre, comuna_slug, tipo, operacion, args.paginas)
            print(f"{len(df)} propiedades")

            salida = args.salida or f"data_{comuna_nombre}_{tipo}_{operacion}.csv"
            df.to_csv(salida, index=False, encoding="utf-8-sig")
            print(f"Guardado: {salida}")
    finally:
        driver.quit()


def modo_agregar(args):
    archivos = sorted(glob.glob(args.agregar))
    if not archivos:
        sys.exit(f"No se encontraron archivos para el patrón: {args.agregar}")

    print(f"Consolidando {len(archivos)} archivo(s)...")
    df = pd.concat((pd.read_csv(f) for f in archivos), ignore_index=True)
    df = df.drop_duplicates(subset=["listing_id"])
    df = df[COLUMNAS_SALIDA]
    print(f"Total consolidado: {len(df)} propiedades únicas")

    salida = args.salida or "data_consolidado.csv"
    df.to_csv(salida, index=False, encoding="utf-8-sig")
    print(f"Guardado: {salida}")

    if args.sheets:
        from storage.sheets import upsert_propiedades
        total = upsert_propiedades(df)
        print(f"Google Sheets actualizado, total filas en hoja: {total}")

    if args.bigquery:
        from storage.bigquery import cargar_incremental
        filas = cargar_incremental(df)
        print(f"BigQuery: {filas} filas cargadas en la partición de hoy")


def main():
    args = parse_args()
    if args.agregar:
        modo_agregar(args)
    else:
        modo_scraping(args)


if __name__ == "__main__":
    main()
