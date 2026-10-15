"""
PRUEBA 9 — Listado de recursos (Agente Generador, Tipo oficial) y cruce
con la generación por planta.

Correr: python test_9_listado_recursos.py
"""
import datetime as dt

from pydataxm.pydataxm import ReadDB
from sala_control.data.reservas_xm import resolve_metric_id
from sala_control.data.predespacho_xm import (
    LISTADO_RECURSOS_KEYWORDS, fetch_generacion_ideal_raw, adaptar_a_formato_ancho,
    fetch_listado_recursos, enriquecer_con_recursos,
)

api = ReadDB()

print("1/3 — Resolviendo el listado de recursos (Entity=Sistema, confirmado)...")
metric_id = resolve_metric_id(api, LISTADO_RECURSOS_KEYWORDS, entity="Sistema")
print(f"   MetricId encontrado: {metric_id} (esperado: ListadoRecursos)")

print("\n2/3 — Trayendo el listado...")
listado = fetch_listado_recursos(api=api)
print(f"   Filas: {len(listado)}")
print(f"   Columnas: {listado.columns.tolist()}")
print(listado.head(10).to_string(index=False))

print("\n3/3 — Cruzando con la generación de ayer...")
ayer = dt.date.today() - dt.timedelta(days=1)
crudo = fetch_generacion_ideal_raw(ayer, ayer, api=api)
ancho = adaptar_a_formato_ancho(crudo, fecha_filtro=ayer)

enriquecido = enriquecer_con_recursos(ancho, listado)
print(enriquecido.head(10).to_string(index=False))
print("\nPRUEBA 9 OK.")
