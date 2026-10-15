"""
PRUEBA 4 — Etapa 2: pronóstico condicionado por ENSO (analog/KNN), con datos
reales (histórico de reservas de la Prueba 3 + histórico RONI de NOAA).

Requiere haber corrido test_3_pipeline_completo.py antes (o al menos tener
`requests` instalado; NOAA no requiere llave/autenticación).

Correr: python test_4_enso_forecast.py
Luego abre test_reservas_condicionado.html en el navegador.
"""
import datetime as dt

from sala_control.data.reservas_xm import fetch_reservas_pct
from sala_control.data.enso_noaa import fetch_roni_historical
from sala_control.analytics.hydro_bands import compute_climatology, split_current_year_series
from sala_control.analytics.enso_analog import analog_weights, compute_conditional_bands, effective_sample_size
from sala_control.charts.reservas_chart import build_reservas_figure, add_conditional_band
from sala_control.utils import hydro_year

HISTORY_START = dt.date(2015, 1, 1)  # misma ventana que test_3; amplía si ya la ampliaste allá
today = dt.date.today()

print("1/4 — Descargando histórico de reservas (usa caché si ya corriste test_3)...")
df = fetch_reservas_pct(HISTORY_START, today)

print("2/4 — Descargando histórico RONI de NOAA...")
roni_df = fetch_roni_historical()
print(f"   {len(roni_df)} estaciones descargadas, última: "
      f"{roni_df.iloc[-1]['Season']} {int(roni_df.iloc[-1]['Year'])} = {roni_df.iloc[-1]['Anom']:.2f}")

cur_hy = hydro_year(today)
clima = compute_climatology(df, current_hydro_year=cur_hy, drought_hydro_year=2019)
split = split_current_year_series(clima["current"], today=today)

print("3/4 — Calculando pesos de años análogos...")
historical_years = sorted(df.assign(HY=df["Date"].map(hydro_year))["HY"].unique())
historical_years = [y for y in historical_years if y != cur_hy]
weights = analog_weights(roni_df, historical_years, anchor_month=today.month)

print("\n=== Años análogos (ordenados por peso) ===")
print(weights.to_string(index=False))
print(f"\nAncla actual: {weights.attrs['anchor_season']} -> "
      f"RONI={weights.attrs['anchor_value']:.2f} -> {weights.attrs['anchor_category']}")

ess = effective_sample_size(weights)
print(f"\nTamaño de muestra efectivo (ESS): {ess:.2f} de {len(weights)} años históricos disponibles.")
if ess < 4:
    print("  -> ESS bajo: la banda condicionada se parece en la práctica a solo "
          "2-3 años. Prueba ampliar HISTORY_START (más candidatos análogos) o "
          "aumentar `bandwidth` en analog_weights() (ver comparación abajo).")

# Comparación rápida con un bandwidth más ancho, para ver el trade-off
weights_wide = analog_weights(roni_df, historical_years, anchor_month=today.month, bandwidth=0.9)
ess_wide = effective_sample_size(weights_wide)
print(f"  (con bandwidth=0.9 en vez de 0.5, ESS sube a {ess_wide:.2f} — "
      f"pesos más repartidos, banda más suave, menos 'apegada' a los años top)")

cond_bands = compute_conditional_bands(df, weights)

print("\n4/4 — Generando gráfico...")
fig = build_reservas_figure(clima, split)
fig = add_conditional_band(fig, cond_bands, anchor_label=weights.attrs["anchor_category"])
fig.write_html("test_reservas_condicionado.html")

print("\nPRUEBA 4 OK: abre test_reservas_condicionado.html en tu navegador.")
print("La banda morada es la climatología CONDICIONADA al estado ENSO actual;")
print("compárala visualmente contra la banda azul (climatología incondicional de la Etapa 1).")
