# Observatorio Energético SIN

App en Streamlit que consolida información del Sistema Interconectado
Nacional (SIN) colombiano — vía la API pública de XM (`pydataxm`) y NOAA —
en KPIs e insights para actores del sector energético. No requiere
credenciales: las fuentes que usa son públicas.

## Páginas

- **Riesgo Climático-Hidrológico**: evolución de reservas hídricas del SIN,
  contexto histórico y pronóstico condicionado por el fenómeno ENSO.
- **Matriz de Generación Horaria**: composición por tecnología de la
  generación horaria real por recurso.

## Correr localmente

```
pip install -r requirements.txt
streamlit run app.py
```

(La primera vez que uses el scraper de NOAA con Playwright hace falta
además `playwright install chromium` — ver `sala_control/data/enso_scraper_playwright.py`.)

## Estructura del proyecto

```
app.py                     Punto de entrada (streamlit run app.py)
sala_control/               Paquete principal
  theme.py                   Identidad visual ICESI compartida
  pages/                      Las 2 páginas de la app
  data/                        Capa de datos (XM, NOAA)
  analytics/                    Cálculos (climatología, ENSO, KPIs)
  charts/                        Construcción de gráficos Plotly
scripts/                    Scripts de diagnóstico MANUAL (no es un suite
                            de pytest automatizado) — correr con
                            `python -m scripts.<nombre>` desde la raíz,
                            ej. `python -m scripts.test_1_catalogo`.
.streamlit/config.toml      Tema base de Streamlit
```

## Desplegar

Pensada para [Streamlit Community Cloud](https://streamlit.io/cloud):
gratis, se conecta directo a un repo de GitHub y detecta `app.py` solo, sin
necesidad de credenciales ni configuración extra.

## Notas

- `sala_control_pruebas_windows.zip` en la raíz es un snapshot viejo del
  proyecto (de antes de la reorganización actual) — no se usa en ningún
  lado, se puede borrar cuando quieras confirmarlo.
- `scripts/test_7_simem_generacion.py` y `scripts/test_7b_comparar_candidatos.py`
  quedaron de un enfoque con SIMEM que se descartó (ver
  `sala_control/data/predespacho_xm.py`) — están desactualizados, se
  conservan solo como referencia histórica.
