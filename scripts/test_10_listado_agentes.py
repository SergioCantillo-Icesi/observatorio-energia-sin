"""
PRUEBA 10 — Listado de agentes (nombre completo de la empresa).

Correr: python test_10_listado_agentes.py
"""
from pydataxm.pydataxm import ReadDB
from sala_control.data.reservas_xm import resolve_metric_id, _catalog
from sala_control.data.predespacho_xm import (
    LISTADO_AGENTES_KEYWORDS, fetch_listado_agentes, nombres_de_agentes,
)

api = ReadDB()

print("1/2 — Resolviendo el listado de agentes...")
try:
    metric_id = resolve_metric_id(api, LISTADO_AGENTES_KEYWORDS, entity="Sistema")
    print(f"   MetricId encontrado: {metric_id}")
except RuntimeError as e:
    print(f"   {e}")
    print("   Buscando candidatos más amplios ('agente' en el nombre, cualquier entity)...")
    cat = _catalog(api)
    candidatos = cat[cat["_name_norm"].str.contains("agente")]
    print(candidatos[["MetricId", "MetricName", "Entity"]].drop_duplicates().to_string(index=False))
    raise SystemExit(1)

print("\n2/2 — Trayendo el listado...")
listado = fetch_listado_agentes(api=api)
print(f"   Filas: {len(listado)}")
print(f"   Columnas: {listado.columns.tolist()}")
print(listado.head(10).to_string(index=False))

print("\nProbando nombres_de_agentes()...")
try:
    nombres = nombres_de_agentes(listado)
    print(nombres.head(10).to_string(index=False))
    print("\nPRUEBA 10 OK.")
except RuntimeError as e:
    print(f"\nNo se pudo reducir automáticamente: {e}")
    print("Copia las columnas de arriba y dime cuál es el código y cuál el nombre "
          "— ajusto nombres_de_agentes().")
