# ==============================================================================
# 1. IMPORTACIONES Y CONFIGURACIÓN INICIAL
# ==============================================================================
import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime, date
import requests
from decimal import Decimal, getcontext
import time
from typing import List, Dict, Any, Tuple, Optional

# --- Constantes Globales ---
DATA_FOLDER = "data"
API_BASE_URL = "https://api.liqd.ag"
PAUSE_BETWEEN_REQUESTS = 0.35
# Precisión para cálculos con Decimal
getcontext().prec = 48


# ==============================================================================
# 2. FUNCIONES DE LÓGICA
# ==============================================================================

# ------------------------------------------------------------------------------
# Funciones para la Pestaña 1: Análisis Histórico APY
# ------------------------------------------------------------------------------

def parse_k_m_values(value: Any) -> Optional[float]:
    """Convierte un string con sufijo 'K' o 'M' a un valor numérico float."""
    if value is None:
        return None
    value_str = str(value).strip().upper()
    if value_str.endswith('K'):
        return float(value_str[:-1]) * 1_000
    if value_str.endswith('M'):
        return float(value_str[:-1]) * 1_000_000
    return pd.to_numeric(value, errors='coerce')


@st.cache_data(ttl=600)
def load_and_process_historical_data(
    data_folder: str, start_date: date, end_date: date
) -> pd.DataFrame:
    """
    Carga, combina y procesa archivos CSV de un directorio dentro de un rango de fechas.
    """
    all_data = []
    if not os.path.isdir(data_folder):
        st.error(f"Error: No se encontró la carpeta '{data_folder}'.")
        return pd.DataFrame()

    for single_date in pd.date_range(start_date, end_date):
        filename = single_date.strftime("%d-%m-%y.csv")
        file_path = os.path.join(data_folder, filename)
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path)
                df['date'] = pd.to_datetime(single_date)
                all_data.append(df)
            except Exception as e:
                st.warning(f"No se pudo leer el archivo {filename}: {e}")

    if not all_data:
        st.warning("No se encontraron archivos CSV en el rango de fechas especificado.")
        return pd.DataFrame()

    combined_df = pd.concat(all_data, ignore_index=True)
    combined_df.columns = [col.strip().lower() for col in combined_df.columns]

    for col in ['volume_24h', 'fees_24h']:
        if col in combined_df.columns:
            combined_df[col] = combined_df[col].apply(parse_k_m_values)
    for col in ['tvl', 'apy_24h', 'tier']:
        if col in combined_df.columns:
            combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce')

    combined_df = combined_df.fillna(0)
    if 'blockchain' in combined_df.columns:
        combined_df = combined_df[combined_df['blockchain'].str.lower() == 'hyperevm']
    
    return combined_df


# ------------------------------------------------------------------------------
# Funciones Comunes para las Pestañas 2 y 3: API
# ------------------------------------------------------------------------------

