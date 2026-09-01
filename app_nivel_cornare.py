"""
App de Streamlit — Nivel de ríos/quebradas (CORNARE / MARCO)
--------------------------------------------------------------
Versión con carga AUTOMÁTICA del código 31.
Sin botón de consulta, se carga apenas abres la app.

Para correrla:
    streamlit run app_nivel_cornare_auto.py
"""

import requests
import pandas as pd
import numpy as np
import streamlit as st
import urllib3
from datetime import datetime, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ------------------------------------------------------------------
# Coordenadas por defecto (Institución Universitaria Pascual Bravo)
# ------------------------------------------------------------------
LAT_DEFECTO = 6.2766
LON_DEFECTO = -75.5901

API_BASE_URL = "https://marco.cornare.gov.co/api/v1/estaciones"

LLAVE_FECHA = "level_date"
LLAVE_VALOR = "level"
CANDIDATOS_LAT = ["lat", "latitude", "latitud"]
CANDIDATOS_LON = ["lng", "lon", "longitude", "longitud"]

st.set_page_config(page_title="Nivel de estación — CORNARE", page_icon="🌊", layout="wide")


# ------------------------------------------------------------------
# Funciones de consulta
# ------------------------------------------------------------------
@st.cache_data(ttl=600)  # Cache por 10 minutos
def obtener_serie_nivel(codigo_estacion, desde, hasta, calidad=1, timeout=30):
    url = f"{API_BASE_URL}/{codigo_estacion}/nivel"
    params = {"desde": desde, "hasta": hasta, "calidad": calidad}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout, verify=False)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"HTTP {resp.status_code}"
    except requests.exceptions.RequestException as e:
        return None, f"Error de red: {e}"


def obtener_todas_las_paginas(datos_json, timeout=30):
    registros = list(datos_json.get("values", []))
    siguiente_url = datos_json.get("next")
    while siguiente_url:
        try:
            resp = requests.get(siguiente_url, timeout=timeout, verify=False)
        except requests.exceptions.RequestException:
            break
        if resp.status_code != 200:
            break
        pagina = resp.json()
        registros.extend(pagina.get("values", []))
        siguiente_url = pagina.get("next")
    return registros


def detectar_coordenadas(datos_json):
    """Busca lat/lon en las llaves raíz de la respuesta."""
    if not isinstance(datos_json, dict):
        return LAT_DEFECTO, LON_DEFECTO, False

    lat = next((datos_json[k] for k in CANDIDATOS_LAT if k in datos_json), None)
    lon = next((datos_json[k] for k in CANDIDATOS_LON if k in datos_json), None)

    if lat is not None and lon is not None:
        try:
            return float(lat), float(lon), True
        except (TypeError, ValueError):
            pass
    return LAT_DEFECTO, LON_DEFECTO, False


def calcular_indice_calidad(df):
    """Índice simple (0-100) combinando completitud de la serie y proporción de outliers."""
    if df.empty or len(df) < 2:
        return 0.0, 0, 0

    df_idx = df.set_index("fecha")
    frecuencia_tipica = df["fecha"].diff().dropna().mode()
    if len(frecuencia_tipica) == 0:
        return 0.0, 0, 0
    frecuencia_tipica = frecuencia_tipica[0]

    rango_completo = pd.date_range(start=df_idx.index.min(), end=df_idx.index.max(), freq=frecuencia_tipica)
    esperados = len(rango_completo)
    huecos = esperados - len(df_idx)
    completitud = max(0.0, 1 - (huecos / esperados)) if esperados > 0 else 0.0

    Q1, Q3 = df["nivel"].quantile(0.25), df["nivel"].quantile(0.75)
    IQR = Q3 - Q1
    lim_inf, lim_sup = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
    es_outlier = (df["nivel"] < lim_inf) | (df["nivel"] > lim_sup) | (df["nivel"] < 0)
    proporcion_outliers = es_outlier.mean()

    indice = (completitud * 0.7 + (1 - proporcion_outliers) * 0.3) * 100
    return round(indice, 1), int(huecos), int(es_outlier.sum())


# ------------------------------------------------------------------
# INTERFAZ PRINCIPAL
# ------------------------------------------------------------------

st.title("🌊 Nivel de ríos y quebradas — CORNARE")

# --- Sidebar ---
st.sidebar.header("📍 Estación 31")
st.sidebar.success("✓ Código de estación: **31** (cargada automáticamente)")

# Entrada del nombre del estudiante
nombre_estudiante = st.sidebar.text_input("Nombre del estudiante", "Tu Nombre Aquí")

