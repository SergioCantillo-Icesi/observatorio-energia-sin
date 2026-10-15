"""
PRUEBA 6 — Scraper con Playwright para la tabla oficial de NOAA (reemplaza
la semilla manual por un fetch automático real).

Requiere instalar (una sola vez):
    pip install playwright
    playwright install chromium

Correr: python test_6_playwright_noaa.py

Si falla, este script YA guarda automáticamente screenshot + HTML +
diagnóstico en .cache/enso/debug/ — no hace falta que corras nada aparte
con headless=False. Solo copia y pégame la salida de consola completa
(y adjunta el screenshot si puedes).
"""
from sala_control.data.enso_scraper_playwright import scrape_strength_table
from sala_control.data.enso_noaa import _validate_strength_table

print("Abriendo Chromium y navegando a NOAA CPC (puede tardar 10-30s)...")

df = scrape_strength_table(headless=True)

if df is None:
    print("\nNO SE PUDO EXTRAER LA TABLA.")
    print("Revisa arriba el bloque '--- Diagnóstico ---': te dice cuántas tablas/gráficos "
          "encontró, si los códigos de estación (JAS, ASO, ...) aparecen como texto en la "
          "página, y dónde quedaron guardados el screenshot y el HTML renderizado "
          "(.cache/enso/debug/). Mándame esa salida completa, y si puedes, el screenshot.")
    print("\nMientras tanto, el pipeline cae automáticamente a la semilla manual "
          "(sala_control/data/enso_strength_table_seed.csv) — no se rompe nada, solo "
          "queda desactualizado hasta que la actualices a mano una vez al mes.")
else:
    print("\n¡Tabla extraída correctamente!")
    print(f"Fuente: {df['fuente'].iloc[0]}, capturada: {df['captured_on'].iloc[0]}")
    print(df[["season"] + [c for c in df.columns if c.startswith("idx_")]].to_string(index=False))
    print(f"\nValidación estructural: {_validate_strength_table(df)}")
    print("\nGuardada en caché (.cache/enso/strength_table_live.parquet) por 24h.")
    print("La próxima vez que corras load_strength_table(), la va a usar sin reabrir el navegador.")
