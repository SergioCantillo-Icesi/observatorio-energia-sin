"""
PRUEBA 1 de 3 — Resolución de métricas contra el catálogo en vivo.

Objetivo: confirmar que pydataxm responde y que resolve_metric_id()
encuentra exactamente una métrica para el % de reservas del sistema
(PorcVoluUtilDiar), sin ambigüedad.

Correr: python test_1_catalogo.py
"""
from pydataxm.pydataxm import ReadDB
from sala_control.data.reservas_xm import resolve_metric_id, VOL_PCT_KEYWORDS

print("Conectando a la API XM y descargando catálogo de métricas...")
api = ReadDB()

print("\nColumnas del catálogo:")
print(api.inventario_metricas.columns.tolist())

print("\nResolviendo 'Volumen Útil diario % por Sistema'...")
pct_id = resolve_metric_id(api, VOL_PCT_KEYWORDS, entity="Sistema")
print("  -> MetricId encontrado:", pct_id, "(debe ser PorcVoluUtilDiar)")

print("\nPRUEBA 1 OK: si ves el MetricId arriba sin errores, continua con test_2_pull_corto.py")
