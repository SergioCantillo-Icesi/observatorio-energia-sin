"""
PRUEBA 5 — Etapa 2 (v2): pronóstico condicionado por ENSO usando la tabla
oficial de probabilidades de fuerza (9 estaciones), no solo el último RONI
observado. El condicional ahora arranca justo después del mes actual.

Requiere test_3 corrido antes (para tener el histórico de reservas en caché).

Correr: python test_5_enso_forecast_conditioned.py
Luego abre test_reservas_condicionado.html en el navegador.
"""
import datetime as dt

from sala_control.data.reservas_xm import fetch_reservas_pct
from sala_control.data.enso_noaa import fetch_roni_historical, load_strength_table
from sala_control.analytics.hydro_bands import compute_climatology, split_current_year_series
from sala_control.analytics.enso_analog import (
    compute_conditional_bands_forecast, effective_sample_size,
)
from sala_control.charts.reservas_chart import build_reservas_figure, add_conditional_band
from sala_control.utils import hydro_year, hydro_day

HISTORY_START = dt.date(2000, 1, 1)  # amplía si quieres más candidatos análogos
today = dt.date.today()

print("1/4 — Descargando histórico de reservas (usa caché si ya corriste test_3)...")
df = fetch_reservas_pct(HISTORY_START, today)

print("2/4 — Descargando RONI histórico + tabla de probabilidades de fuerza...")
roni_df = fetch_roni_historical()
strength_table = load_strength_table(prefer_live=True)  # intenta en vivo, si falla usa la semilla
print(f"   Fuente de la tabla de fuerza: {strength_table['fuente'].iloc[0]}")
print(strength_table[["season"] + [c for c in strength_table.columns if c.startswith("idx_")]].to_string(index=False))

cur_hy = hydro_year(today)
clima = compute_climatology(df, current_hydro_year=cur_hy, drought_hydro_year=2019)
split = split_current_year_series(clima["current"], today=today)

historical_years = sorted(df.assign(HY=df["Date"].map(hydro_year))["HY"].unique())
historical_years = [y for y in historical_years if y != cur_hy]

if today.month == 12:
    fcst_start = dt.date(today.year + 1, 1, 1)
else:
    fcst_start = dt.date(today.year, today.month + 1, 1)
fcst_end = dt.date(cur_hy + 1, 11, 30)
print(f"\n3/4 — Rango de pronóstico: {fcst_start} -> {fcst_end} (justo después del mes actual)")

if fcst_start > fcst_end:
    print("No queda ningún mes por pronosticar dentro del año hidrológico actual.")
else:
    hd_start, hd_end = hydro_day(fcst_start), hydro_day(fcst_end)
    cond_bands, weights_by_month = compute_conditional_bands_forecast(
        df, roni_df, strength_table, historical_years, cur_hy, hd_start, hd_end,
    )

    print("\n=== Diagnóstico por mes ===")
    for month, w in weights_by_month.items():
        top = w.iloc[0]
        print(f"  Mes {month:>2} ({w.attrs['season']}): ESS={effective_sample_size(w):.2f}/{len(w)} años | "
              f"top análogo = {int(top['HydroYear'])}-{int(top['HydroYear'])+1} "
              f"({top['CategoriaAnalogo']}, peso {top['Peso']:.0%})")

    print("\n4/4 — Generando gráfico...")
    fig = build_reservas_figure(clima, split)
    fig = add_conditional_band(fig, cond_bands, anchor_label="pronóstico NOAA")
    fig.write_html("test_reservas_condicionado.html")
    print("\nPRUEBA 5 OK: abre test_reservas_condicionado.html")
    print("La banda morada ahora debe empezar en septiembre, no antes.")
