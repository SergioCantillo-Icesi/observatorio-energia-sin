"""
pages/1_Riesgo_Climatico_Hidrologico.py

Página informativa "Riesgo Climático-Hidrológico" del Observatorio
Energético SIN. Diseñada para lectura en una sola pantalla (sin scroll):
4 KPIs de decisión arriba, gráfico de evolución + pronóstico condicionado
ENSO abajo.

Ajusta los imports de paquete (`sala_control....`) a la ruta real de tu
proyecto si difiere.
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Streamlit ejecuta este archivo con sys.path[0] = la carpeta "pages/" (no
# la raíz del proyecto), así que "import sala_control..." falla con
# ModuleNotFoundError si no se agrega la raíz a mano.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from sala_control.data.reservas_xm import fetch_reservas_pct
from sala_control.data.enso_noaa import fetch_roni_historical, load_strength_table
from sala_control.analytics.hydro_bands import compute_climatology, split_current_year_series
from sala_control.analytics.enso_analog import compute_conditional_bands_forecast
from sala_control.analytics.kpis import (
    projected_year_end_level, margin_over_historical_min,
    implied_probability_at_or_below, worst_el_nino_closing,
    recent_trend_vs_historical,
)
from sala_control.charts.reservas_chart import build_reservas_figure, add_conditional_band
from sala_control.theme import apply_icesi_theme, kpi_card_html
from sala_control.utils import hydro_year, hydro_day, fmt_pct_co

try:
    st.set_page_config(layout="wide", page_title="Riesgo Climático-Hidrológico")
except Exception:
    pass  # ya se llamó desde app.py (multipage) — no puede llamarse dos veces por corrida
apply_icesi_theme()

# El eje X del gráfico de reservas es HydroDay (entero interno 0-365, sin
# significado para el usuario — los meses del eje son solo ticktext). El
# hover unificado de Plotly ("x unified") igual muestra ese número crudo
# como encabezado arriba de las categorías; se renderiza como SVG con
# clase "legendtitletext" (Plotly reutiliza el layout de leyenda para esta
# caja). Solo se oculta en ESTA página a propósito: en la página de
# Generación por hora ese mismo encabezado sí es útil (muestra la hora).
st.markdown(
    "<style>[data-testid='stPlotlyChart'] .hoverlayer .legendtitletext "
    "{ display: none !important; } </style>",
    unsafe_allow_html=True,
)

HISTORY_START = dt.date(2000, 1, 1)  # ajusta al primer dato disponible en XM
TODAY = dt.date.today()


@st.cache_data(ttl=3600, show_spinner="Consultando SinergOX / API XM...")
def _load_reservas(history_start: dt.date, today: dt.date):
    return fetch_reservas_pct(history_start, today)


@st.cache_data(ttl=3600, show_spinner="Consultando NOAA CPC...")
def _load_enso():
    roni_df = fetch_roni_historical()
    strength_table = load_strength_table()
    return roni_df, strength_table


def render():
    st.markdown("## Riesgo Climático-Hidrológico")
    st.caption("Reservas hídricas del SIN — evolución, contexto histórico y pronóstico condicionado por ENSO")

    df = _load_reservas(HISTORY_START, TODAY)
    roni_df, strength_table = _load_enso()

    # IMPORTANTE: XM puede tener rezago de publicación — la fecha calendario
    # de "hoy" puede no tener dato todavía (por eso los KPIs salían vacíos
    # a las 11pm). Todos los cálculos usan la fecha MÁS RECIENTE con dato
    # real, no date.today() directamente.
    latest_date = df["Date"].max()
    if latest_date != TODAY:
        st.caption(f"⚠ Último dato disponible: {latest_date} (hoy es {TODAY} — XM aún no ha publicado el dato de hoy)")

    cur_hy = hydro_year(latest_date)
    clima = compute_climatology(df, current_hydro_year=cur_hy, drought_hydro_year=2019)
    split = split_current_year_series(clima["current"], today=latest_date)
    historical_years = sorted(df.assign(HY=df["Date"].map(hydro_year))["HY"].unique())
    historical_years = [y for y in historical_years if y != cur_hy]

    # --- Rango de pronóstico: desde el 1º del mes siguiente al último dato real ---
    if latest_date.month == 12:
        fcst_start_date = dt.date(latest_date.year + 1, 1, 1)
    else:
        fcst_start_date = dt.date(latest_date.year, latest_date.month + 1, 1)
    fcst_end_date = dt.date(cur_hy + 1, 11, 30)

    cond_bands = pd.DataFrame()
    if fcst_start_date <= fcst_end_date:
        hd_start, hd_end = hydro_day(fcst_start_date), hydro_day(fcst_end_date)
        cond_bands, _ = compute_conditional_bands_forecast(
            df, roni_df, strength_table, historical_years, cur_hy, hd_start, hd_end,
        )

    # ============================= 4 KPIs =============================
    k1, k2, k3, k4 = st.columns(4)

    # KPI 1 — Proyección al cierre del año hidrológico (mediana del
    # pronóstico condicionado por ENSO). Reemplaza el percentil histórico
    # (que solo contextualizaba "dónde estás hoy") por algo prospectivo:
    # hacia dónde se espera que vayan las reservas y cuánto — información
    # directamente accionable para planeación.
    proj = projected_year_end_level(df, cond_bands, cur_hy, latest_date)
    if proj is not None:
        k1.markdown(kpi_card_html(
            "📈", "Proyección al cierre (mediana ENSO)",
            f"{proj['projected']:.1f}%",
            (f"{proj['delta']:+.1f} pp vs. hoy. Nivel esperado al cierre del año hidrológico "
             f"(30-nov), según la mediana del pronóstico condicionado por ENSO, partiendo del "
             f"nivel más reciente ({fmt_pct_co(proj['current'])}). Rango de escenarios al cierre: "
             f"{fmt_pct_co(proj['p10'])} (P10) a {fmt_pct_co(proj['p90'])} (P90). "
             f"Es una proyección del modelo, no una certeza."),
        ), unsafe_allow_html=True)
    else:
        k1.markdown(kpi_card_html(
            "📈", "Proyección al cierre (mediana ENSO)", "Sin dato",
            "No hay pronóstico condicionado disponible (puede que ya estemos en el "
            "último mes del año hidrológico, sin nada más por pronosticar).",
        ), unsafe_allow_html=True)

    # KPI 2 — Margen sobre el mínimo histórico (SIEMPRE calculable, a
    # diferencia de un "días hasta cruce" que casi siempre da "sin cruce")
    margen = None
    if len(clima["bands"]):
        min_series = clima["bands"].set_index("HydroDay")["Min"]
        margen = margin_over_historical_min(df, min_series, cur_hy, latest_date)
    k2.markdown(kpi_card_html(
        "🛟", "Margen sobre mínimo histórico",
        f"{margen:+.1f} pp" if margen is not None else "Sin dato",
        ("Diferencia, en puntos porcentuales, entre el nivel más reciente y el mínimo histórico "
         "registrado para esta misma época del año hidrológico. Menor margen = más cerca del peor "
         "registro histórico = más urgente. Siempre se puede calcular (no depende de que el "
         "pronóstico proyecte cruzar ningún umbral)."
         if margen is not None else "No hay suficiente dato histórico para esta fecha."),
    ), unsafe_allow_html=True)

    # KPI 3 — Probabilidad implícita de cerrar en niveles del peor El Niño
    # histórico o peor. Reemplaza la comparación contra un año fijo
    # arbitrario ("sequía 2019-2020", que según el RONI real ni siquiera fue
    # El Niño — llegó apenas a 0.22, prácticamente Neutral) por el peor
    # cierre observado entre años que SÍ fueron El Niño: comparación
    # apples-to-apples con la condición climática que estamos viviendo ahora.
    prob_label, prob_help = "Sin dato", "No hay suficiente dato para estimarlo."
    if len(cond_bands):
        hd_end = cond_bands["HydroDay"].max()
        worst = worst_el_nino_closing(df, roni_df, historical_years, hd_end)
        band_row = cond_bands[cond_bands["HydroDay"] == hd_end]
        if worst is not None and len(band_row):
            dval = worst["value"]
            b = band_row.iloc[0]
            prob = implied_probability_at_or_below(dval, b["P10_cond"], b["P50_cond"], b["P90_cond"])
            if prob is not None:
                prob_label = f"{prob:.0%}"
            elif dval <= b["P10_cond"]:
                prob_label = "<10%"
            else:
                prob_label = ">90%"
            prob_help = (f"Compara el peor cierre histórico observado entre años que SÍ fueron El Niño "
                         f"— {worst['hydro_year']}-{worst['hydro_year']+1} ({worst['category']}, "
                         f"RONI pico {worst['peak_roni']:.2f}), que cerró en {fmt_pct_co(dval)} — contra "
                         f"la banda condicionada por ENSO para esa misma fecha (P10={fmt_pct_co(b['P10_cond'])}, "
                         f"P50={fmt_pct_co(b['P50_cond'])}, P90={fmt_pct_co(b['P90_cond'])}), interpolando en "
                         f"el espacio de cuantiles. Es una probabilidad IMPLÍCITA del modelo, no una certeza "
                         f"estadística.")
        elif worst is None:
            prob_help = ("No hay ningún año El Niño en la ventana histórica disponible — amplía "
                         "HISTORY_START para incluir más años (los 'Muy Fuerte' del registro 1950-2026 "
                         "son 1997-98 y 2015-16).")
    k3.markdown(kpi_card_html("🎲", "Prob. cierre ≤ peor El Niño histórico", prob_label, prob_help),
                unsafe_allow_html=True)

    # KPI 4 — Ritmo de recuperación reciente (30 días) vs. lo típico
    current_rate, hist_rate = recent_trend_vs_historical(df, cur_hy, latest_date)
    rate_label, rate_help = "Sin dato", "No hay suficiente dato para calcular el ritmo reciente."
    if current_rate is not None:
        rate_label = f"{current_rate:+.1f} pp/mes"
        if hist_rate is not None:
            delta = current_rate - hist_rate
            rate_help = (f"Cambio en las reservas en los últimos 30 días, anualizado a pp/mes. "
                         f"El ritmo típico histórico para esta misma época del año es "
                         f"{hist_rate:+.1f} pp/mes — hoy vas {delta:+.1f} pp/mes "
                         f"{'más rápido' if delta > 0 else 'más lento'} que lo normal. "
                         f"Señal de momentum: no depende del pronóstico ENSO, solo de datos ya observados.")
    k4.markdown(kpi_card_html("⏱️", "Ritmo de recuperación (30d) vs. típico", rate_label, rate_help),
                unsafe_allow_html=True)
    st.write("")  # separador de aire entre las tarjetas y el gráfico

    # ============================= Gráfico =============================
    fig = build_reservas_figure(clima, split)
    if len(cond_bands):
        fig = add_conditional_band(fig, cond_bands, anchor_label="pronóstico NOAA")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


render()
