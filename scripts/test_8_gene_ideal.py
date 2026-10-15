"""
PRUEBA 8 — Generación Ideal por Recurso (GeneIdea) vía el catálogo
principal de pydataxm — sin SIMEM, sin credenciales.

Correr: python test_8_gene_ideal.py
"""
import datetime as dt

from pydataxm.pydataxm import ReadDB
from sala_control.data.reservas_xm import resolve_metric_id
from sala_control.data.predespacho_xm import (
    GENE_IDEAL_KEYWORDS, fetch_generacion_ideal_raw, adaptar_a_formato_ancho,
)

print("1/3 — Resolviendo la métrica GeneIdea contra el catálogo en vivo...")
api = ReadDB()
metric_id = resolve_metric_id(api, GENE_IDEAL_KEYWORDS, entity="Recurso")
print(f"   MetricId encontrado: {metric_id} (esperado: GeneIdea)")

print("\n2/3 — Trayendo un día de datos (ayer)...")
ayer = dt.date.today() - dt.timedelta(days=1)
crudo = fetch_generacion_ideal_raw(ayer, ayer, api=api)
print(f"   Filas recibidas: {len(crudo)}")
print(f"   Columnas: {crudo.columns.tolist()}")
print(crudo.head(5).to_string(index=False))

print("\n3/3 — Adaptando a formato ancho (Planta, H1..H24)...")
try:
    ancho = adaptar_a_formato_ancho(crudo, fecha_filtro=ayer)
    print(f"   {len(ancho)} recursos detectados.")
    print(ancho.head(10).to_string(index=False))
    print("\nPRUEBA 8 OK.")
except RuntimeError as e:
    print(f"\nNo se pudo adaptar automáticamente: {e}")
    print("Copia el listado de columnas de arriba y dime cuál es cuál "
          "(nombre del recurso, y el patrón de las 24 columnas horarias) "
          "— ajusto adaptar_a_formato_ancho().")