# Rango de fechas (editable)
col_desde, col_hasta = st.sidebar.columns(2)
with col_desde:
    fecha_desde = st.date_input("Desde", pd.to_datetime("2026-08-23"))
with col_hasta:
    fecha_hasta = st.date_input("Hasta", pd.to_datetime("2026-08-30"))

# Calidad
calidad = st.sidebar.selectbox("Calidad de datos", [1, 0], format_func=lambda x: "Solo validados" if x == 1 else "Todos", index=0)

# Botón para refrescar (opcional)
refrescar = st.sidebar.button("🔄 Refrescar datos", type="secondary", use_container_width=True)

# Checkbox para geoportal
st.sidebar.markdown("---")
ver_geoportal = st.sidebar.checkbox("📡 Ver geoportal MARCO", value=False)

st.caption(f"Estudiante: **{nombre_estudiante}** · Estación: **31**")

# ------------------------------------------------------------------
# Carga automática de datos
# ------------------------------------------------------------------
codigo_estacion = "31"
fecha_desde_str = fecha_desde.strftime("%Y-%m-%d")
fecha_hasta_str = fecha_hasta.strftime("%Y-%m-%d")

with st.spinner("Cargando datos de la estación 31..."):
    datos_crudos, error = obtener_serie_nivel(codigo_estacion, fecha_desde_str, fecha_hasta_str, calidad)

if error:
    st.error(f"❌ Error al consultar: {error}")
    st.stop()
else:
    registros = obtener_todas_las_paginas(datos_crudos)

    if not registros:
        st.warning("⚠️ No hay registros para este rango de fechas. Prueba ampliar el período.")
    else:
        # Procesar datos
        df = pd.DataFrame(registros)
        df = df.rename(columns={LLAVE_FECHA: "fecha", LLAVE_VALOR: "nivel"})
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df["nivel"] = pd.to_numeric(df["nivel"], errors="coerce")
        df = df.dropna(subset=["fecha", "nivel"]).sort_values("fecha").reset_index(drop=True)

        lat, lon, coords_reales = detectar_coordenadas(datos_crudos)
        indice_calidad, huecos, n_outliers = calcular_indice_calidad(df)

        # --- Métricas principales ---
        st.subheader("📊 Estadísticas")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total de lecturas", len(df))
        with col2:
            st.metric("Nivel promedio", f"{df['nivel'].mean():.2f}")
        with col3:
            st.metric("Nivel máximo", f"{df['nivel'].max():.2f}")
        with col4:
            st.metric("Nivel mínimo", f"{df['nivel'].min():.2f}")

        # --- Gráfico de la serie ---
        st.subheader("📈 Serie temporal de nivel")
        st.line_chart(df.set_index("fecha")["nivel"], use_container_width=True)

        # --- Dos columnas: mapa + métricas de calidad ---
        col_map, col_quality = st.columns([1, 1])

        with col_map:
            st.subheader("📍 Ubicación")
            if not coords_reales:
                st.caption("📌 Punto de referencia (Pascual Bravo)")
            st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}), zoom=10)

        with col_quality:
            st.subheader("✅ Calidad de datos")
            st.metric("Índice de calidad", f"{indice_calidad} / 100")
            st.write(f"📊 Huecos detectados: **{huecos}**")
            st.write(f"⚠️ Outliers: **{n_outliers}** de {len(df)}")

        # --- Detalle expandible ---
        with st.expander("Ver metodología del índice de calidad"):
            st.write("""
            El **índice de calidad** (0-100) mide dos aspectos:
            - **Completitud (70%):** Proporción de fechas esperadas vs. registros reales
            - **Validez (30%):** Proporción de valores sin outliers (método IQR + niveles negativos)
            
            Un índice cercano a 100 indica datos completos y confiables.
            """)

        # --- Tabla de datos ---
        with st.expander("Ver tabla de datos crudos"):
            st.dataframe(df, use_container_width=True, height=400)

        # --- Descarga ---
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar como CSV",
            csv,
            file_name="nivel_estacion_31.csv",
            mime="text/csv",
            use_container_width=True
        )


# ------------------------------------------------------------------
# Geoportal MARCO (opcional)
# ------------------------------------------------------------------
if ver_geoportal:
    st.markdown("---")
    st.subheader("🗺️ Geoportal MARCO - Cornare")
    st.components.v1.iframe(
        src="https://marco.cornare.gov.co/geoportal/31",
        height=700,
        scrolling=True
    )
    st.caption("Fuente: [MARCO - Cornare Estación 31](https://marco.cornare.gov.co/geoportal/31)")
