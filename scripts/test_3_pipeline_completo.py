"""
PRUEBA 3 de 3 — Pipeline completo: descarga histórica + bandas + gráfico.

Empieza con 2015 (más rápido) en vez de 2000, para no golpear el límite de
tasa de XM en la primera corrida. Cuando esto funcione, puedes ampliar
HISTORY_START a 2000-01-01 y volver a correr (el caché incremental solo
pedirá lo que falte).

Correr: python test_3_pipeline_completo.py
Luego abre test_reservas.html en el navegador (doble clic, no necesita nada más).
"""
import datetime as dt
from sala_control.data.reservas_xm import fetch_reservas_pct
from sala_control.analytics.hydro_bands import compute_climatology, split_current_year_series
from sala_control.charts.reservas_chart import build_reservas_figure
from sala_control.utils import hydro_year

HISTORY_START = dt.date(2015, 1, 1)  # amplía a 2000-01-01 una vez esto funcione

today = dt.date.today()
print(f"Descargando histórico {HISTORY_START} -> {today} (puede tardar varios minutos)...")
df = fetch_reservas_pct(HISTORY_START, today)
print(f"Filas descargadas: {len(df)}")

cur_hy = hydro_year(today)
clima = compute_climatology(df, current_hydro_year=cur_hy, drought_hydro_year=2019)
split = split_current_year_series(clima["current"], today=today)

print("\nMínimo histórico por época del año (debe acercarse a 30-35% en marzo-abril si tu ventana incluye 2020/2024):")
print(clima["bands"][["HydroDay", "Min"]].describe())

print("\nMeses cerrados del año en curso:")
print(split["closed_months"])

print("\nPunto del mes actual:")
print(split["current_point"])

fig = build_reservas_figure(clima, split)
fig.write_html("test_reservas.html")
print("\nPRUEBA 3 OK: abre test_reservas.html en tu navegador para ver el gráfico.")
