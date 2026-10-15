"""
PRUEBA 7 — Fetch automático de generación por recurso vía SIMEM (API
pública, sin credenciales).

Requiere: pip install --upgrade pydataxm  (necesitas >= 0.3.14 para el
submódulo pydatasimem; si el import falla, actualiza la librería).

Correr: python test_7_simem_generacion.py

Este script es DIAGNÓSTICO primero, como hicimos con el catálogo de XM:
muestra el catálogo real de datasets de SIMEM y la forma cruda de los
datos ANTES de asumir que mis nombres de columna (en
adaptar_a_formato_ancho) son correctos. Si algo no calza, pégame la
salida completa.

NOTA sobre el bug de 'CatalogSIMEM' object has no attribute '_filters':
es un bug conocido de la librería (no de este código). catalogo_datasets()
ya intenta 3 niveles en cascada: normal -> parche de clase -> REST directo.
Si los 3 fallan, el último recurso es 100% manual: entra a
https://www.simem.co, busca "Predespacho Ideal" en el catálogo de datos
desde el navegador, y copia el ID de 6 caracteres que aparece ahí (o en la
URL de la página de detalle del dataset) — pásalo directo a
fetch_generacion_simem() como si fuera el resultado de resolve_dataset_id().
"""
import datetime as dt

from sala_control.data.predespacho_xm import (
    catalogo_datasets, catalogo_datasets_rest, resolve_dataset_id,
    fetch_generacion_simem, adaptar_a_formato_ancho,
)

print("1/4 — Descargando catálogo de datasets de SIMEM...")
try:
    catalogo = catalogo_datasets()
    print(f"   OK (camino normal o con parche). {len(catalogo)} datasets.")
except Exception as e:
    print(f"   Camino normal falló del todo: {e}")
    print("   Probando REST directo...")
    catalogo = catalogo_datasets_rest()
    print(f"   OK (REST directo). {len(catalogo)} datasets.")
print(f"   Columnas: {catalogo.columns.tolist()}")

print("\n2/4 — Buscando datasets relacionados con 'predespacho'...")
relacionados = catalogo[catalogo.apply(lambda r: "predespacho" in str(r).lower(), axis=1)]
print(relacionados.to_string(index=False))
if len(relacionados) == 0:
    print("   (nada con 'predespacho' literal — probando 'despacho' más amplio, por si el "
          "catálogo lo nombra distinto, ej. 'Despacho Programado')")
    relacionados_amplio = catalogo[catalogo.apply(lambda r: "despacho" in str(r).lower(), axis=1)]
    print(relacionados_amplio.to_string(index=False))

print("\n3/4 — Resolviendo dataset de Predespacho Ideal...")
try:
    ds_id = resolve_dataset_id(["predespacho"], catalogo=catalogo)
    print(f"   MetricId/datasetId encontrado: {ds_id}")
except RuntimeError as e:
    print(f"   {e}")
    print("   Revisa la tabla del paso 2 y ajusta la keyword si el nombre real es distinto "
          "(ej. 'Despacho Programado', 'Predespacho de Generación', etc.).")
    raise SystemExit(1)

print("\n4/4 — Trayendo un día de datos (ayer)...")
ayer = dt.date.today() - dt.timedelta(days=1)
crudo = fetch_generacion_simem(ayer, ayer, keywords=["predespacho"])
print(f"   Filas recibidas: {len(crudo)}")
print(f"   Columnas: {crudo.columns.tolist()}")
print(crudo.head(10).to_string(index=False))

print("\nIntentando adaptar a formato ancho (Planta, H1..H24)...")
try:
    ancho = adaptar_a_formato_ancho(crudo, fecha_filtro=ayer)
    print(ancho.head().to_string(index=False))
    print(f"\nPRUEBA 7 OK: {len(ancho)} recursos, formato ancho correcto.")
except RuntimeError as e:
    print(f"\nNo se pudo autodetectar columnas: {e}")
    print("Copia el listado de columnas de arriba y dime cuál es cuál "
          "(planta/recurso, hora, fecha, valor) — ajusto adaptar_a_formato_ancho().")
