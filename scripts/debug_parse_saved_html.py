"""
DIAGNÓSTICO OFFLINE — inspecciona el HTML que ya guardaste en
.cache/enso/debug/ para ver exactamente por qué ninguna de las 10 tablas
pasó la validación. No necesita red — corre 100% sobre el archivo local.

Correr: python debug_parse_saved_html.py
(Si tienes varios archivos page_*.html en .cache/enso/debug/, toma el más
reciente automáticamente.)
"""
import glob
from io import StringIO
from pathlib import Path

import pandas as pd

from sala_control.data.enso_noaa import _extract_season_code, N_SEASONS_IN_TABLE

candidates = sorted(glob.glob(".cache/enso/debug/page_*.html"))
if not candidates:
    raise SystemExit("No encontré ningún .cache/enso/debug/page_*.html. "
                      "Corre test_6_playwright_noaa.py primero.")

html_path = candidates[-1]
print(f"Analizando: {html_path}\n")
html = Path(html_path).read_text(encoding="utf-8")

tables = pd.read_html(StringIO(html))
print(f"pandas.read_html encontró {len(tables)} tablas.\n")

for i, t in enumerate(tables):
    print(f"=== Tabla #{i} — shape={t.shape} ===")
    print("Columnas:", list(t.columns))
    first_col = t.columns[0]
    print(f"Primera columna ('{first_col}') valores (repr(), para ver espacios/caracteres ocultos):")
    print([repr(v) for v in t[first_col].tolist()])

    # Usa la MISMA extracción tolerante (regex con límites de palabra) que
    # parse_strength_html en producción — no la comparación exacta vieja,
    # que da falsos negativos con formatos tipo "JAS Jul Aug Sep".
    extracted = t[first_col].map(_extract_season_code)
    found = extracted.dropna().unique().tolist()
    print(f"Códigos de estación detectados (extracción tolerante): {found} "
          f"({len(found)}/{N_SEASONS_IN_TABLE})")
    print()
