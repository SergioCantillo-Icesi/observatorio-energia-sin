"""
DIAGNÓSTICO — Ver el nombre real de las métricas de capacidad en el catálogo.

Correr: python test_1b_diagnostico.py
Pégame la salida completa.
"""
from pydataxm.pydataxm import ReadDB
from sala_control.utils import normalize

api = ReadDB()
cat = api.inventario_metricas.copy()

# Detecta la columna de nombre igual que _catalog() en reservas_xm.py
name_col = next(
    (c for c in cat.columns if normalize(c) in ("metricname", "name", "nombremetrica")),
    None,
)
entity_col = next((c for c in cat.columns if normalize(c) == "entity"), None)
id_col = next((c for c in cat.columns if normalize(c) in ("metricid", "id")), None)

print("Columna de nombre detectada:", name_col)
print("Columna de entity detectada:", entity_col)
print("Columna de id detectada:", id_col)
print()

cat["_norm"] = cat[name_col].map(normalize)

print("=== Métricas que contienen 'capacidad' ===")
sub = cat[cat["_norm"].str.contains("capacidad")]
cols = [c for c in [id_col, name_col, entity_col] if c]
print(sub[cols].drop_duplicates().to_string(index=False))

print("\n=== Métricas que contienen 'util' (para comparar cómo nombraron Volumen Útil) ===")
sub2 = cat[cat["_norm"].str.contains("util")]
print(sub2[cols].drop_duplicates().to_string(index=False))
