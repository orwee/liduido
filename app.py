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
import numpy as np
import re

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
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Carga, combina y procesa archivos CSV de un directorio dentro de un rango de fechas.
    """
    all_data = []
    loaded_files = []

    if not os.path.isdir(data_folder):
        st.error(f"Error: No se encontró la carpeta '{data_folder}'.")
        return pd.DataFrame(), []

    for single_date in pd.date_range(start_date, end_date):
        filename = single_date.strftime("%d-%m-%y.csv")
        file_path = os.path.join(data_folder, filename)
        if os.path.exists(file_path):
            try:
                df = pd.read_csv(file_path)
                df['date'] = pd.to_datetime(single_date)
                all_data.append(df)
                loaded_files.append(filename)
            except Exception as e:
                st.warning(f"No se pudo leer el archivo {filename}: {e}")

    if not all_data:
        return pd.DataFrame(), []

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
    
    return combined_df, loaded_files


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

def compute_amount_pct_routes(df):
    """Calcula y añade columnas con el porcentaje de volumen por cada hop de la ruta."""
    if 'amount_requested' not in df.columns: return df
    
    df['amount_requested_num'] = pd.to_numeric(df['amount_requested'], errors='coerce')
    route_cols = sorted([c for c in df.columns if re.match(r'^amount_route_(\d+)$', c)])

    for col in route_cols:
        n = col.split('_')[-1]
        pct_col = f'amount_pct_route_{n}'
        df[col + '_num'] = pd.to_numeric(df[col], errors='coerce')
        
        denom = df['amount_requested_num']
        valid_denom = denom.notna() & (denom != 0)
        
        df[pct_col] = np.nan
        df.loc[valid_denom, pct_col] = (df.loc[valid_denom, col + '_num'] / denom[valid_denom]) * 100
    
    df.drop(columns=[c for c in df.columns if c.endswith('_num')], inplace=True, errors='ignore')
    return df

def is_amount_close(requested_str, routed_str):
    """Compara si el monto ruteado está dentro de una tolerancia del solicitado."""
    try:
        requested = Decimal(str(requested_str))
        routed = Decimal(str(routed_str))
        if requested == 0: return False
        tolerance = requested * Decimal('0.001') # 0.1%
        return (requested - tolerance) <= routed <= (requested + tolerance)
    except:
        return False

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
    st.markdown("Carga datos históricos, filtra por blockchain y permite analizar el APY por par, incluyendo una simulación dinámica.")

    # --- Controles del Usuario ---
    st.subheader("1. Configuración de Datos y Simulación")
    
    available_dates = [datetime(2025, 8, i).date() for i in range(10, 17)] # Fechas de ejemplo
    
    col1, col2 = st.columns(2)
    with col1:
        start_date_input = st.date_input("Fecha de inicio", available_dates[0])
    with col2:
        end_date_input = st.date_input("Fecha de fin", available_dates[-1])

    simulated_tier = st.slider(
        "Selecciona el Fee Tier para la simulación de 'gliquid_test':",
        min_value=0.01, max_value=5.0, value=1.0, step=0.05, format="%.2f%%"
    )

    # --- Carga y Procesamiento de Datos ---
    historical_df, loaded_files = load_and_process_historical_data(DATA_FOLDER, start_date_input, end_date_input)

    if loaded_files:
        with st.expander("Ver archivos cargados"):
            st.write(loaded_files)

    if not historical_df.empty:
        required_columns = ['dex', 'volume_24h', 'tvl', 'apy_24h', 'pair']
        if not all(col in historical_df.columns for col in required_columns):
            st.error(f"Error: Faltan columnas esenciales en los CSVs. Se necesitan: {', '.join(required_columns)}")
        else:
            st.subheader("2. Análisis y Comparativa")
            all_pairs = sorted(historical_df['pair'].str.lower().unique())
            selected_pairs = st.multiselect("Selecciona los Pairs a visualizar:", options=all_pairs, default=all_pairs[0] if all_pairs else [])

            if selected_pairs:
                filtered_df = historical_df[historical_df['pair'].str.lower().isin(selected_pairs)].copy()
                gliquid_df = filtered_df[filtered_df['dex'].str.lower() == 'gliquid'].copy()
                other_dex_df = filtered_df[filtered_df['dex'].str.lower() != 'gliquid'].copy()

                best_gliquid_df = pd.DataFrame()
                if not gliquid_df.empty:
                    best_gliquid_df = gliquid_df.loc[gliquid_df.groupby(['date', 'pair'])['apy_24h'].idxmax()].copy()
                    best_gliquid_df['dex'] = 'gliquid (best)'

                simulation_rows = []
                if not best_gliquid_df.empty:
                    sim_df = best_gliquid_df.copy()
                    sim_df['apy_24h'] = sim_df.apply(lambda row: ((row['volume_24h'] * (simulated_tier / 100)) / row['tvl'] * 365 * 100) if row['tvl'] > 0 else 0, axis=1)
                    sim_df['dex'] = 'gliquid_test'
                    sim_df['tier'] = simulated_tier
                    simulation_rows = sim_df.to_dict('records')

                chart_df = pd.concat([other_dex_df, best_gliquid_df, pd.DataFrame(simulation_rows)], ignore_index=True)
                chart_df['identifier'] = chart_df.apply(lambda row: f"{row['pair']} ({row['dex']}, Tier: {row.get('tier', 0):.2f}%)", axis=1)

                if st.checkbox("Mostrar tabla de datos del gráfico", value=True):
                    st.dataframe(chart_df[['date', 'pair', 'dex', 'tier', 'tvl', 'volume_24h', 'apy_24h']].sort_values(by=['date', 'pair']))

                fig = px.line(chart_df, x='date', y='apy_24h', color='identifier', title="Evolución Histórica del APY por Par", labels={'date': 'Fecha', 'apy_24h': 'APY 24h (%)', 'identifier': 'Pool'}, markers=True)
                st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# Pestaña 2: Interfaz
# ------------------------------------------------------------------------------
with tab2:
    st.header("💧 Análisis de Price Impact para Pools de Gliquid")
    st.markdown("Analiza el impacto en el precio para diferentes volúmenes de trade en pools específicos de Gliquid.")

    uploaded_file_tab2 = st.file_uploader("Sube tu archivo CSV con los pares de Gliquid.", type="csv", key="uploader_tab2")

    if uploaded_file_tab2:
        try:
            df_tokens = pd.read_csv(uploaded_file_tab2, dtype=str)
            df_gliquid = df_tokens[df_tokens["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])
        except Exception as e:
            st.error(f"No se pudo procesar el archivo CSV: {e}"); st.stop()
        
        if df_gliquid.empty:
            st.warning("No se encontraron pares con 'dex' igual a 'gliquid' en el archivo.")
        else:
            selected_pair = st.selectbox("Selecciona el Par a analizar:", df_gliquid['pair'].unique(), key="pair_select_tab2")
            amounts_input = st.text_input("Define montos (separados por coma):", "100, 1000, 10000", key="amounts_tab2")

            if st.button(f"🚀 Iniciar Análisis de Liquidez para {selected_pair}", key="start_analysis_tab2"):
                try: amounts = [float(x.strip()) for x in amounts_input.split(',') if x.strip()]
                except ValueError: st.error("Formato de montos inválido."); st.stop()

                pair_row = df_gliquid.loc[df_gliquid['pair'] == selected_pair].iloc[0]
                token_a, token_b = pair_row["tokenaddress"], pair_row["quotetokenaddress"]
                
                all_results = []
                with st.spinner(f"Analizando '{selected_pair}'..."):
                    # Analizar A -> B (Directo)
                    params = {"tokenA": token_a, "tokenB": token_b}
                    pools = call_api("/pools", params).get("data", [])
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
                    # (Aquí se podría añadir la lógica para la dirección inversa si se desea)

                if not all_results:
                    st.error("El análisis no produjo resultados.")
                else:
                    st.success("🎉 ¡Análisis completado!")
                    df_res = pd.DataFrame(all_results)
                    df_res['pool_label'] = df_res['protocol'] + ' (' + df_res['inverse'] + ')'
                    
                    st.subheader("📄 Tabla de Resultados (Price Impact)")
                    st.dataframe(df_res)
                    
                    numeric_cols = [f"amount_{amt}" for amt in amounts]
                    for col in numeric_cols: df_res[col] = df_res[col].apply(parse_price_impact_value)
                    
                    df_melted = df_res.melt(id_vars=['pool_label'], value_vars=numeric_cols, var_name='Monto', value_name='Price Impact (%)').dropna()
                    if not df_melted.empty:
                        st.subheader("📈 Gráfico Comparativo de Liquidez")
                        df_melted['Monto'] = df_melted['Monto'].str.replace('amount_', '')
                        fig = px.bar(df_melted, x='Monto', y='Price Impact (%)', color='pool_label', barmode='group', title=f"Comparación de Price Impact para {selected_pair}")
                        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# Pestaña 3: Interfaz
# ------------------------------------------------------------------------------
with tab3:
    st.header("🔬 Simulación de Rutas Óptimas con Distribución de Volumen")
    st.markdown("Simula la ruta de trading, calcula comisiones y visualiza el % de volumen por cada exchange.")

    DEFAULT_FEE_BPS = Decimal("7.5")
    SPECIAL_PROTOCOLS = {"HyperSwapV2", "LaminarV3", "HybraFinanceV3", "ProjectX"}

    uploaded_file_tab3 = st.file_uploader("Sube tu archivo CSV.", type="csv", key="uploader_tab3")
    if uploaded_file_tab3:
        df_gliquid_tab3 = pd.read_csv(uploaded_file_tab3, dtype=str)
        df_gliquid_tab3 = df_gliquid_tab3[df_gliquid_tab3["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])

        if not df_gliquid_tab3.empty:
            selected_pairs = st.multiselect("Selecciona Pares a analizar:", df_gliquid_tab3['pair'].unique(), default=list(df_gliquid_tab3['pair'].unique())[:1], key="pair_select_tab3")
            amounts_input = st.text_input("Define montos a simular (separados por coma):", "100, 1000, 10000", key="amounts_tab3")

            if st.button("🚀 Iniciar Simulación de Rutas", key="start_sim_tab3"):
                try: amounts = [float(x.strip()) for x in amounts_input.split(',') if x.strip()]
                except ValueError: st.error("Formato de montos inválido."); st.stop()

                df_to_analyze = df_gliquid_tab3[df_gliquid_tab3['pair'].isin(selected_pairs)]
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
                                    route_amount_in_hr = normalize_raw_amount(route.get("amountIn"))
                                    for hop in flat_hops:
                                        protocol = hop.get("routerName", str(hop.get("routerIndex", "")))
                                        amount_in = normalize_raw_amount(hop.get("amountIn"))
                                        fee_bps = detect_fee_bps_from_hop(hop) or DEFAULT_FEE_BPS
                                        if protocol in SPECIAL_PROTOCOLS: fee_bps /= 100
                                        fee_amount = (amount_in * fee_bps / 10000) if amount_in else None
                                        if fee_amount: total_fee += fee_amount
                                        parsed_hops.append({"protocol": protocol, "amount": amount_in, "price_impact": hop.get("priceImpact", ""), "fee_bps": fee_bps, "fee_amount": fee_amount})
                                    output_rows.append({"pair": row.pair, "inverse": "YES" if is_inverse else "NO", "amount_requested": amount, "route_amountIn_hr": route_amount_in_hr, "total_fee_route": total_fee, "hops_data": parsed_hops})
                                progress_bar.progress(sim_count / total_sims if total_sims > 0 else 1.0)
                
                if not output_rows:
                    st.error("La simulación no produjo resultados.")
                else:
                    st.success("🎉 ¡Simulación completada!")
                    df_out = pd.DataFrame(output_rows)
                    
                    mask = df_out.apply(lambda r: is_amount_close(r['amount_requested'], r['route_amountIn_hr']), axis=1)
                    df_filtered = df_out[mask].reset_index(drop=True)

                    if df_filtered.empty:
                        st.warning("No se encontraron rutas donde el monto enrutado coincida con el solicitado (con tolerancia).")
                    else:
                        max_hops = max(len(h) for h in df_filtered['hops_data']) if not df_filtered.empty else 0
                        for k in range(max_hops):
                            df_filtered[f'protocol_route_{k+1}'] = df_filtered['hops_data'].apply(lambda h: h[k]['protocol'] if len(h) > k else None)
                            df_filtered[f'amount_route_{k+1}'] = df_filtered['hops_data'].apply(lambda h: h[k]['amount'] if len(h) > k else None)
                        
                        df_final = compute_amount_pct_routes(df_filtered.copy())
                        df_final['label'] = df_final['pair'] + ' (' + df_final['inverse'] + ')'

                        st.subheader("📈 Gráfico de Comisiones Totales")
                        fig_fees = px.bar(df_final, x='amount_requested', y='total_fee_route', color='label', barmode='group', title="Comisión Total Estimada por Ruta")
                        st.plotly_chart(fig_fees, use_container_width=True)

                        st.subheader("📄 Resumen de Rutas y Distribución de Volumen")
                        for i, row in df_final.iterrows():
                            summary = f"**Par:** {row['pair']} | **Inverso:** {row['inverse']} | **Monto:** {row['amount_requested']} | **Fee Total:** {row['total_fee_route']:.8f}"
                            with st.expander(summary):
                                col1, col2 = st.columns([1,1])
                                with col1:
                                    st.write("Detalle de Pasos (Hops):")
                                    st.dataframe(pd.DataFrame(row['hops_data']))
                                with col2:
                                    pie_data = []
                                    for k in range(1, max_hops + 1):
                                        protocol = row.get(f'protocol_route_{k+1}')
                                        percent = row.get(f'amount_pct_route_{k+1}')
                                        if protocol and pd.notna(percent) and percent > 0:
                                            pie_data.append({'Protocolo': protocol, 'Porcentaje': percent})
                                    if pie_data:
                                        pie_df = pd.DataFrame(pie_data).groupby('Protocolo')['Porcentaje'].sum().reset_index()
                                        fig_pie = px.pie(pie_df, values='Porcentaje', names='Protocolo', title='Distribución de Volumen')
                                        st.plotly_chart(fig_pie, use_container_width=True)
