"""
PRUEBA 8b — Diagnóstico de por qué GeneIdea vino vacío para "ayer".

Prueba 3 hipótesis por separado:
  A) Rango más amplio (últimos 30 días) — ¿hay AL MENOS un día con datos?
  B) Filtro explícito con códigos de recurso conocidos (GVIO=Guavio,
     TBST=Termosierra... ajusta si no son los códigos reales) — algunas
     métricas 'por Recurso' de XM devuelven vacío sin filtro.
  C) Una fecha bastante más vieja (hace 6 meses) — descarta problemas de
     publicación reciente.

Correr: python test_8b_diagnostico_vacio.py
"""
import datetime as dt

from pydataxm.pydataxm import ReadDB
from sala_control.data.reservas_xm import resolve_metric_id
from sala_control.data.predespacho_xm import GENE_IDEAL_KEYWORDS

api = ReadDB()
metric_id = resolve_metric_id(api, GENE_IDEAL_KEYWORDS, entity="Recurso")
print(f"MetricId: {metric_id}\n")

hoy = dt.date.today()

print("=== A) Últimos 30 días, sin filtro ===")
df_a = api.request_data(metric_id, "Recurso", hoy - dt.timedelta(days=30), hoy - dt.timedelta(days=1))
print(f"Filas: {len(df_a)}")
if len(df_a):
    print(f"Columnas: {df_a.columns.tolist()}")
    print(df_a.head(3).to_string(index=False))
    date_col = next((c for c in df_a.columns if c.lower() == "date"), None)
    if date_col:
        print(f"\nFechas con datos: {sorted(df_a[date_col].dt.date.unique())}")

print("\n=== B) Con filtro explícito (GVIO, TBST), ayer ===")
ayer = hoy - dt.timedelta(days=1)
df_b = api.request_data(metric_id, "Recurso", ayer, ayer, filtros=["GVIO", "TBST"])
print(f"Filas: {len(df_b)}")
if len(df_b):
    print(f"Columnas: {df_b.columns.tolist()}")
    print(df_b.head(3).to_string(index=False))

print("\n=== C) Fecha antigua (hace 6 meses), sin filtro ===")
vieja = hoy - dt.timedelta(days=180)
df_c = api.request_data(metric_id, "Recurso", vieja, vieja)
print(f"Filas: {len(df_c)}")
if len(df_c):
    print(f"Columnas: {df_c.columns.tolist()}")
    print(df_c.head(3).to_string(index=False))

print("\n=== RESUMEN ===")
print(f"A) Últimos 30 días sin filtro: {len(df_a)} filas")
print(f"B) Ayer CON filtro (GVIO,TBST): {len(df_b)} filas")
print(f"C) Hace 6 meses sin filtro: {len(df_c)} filas")
print("\nSi B trae datos y A/C no: la métrica necesita filtro explícito.")
print("Si C trae datos y A no: es rezago de publicación reciente, no falta el filtro.")
print("Si ninguno trae datos: puede que 'GeneIdea' no sea la métrica correcta pese al "
      "nombre, o que XM cambió cómo se consulta esto. Copié la métrica desde el catálogo "
      "que tú mismo revisaste, así que el nombre debería ser correcto — el problema estaría "
      "en algo más específico de la consulta.")