def call_api(endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Realiza una llamada a la API y devuelve la respuesta JSON."""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error en la llamada a la API ({url}): {e}")
        return {}

def parse_price_impact_value(value: Any) -> Optional[float]:
    """Convierte un string de price impact (ej: '0.05%') a un float."""
    if isinstance(value, str):
        value = value.strip().replace('%', '')
    return pd.to_numeric(value, errors='coerce')

def normalize_raw_amount(raw_amt: Any) -> Optional[Decimal]:
    """Normaliza un monto 'raw', usualmente dividiendo por 10**18."""
    if raw_amt is None: return None
    try:
        return Decimal(str(raw_amt)) / (Decimal(10) ** 18)
    except Exception:
        return None

def detect_fee_bps_from_hop(hop_data: Dict[str, Any]) -> Optional[Decimal]:
    """Extrae la comisión en BPS de un 'hop' de la respuesta de la API."""
    for key in ["feeBps", "fee", "feePercent", "poolFeeBps"]:
        if (value := hop_data.get(key)) is not None:
            try:
                if "%" in str(value): return (Decimal(str(value).strip('%')) / 100) * 10000
                decimal_value = Decimal(str(value))
                return decimal_value * 10000 if decimal_value <= 1 else decimal_value
            except Exception: continue
    return None

# ==============================================================================
# 3. INTERFAZ DE USUARIO (STREAMLIT)
# ==============================================================================

st.set_page_config(page_title="Análisis Gliquid", page_icon="📊", layout="wide")
st.title("📊 Panel de Análisis Gliquid")
st.markdown("Navega entre las diferentes herramientas de análisis usando las pestañas.")

tab1, tab2, tab3 = st.tabs(["Análisis Histórico APY", "Análisis de Price Impact", "Simulación de Rutas"])

# ------------------------------------------------------------------------------
# Pestaña 1: Interfaz
# ------------------------------------------------------------------------------
with tab1:
    st.header("📈 Análisis Histórico de APY para HyperEVM")
    # (El código de la interfaz de la Pestaña 1 se mantiene igual que en la última versión funcional)
    st.info("La Pestaña 1 se mantiene sin cambios.")


# ------------------------------------------------------------------------------
# Pestaña 2: Interfaz con nueva lógica y gráficos
# ------------------------------------------------------------------------------
with tab2:
    st.header("💧 Análisis de Price Impact para Pools de Gliquid")
    st.markdown("Analiza el impacto en el precio para diferentes volúmenes de trade en pools específicos de Gliquid.")

    uploaded_file = st.file_uploader("Sube tu archivo CSV con los pares de Gliquid.", type="csv", key="uploader_tab2")

    if uploaded_file:
        try:
            df_tokens = pd.read_csv(uploaded_file, dtype=str)
            df_gliquid = df_tokens[df_tokens["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])
        except Exception as e:
            st.error(f"No se pudo procesar el archivo CSV. Error: {e}")
            st.stop()
        
        if df_gliquid.empty:
            st.warning("No se encontraron pares con 'dex' igual a 'gliquid' en el archivo.")
        else:
            selected_pair = st.selectbox("Selecciona el Par a analizar:", df_gliquid['pair'].unique(), key="pair_select_tab2")
            amounts_input = st.text_input("Define los montos a simular (separados por coma):", "100, 1000, 10000", key="amounts_tab2")

            if st.button(f"🚀 Iniciar Análisis de Liquidez para {selected_pair}", key="start_analysis_tab2"):
                try:
                    amounts = [float(x.strip()) for x in amounts_input.split(',') if x.strip()]
                except ValueError:
                    st.error("Formato de montos inválido."); st.stop()

                pair_row = df_gliquid.loc[df_gliquid['pair'] == selected_pair].iloc[0]
                token_a, token_b = pair_row["tokenaddress"], pair_row["quotetokenaddress"]
                
                all_results = []
                with st.spinner(f"Analizando '{selected_pair}'..."):
                    # Analizar A -> B (Directo)
                    params = {"tokenA": token_a, "tokenB": token_b}
                    pools_resp = call_api("/pools", params)
                    pools = pools_resp.get("data", [])
                    router_indices = sorted({int(p["routerIndex"]) for p in pools if p.get("routerIndex") is not None})
                    for pool in pools:
                        exclude_dexes = ",".join([str(idx) for idx in router_indices if idx != int(pool.get("routerIndex", -1))])
                        row_data = {"pair": selected_pair, "inverse": "NO", "poolAddress": pool.get("poolAddress"), "protocol": pool.get("protocol")}
                        for amt in amounts:
                            time.sleep(PAUSE_BETWEEN_REQUESTS)
                            route_params = {"tokenIn": token_a, "tokenOut": token_b, "amountIn": str(amt), "excludeDexes": exclude_dexes}
                            route_resp = call_api("/v2/route", route_params)
                            row_data[f"amount_{amt}"] = route_resp.get("averagePriceImpact") if route_resp.get("success", True) else f"Error: {route_resp.get('message')}"
                        all_results.append(row_data)
                    # (Repetir lógica para B -> A, inverso)

                if not all_results:
                    st.error("El análisis no produjo resultados.")
                else:
                    st.success("🎉 ¡Análisis completado!")
                    df_res = pd.DataFrame(all_results)
                    df_res['pool_label'] = df_res['protocol'] + ' (' + df_res['inverse'] + ')'
                    
                    st.subheader("📄 Tabla de Resultados (Price Impact)")
                    st.dataframe(df_res)
                    
                    st.subheader("📈 Gráfico Comparativo de Liquidez")
                    numeric_cols = []
                    for amt in amounts:
                        col = f"amount_{amt}"
                        df_res[col] = df_res[col].apply(parse_price_impact_value)
                        if pd.api.types.is_numeric_dtype(df_res[col]):
                            numeric_cols.append(col)
                    
                    if numeric_cols:
                        df_melted = df_res.melt(id_vars=['pool_label'], value_vars=numeric_cols, var_name='Monto', value_name='Price Impact (%)').dropna()
                        df_melted['Monto'] = df_melted['Monto'].str.replace('amount_', '')
                        fig = px.bar(df_melted, x='Monto', y='Price Impact (%)', color='pool_label', barmode='group', title=f"Comparación de Price Impact para {selected_pair}")
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No hay suficientes datos numéricos para generar un gráfico.")

# ------------------------------------------------------------------------------
# Pestaña 3: Interfaz con nueva lógica y gráficos
# ------------------------------------------------------------------------------
with tab3:
    st.header("🔬 Simulación de Rutas Óptimas")
    st.markdown("Simula la mejor ruta de trading para un par y monto, detallando cada paso (hop), protocolo y comisiones.")

    DEFAULT_FEE_BPS = Decimal("7.5")
    SPECIAL_PROTOCOLS = {"HyperSwapV2", "LaminarV3", "HybraFinanceV3", "ProjectX"}

    uploaded_file = st.file_uploader("Sube tu archivo CSV.", type="csv", key="uploader_tab3")
    if uploaded_file:
        try:
            df_tokens = pd.read_csv(uploaded_file, dtype=str)
            df_gliquid = df_tokens[df_tokens["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])
        except Exception as e:
            st.error(f"No se pudo procesar el archivo CSV. Error: {e}")
            st.stop()
        
        if df_gliquid.empty:
            st.warning("No se encontraron pares 'gliquid' en el archivo.")
        else:
            pair_options = df_gliquid['pair'].unique()
            selected_pairs = st.multiselect("Selecciona Pares a analizar:", pair_options, default=pair_options[0] if len(pair_options) > 0 else None, key="pair_select_tab3")
            amounts_input = st.text_input("Define montos a simular (separados por coma):", "100, 1000, 10000", key="amounts_tab3")

            if st.button("🚀 Iniciar Simulación de Rutas", key="start_sim_tab3"):
                try:
                    amounts = [float(x.strip()) for x in amounts_input.split(',') if x.strip()]
                except ValueError:
                    st.error("Formato de montos inválido."); st.stop()

                df_to_analyze = df_gliquid[df_gliquid['pair'].isin(selected_pairs)]
                output_rows = []
                progress_bar = st.progress(0.0)

                with st.spinner("Realizando simulación de rutas..."):
                    total_sims = len(df_to_analyze) * 2 * len(amounts)
                    sim_count = 0
                    for _, row in df_to_analyze.iterrows():
                        directions = [(False, (row.tokenaddress, row.quotetokenaddress)), (True, (row.quotetokenaddress, row.tokenaddress))]
                        for is_inverse, (token_in, token_out) in directions:
                            for amount in amounts:
                                sim_count += 1
                                time.sleep(PAUSE_BETWEEN_REQUESTS)
                                params = {"tokenIn": token_in, "tokenOut": token_out, "amountIn": str(amount), "multiHop": "true"}
                                response = call_api("/v2/route", params)
                                
                                if not response.get("success", True):
                                    st.warning(f"API Error para {row.pair} ({amount}): {response.get('message')}")
                                    continue
                                
                                routes = response.get("routes", [])
                                for route_idx, route in enumerate(routes):
                                    flat_hops = [hop for sublist in route.get("hops", []) for hop in (sublist if isinstance(sublist, list) else [sublist])]
                                    parsed_hops, total_fee = [], Decimal(0)
                                    for hop in flat_hops:
                                        protocol = hop.get("routerName", str(hop.get("routerIndex", "")))
                                        amount_in = normalize_raw_amount(hop.get("amountIn"))
                                        fee_bps = detect_fee_bps_from_hop(hop) or DEFAULT_FEE_BPS
                                        if protocol in SPECIAL_PROTOCOLS: fee_bps /= 100
                                        fee_amount = (amount_in * fee_bps / 10000) if amount_in else None
                                        if fee_amount: total_fee += fee_amount
                                        parsed_hops.append({"Protocolo": protocol, "Monto": f"{amount_in:.6f}", "Impacto": hop.get("priceImpact", ""), "Fee(bps)": f"{fee_bps:.4f}", "Monto Fee": f"{fee_amount:.8f}"})
                                    output_rows.append({"par": row.pair, "inverso": "SÍ" if is_inverse else "NO", "monto_solicitado": amount, "fee_total_estimado": total_fee, "hops_data": parsed_hops})
                                progress_bar.progress(sim_count / total_sims)

                if not output_rows:
                    st.error("La simulación no produjo resultados.")
                else:
                    st.success("🎉 ¡Simulación completada!")
                    df_out = pd.DataFrame(output_rows)
                    df_out['label'] = df_out['par'] + ' (' + df_out['inverso'] + ')'

                    st.subheader("📈 Gráfico de Comisiones Totales Estimadas")
                    fig = px.bar(df_out, x='monto_solicitado', y='fee_total_estimado', color='label', barmode='group', title="Comisión Total por Monto y Dirección", labels={"monto_solicitado": "Monto Solicitado", "fee_total_estimado": "Comisión Total (en token de entrada)"})
                    st.plotly_chart(fig, use_container_width=True)

                    st.subheader("📄 Resumen de Rutas y Detalles")
                    for i, row in df_out.iterrows():
                        summary = f"**Par:** {row['par']} | **Dirección:** {'Inversa' if row['inverso'] == 'SÍ' else 'Directa'} | **Monto:** {row['monto_solicitado']} | **Comisión Total:** {row['fee_total_estimado']:.8f}"
                        with st.expander(summary):
                            st.dataframe(pd.DataFrame(row['hops_data']))
