import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime
import requests
from decimal import Decimal, getcontext
import time
import io
import json

# --- Configuración General de la Página ---
st.set_page_config(
    page_title="Análisis Gliquid",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Panel de Análisis Gliquid")
st.markdown("Navega entre las diferentes herramientas de análisis usando las pestañas.")

# --- Creación de Pestañas ---
tab1, tab2, tab3 = st.tabs([
    "Análisis Histórico APY", 
    "Análisis de Price Impact", 
    "Simulación de Rutas"
])

# ==============================================================================
# Pestaña 1: ANÁLISIS HISTÓRICO APY
# ==============================================================================
with tab1:
    st.header("📈 Análisis Histórico de APY para HyperEVM")
    # (El código de la Pestaña 1 se mantiene igual, lo he omitido aquí para no hacer la respuesta excesivamente larga)
    # (Asegúrate de mantener tu código original de la Pestaña 1 aquí)
    def parse_k_m_values(value):
        value_str = str(value).strip().upper()
        if value_str.endswith('K'): return float(value_str[:-1]) * 1_000
        if value_str.endswith('M'): return float(value_str[:-1]) * 1_000_000
        return pd.to_numeric(value, errors='coerce')
    @st.cache_data(ttl=600)
    def load_all_data(data_folder="data"):
        # ... (resto de tu función load_all_data)
        all_data = []
        if not os.path.isdir(data_folder):
            st.error(f"Error: No se encontró la carpeta '{data_folder}'.")
            return pd.DataFrame(), []
        # ... (completa con tu código original de la pestaña 1)
        return pd.DataFrame(), [] # Placeholder, usa tu código real
    st.info("El código de la Pestaña 1 está listo. Pega tu versión funcional aquí.")


# ==============================================================================
# Pestaña 2: ANÁLISIS DE PRICE IMPACT
# ==============================================================================
with tab2:
    st.header("💧 Análisis de Price Impact para Pools de Gliquid")
    # (El código de la Pestaña 2 se mantiene igual, lo he omitido aquí para no hacer la respuesta excesivamente larga)
    # (Asegúrate de mantener tu código original de la Pestaña 2 aquí)
    st.info("El código de la Pestaña 2 está listo. Pega tu versión funcional aquí.")

# ==============================================================================
# Pestaña 3: SIMULACIÓN DE RUTAS (NUEVA FUNCIONALIDAD)
# ==============================================================================
with tab3:
    st.header("🔬 Simulación de Rutas Óptimas")
    st.markdown("Esta herramienta simula la mejor ruta de trading para un par y monto determinados, detallando cada paso (hop), protocolo y comisiones estimadas.")

    # --- Configuración y Utilidades ---
    getcontext().prec = 48
    BASE_ROUTE_URL_TAB3 = "https://api.liqd.ag/v2/route"
    PAUSE_BETWEEN_REQS_TAB3 = 0.35
    DEFAULT_FEE_BPS = Decimal("7.5")
    SPECIAL_PROTOCOLS_TAB3 = {"HyperSwapV2", "LaminarV3", "HybraFinanceV3", "ProjectX"}

    def call_route_tab3(tokenIn, tokenOut, amountIn, log_area):
        params = { "tokenIn": tokenIn, "tokenOut": tokenOut, "amountIn": str(amountIn), "multiHop": "false", "slippage": "1.0" }
        log_area.info(f"🔗 Consultando mejor ruta para {amountIn} de {tokenIn} a {tokenOut}...")
        r = requests.get(BASE_ROUTE_URL_TAB3, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def normalize_raw_amount_tab3(raw_amt):
        if raw_amt is None: return None
        try:
            s = str(raw_amt)
            if "." in s: return Decimal(s)
            if len(s) > 18: return Decimal(s) / (Decimal(10) ** 18)
            return Decimal(s)
        except:
            return None

    def detect_fee_bps_from_hop(hop_dict):
        # ... (Esta función es compleja, la copio tal cual)
        if not isinstance(hop_dict, dict): return None
        candidates = ["feeBps", "fee", "feePercent", "poolFeeBps"]
        for k in candidates:
            if k in hop_dict and hop_dict.get(k) is not None:
                v = hop_dict.get(k)
                try:
                    if isinstance(v, str) and "%" in v:
                        s2 = v.strip().replace('%', '')
                        frac = Decimal(s2) / Decimal(100)
                        return frac * Decimal(10000)
                    vv = Decimal(str(v))
                    if vv <= Decimal("1"): return vv * Decimal(10000)
                    else: return vv
                except: continue
        return None

    # --- Interfaz de Usuario ---
    st.subheader("1. Cargar archivo de datos de Pares")
    uploaded_file_tab3 = st.file_uploader("Sube tu archivo CSV con los pares de Gliquid.", type="csv", key="uploader_tab3")

    if uploaded_file_tab3 is not None:
        try:
            df_tokens = pd.read_csv(uploaded_file_tab3, dtype=str)
            needed_cols = ["dex", "pair", "tokenaddress", "quotetokenaddress"]
            if not all(c in df_tokens.columns for c in needed_cols):
                st.error(f"El CSV debe contener las columnas: {', '.join(needed_cols)}")
            else:
                df_gliquid = df_tokens[df_tokens["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"]).reset_index(drop=True)
                if df_gliquid.empty:
                    st.warning("No se encontraron pares con 'dex' igual a 'gliquid' en el archivo.")
                else:
                    st.subheader("2. Seleccionar Pares y Montos")
                    pair_options = df_gliquid['pair'].unique()
                    selected_pairs = st.multiselect("Selecciona los Pares a analizar:", pair_options, default=pair_options[0] if len(pair_options) > 0 else None)
                    amounts_input = st.text_input("Define los montos (amounts) a simular (separados por coma):", "100, 1000, 10000", key="amounts_tab3")
                    
                    if st.button("🚀 Iniciar Simulación de Rutas"):
                        # --- Lógica Principal de Simulación ---
                        try:
                            amounts_to_analyze = [float(x.strip()) for x in amounts_input.split(',')]
                            if not amounts_to_analyze: raise ValueError("La lista de montos no puede estar vacía.")
                        except ValueError:
                            st.error("Error en el formato de los montos. Asegúrate de que sean números separados por comas.")
                            st.stop()
                        
                        df_to_analyze = df_gliquid[df_gliquid['pair'].isin(selected_pairs)]
                        out_rows = []
                        log_area = st.empty()
                        main_progress = st.progress(0.0)

                        with st.spinner("Realizando simulación de rutas..."):
                            for i, row_pair in enumerate(df_to_analyze.itertuples()):
                                pair_name, tA, tB = row_pair.pair, row_pair.tokenaddress, row_pair.quotetokenaddress
                                log_area.info(f"Analizando par: {pair_name} ({i+1}/{len(df_to_analyze)})")

                                for inverse_flag, (tokenA, tokenB) in (("NO", (tA, tB)), ("YES", (tB, tA))):
                                    for amt in amounts_to_analyze:
                                        time.sleep(PAUSE_BETWEEN_REQS_TAB3)
                                        try:
                                            resp = call_route_tab3(tokenA, tokenB, amt, log_area)
                                            # --- Procesamiento de la respuesta de la API ---
                                            routes = resp.get("routes", [])
                                            if not routes and "execution" in resp: # Fallback
                                                details = resp.get("execution", {}).get("details", {})
                                                routes = [{"hops": details.get("hopSwaps", [])}]

                                            for idx, r in enumerate(routes):
                                                route_hops_data, hop_texts = [], []
                                                hops_list = r.get("hops", r.get("swaps", []))
                                                flat_hops = [item for sublist in hops_list for item in (sublist if isinstance(sublist, list) else [sublist])]
                                                
                                                total_fee_route = Decimal(0)
                                                parsed_with_fees = []

                                                for hop in flat_hops:
                                                    proto = hop.get("routerName") or str(hop.get("routerIndex", ""))
                                                    amt_hr = normalize_raw_amount_tab3(hop.get("amountIn"))
                                                    detected_bps = detect_fee_bps_from_hop(hop)
                                                    fee_bps_used = detected_bps if detected_bps is not None else DEFAULT_FEE_BPS
                                                    if proto in SPECIAL_PROTOCOLS_TAB3: fee_bps_used /= Decimal("100")
                                                    
                                                    fee_amount = (amt_hr * (fee_bps_used / Decimal("10000"))) if amt_hr else None
                                                    if fee_amount: total_fee_route += fee_amount
                                                    
                                                    parsed_with_fees.append({
                                                        "protocol": proto, "amount": str(amt_hr) if amt_hr else None,
                                                        "price_impact": hop.get("priceImpact", ""), "fee_bps_used": str(fee_bps_used),
                                                        "fee_amount": str(fee_amount) if fee_amount else None
                                                    })

                                                out_rows.append({
                                                    "pair": pair_name, "inverse": inverse_flag, "amount_requested": amt,
                                                    "route_index": idx, "total_fee_route": str(total_fee_route) if total_fee_route != 0 else None,
                                                    "hops_data": parsed_with_fees
                                                })
                                        except Exception as e:
                                            st.warning(f"Error en {pair_name} (monto {amt}): {e}")
                                main_progress.progress((i + 1) / len(df_to_analyze))
                        
                        if not out_rows:
                            st.error("La simulación no produjo resultados.")
                        else:
                            st.balloons()
                            st.success("🎉 ¡Simulación completada!")
                            
                            # --- Expansión de columnas ---
                            df_out = pd.DataFrame(out_rows)
                            max_hops = max(len(row) for row in df_out['hops_data']) if not df_out.empty else 0
                            
                            for k in range(1, max_hops + 1):
                                df_out[f"protocol_route_{k}"] = df_out['hops_data'].apply(lambda h: h[k-1]['protocol'] if len(h) >= k else None)
                                df_out[f"amount_route_{k}"] = df_out['hops_data'].apply(lambda h: h[k-1]['amount'] if len(h) >= k else None)
                                df_out[f"price_impact_route_{k}"] = df_out['hops_data'].apply(lambda h: h[k-1]['price_impact'] if len(h) >= k else None)
                                df_out[f"fee_bps_route_{k}"] = df_out['hops_data'].apply(lambda h: h[k-1]['fee_bps_used'] if len(h) >= k else None)
                                df_out[f"fee_amount_route_{k}"] = df_out['hops_data'].apply(lambda h: h[k-1]['fee_amount'] if len(h) >= k else None)
                            
                            df_out = df_out.drop(columns=['hops_data'])
                            st.dataframe(df_out)

                            csv_buffer = io.StringIO()
                            df_out.to_csv(csv_buffer, index=False, encoding="utf-8")
                            st.download_button(
                                label="📥 Descargar resultados en CSV",
                                data=csv_buffer.getvalue(),
                                file_name=f"Simulacion_Rutas_{datetime.now().strftime('%Y%m%d')}.csv",
                                mime="text/csv"
                            )
        except Exception as e:
            st.error(f"No se pudo procesar el archivo CSV. Error: {e}")
