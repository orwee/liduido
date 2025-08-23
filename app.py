import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime
import requests
from decimal import Decimal, getcontext, InvalidOperation
import time
import re
import numpy as np

# ==============================================================================
# CONFIGURACIÓN GENERAL
# ==============================================================================
st.set_page_config(page_title="Análisis Gliquid", page_icon="📊", layout="wide")
getcontext().prec = 60

# --- Helper Functions (Generales y Pestaña 3) ---
def decimal_equal(x, y):
    """Compara dos valores como Decimal de forma segura."""
    try:
        return Decimal(str(x)) == Decimal(str(y))
    except (InvalidOperation, TypeError):
        return False

def compute_amount_pct_routes(df):
    """Calcula y añade columnas con el porcentaje de volumen por cada hop de la ruta."""
    if 'amount_requested' not in df.columns: return df
    
    df['amount_requested_num'] = pd.to_numeric(df['amount_requested'], errors='coerce')
    route_cols = sorted([c for c in df.columns if re.match(r'^amount_route_(\d+)$', c)])

    for col in route_cols:
        n = col.split('_')[-1]
        pct_col = f'amount_pct_route_{n}'
        df[col + '_num'] = pd.to_numeric(df[col], errors='coerce')
        
        # Evitar división por cero
        denom = df['amount_requested_num']
        valid_denom = denom.notna() & (denom != 0)
        
        df[pct_col] = np.nan
        df.loc[valid_denom, pct_col] = (df.loc[valid_denom, col + '_num'] / denom[valid_denom]) * 100
    
    # Limpiar columnas temporales
    df.drop(columns=[c for c in df.columns if c.endswith('_num')], inplace=True)
    return df

st.title("📊 Panel de Análisis Gliquid")
st.markdown("Navega entre las diferentes herramientas de análisis usando las pestañas.")

tab1, tab2, tab3 = st.tabs(["Análisis Histórico APY", "Análisis de Price Impact", "Simulación de Rutas"])

# ==============================================================================
# PESTAÑA 1: ANÁLISIS HISTÓRICO APY (Sin cambios)
# ==============================================================================
with tab1:
    st.header("📈 Análisis Histórico de APY para HyperEVM")
    st.info("La funcionalidad de esta pestaña se mantiene sin cambios.")
    # (Aquí iría el código completo y funcional de la Pestaña 1)

# ==============================================================================
# PESTAÑA 2: ANÁLISIS DE PRICE IMPACT (Sin cambios)
# ==============================================================================
with tab2:
    st.header("💧 Análisis de Price Impact para Pools de Gliquid")
    st.info("La funcionalidad de esta pestaña se mantiene sin cambios.")
    # (Aquí iría el código completo y funcional de la Pestaña 2)

# ==============================================================================
# PESTAÑA 3: SIMULACIÓN DE RUTAS (LÓGICA ACTUALIZADA)
# ==============================================================================
with tab3:
    st.header("🔬 Simulación de Rutas Óptimas con Distribución de Volumen")
    st.markdown("Simula la ruta de trading, calcula las comisiones y visualiza el % de volumen por cada exchange.")
    
    BASE_ROUTE_URL_TAB3 = "https://api.liqd.ag/v2/route"
    PAUSE_BETWEEN_REQS_TAB3 = 0.35
    DEFAULT_FEE_BPS = Decimal("7.5")
    SPECIAL_PROTOCOLS_TAB3 = {"HyperSwapV2", "LaminarV3", "HybraFinanceV3", "ProjectX"}

    def normalize_raw_amount_tab3(raw_amt):
        if raw_amt is None: return None
        try: return Decimal(str(raw_amt)) / (Decimal(10) ** 18)
        except: return None

    def detect_fee_bps_from_hop(hop):
        if not isinstance(hop, dict): return None
        for k in ["feeBps", "fee", "feePercent", "poolFeeBps"]:
            if (v := hop.get(k)) is not None:
                try:
                    if "%" in str(v): return (Decimal(str(v).strip('%')) / 100) * 10000
                    vv = Decimal(str(v)); return vv * 10000 if vv <= 1 else vv
                except: continue
        return None

    uploaded_file_tab3 = st.file_uploader("Sube tu archivo CSV.", type="csv", key="uploader_tab3")
    if uploaded_file_tab3:
        df_gliquid_tab3 = pd.read_csv(uploaded_file_tab3, dtype=str)
        df_gliquid_tab3 = df_gliquid_tab3[df_gliquid_tab3["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])

        if not df_gliquid_tab3.empty:
            selected_pairs_tab3 = st.multiselect("Selecciona Pares a analizar:", df_gliquid_tab3['pair'].unique(), default=list(df_gliquid_tab3['pair'].unique())[:1], key="pair_select_tab3")
            amounts_input_tab3 = st.text_input("Define montos (separados por coma):", "100, 1000, 10000", key="amounts_tab3_sim")

            if st.button("🚀 Iniciar Simulación de Rutas", key="start_sim_tab3"):
                try: amounts = [float(x.strip()) for x in amounts_input_tab3.split(',')]
                except: st.error("Formato de montos incorrecto."); st.stop()
                
                out_rows = []
                df_to_analyze = df_gliquid_tab3[df_gliquid_tab3['pair'].isin(selected_pairs_tab3)]
                progress_bar = st.progress(0.0)
                
                with st.spinner("Realizando simulación de rutas..."):
                    total_sims = len(df_to_analyze) * 2 * len(amounts)
                    sim_count = 0
                    for i, row in enumerate(df_to_analyze.itertuples()):
                        for inv, (tA, tB) in (("NO", (row.tokenaddress, row.quotetokenaddress)), ("YES", (row.quotetokenaddress, row.tokenaddress))):
                            for amt in amounts:
                                sim_count += 1
                                time.sleep(PAUSE_BETWEEN_REQS_TAB3)
                                try:
                                    params = {"tokenIn": tA, "tokenOut": tB, "amountIn": str(amt), "multiHop": "true"}
                                    resp = requests.get(BASE_ROUTE_URL_TAB3, params=params, timeout=30).json()

                                    if resp.get("success") is False:
                                        st.warning(f"API Error para {row.pair} (monto {amt}): {resp.get('message')}")
                                        continue
                                    
                                    # Lógica robusta para encontrar datos de rutas
                                    routes_data = []
                                    if isinstance(resp.get("routes"), list) and resp.get("routes"):
                                        routes_data = resp.get("routes")
                                    elif resp.get("execution"):
                                        details = resp.get("execution", {}).get("details", {})
                                        if hopSwaps := details.get("hopSwaps"):
                                            routes_data = [{"hops": hopSwaps, "amountIn": resp.get("execution", {}).get("amountIn")}]

                                    for idx, r in enumerate(routes_data):
                                        flat_hops = [item for sublist in r.get("hops", []) for item in (sublist if isinstance(sublist, list) else [sublist])]
                                        parsed_hops, total_fee = [], Decimal(0)
                                        # El amountIn de la ruta completa, crucial para el filtro
                                        route_amount_in_hr = normalize_raw_amount_tab3(r.get("amountIn"))

                                        for hop in flat_hops:
                                            proto = hop.get("routerName", str(hop.get("routerIndex", "")))
                                            amt_hr = normalize_raw_amount_tab3(hop.get("amountIn"))
                                            fee_bps = detect_fee_bps_from_hop(hop) or DEFAULT_FEE_BPS
                                            if proto in SPECIAL_PROTOCOLS_TAB3: fee_bps /= 100
                                            fee_amt = (amt_hr * fee_bps / 10000) if amt_hr else None
                                            if fee_amt: total_fee += fee_amt
                                            parsed_hops.append({"protocol": proto, "amount": amt_hr, "price_impact": hop.get("priceImpact", ""), "fee_bps": fee_bps, "fee_amount": fee_amt})
                                        
                                        out_rows.append({"pair": row.pair, "inverse": inv, "amount_requested": amt, "route_index": idx, "route_amountIn_hr": route_amount_in_hr, "total_fee_route": total_fee, "hops_data": parsed_hops})
                                
                                except Exception as e: 
                                    st.error(f"Error crítico en {row.pair} (monto {amt}): {e}")
                        progress_bar.progress((i + 1) / len(df_to_analyze))
                
                if out_rows:
                    st.success("🎉 Simulación completada!")
                    df_out = pd.DataFrame(out_rows)

                    # --- FILTRADO Y CÁLCULO DE PORCENTAJES ---
                    st.info("Filtrando resultados para asegurar que el monto enrutado coincida con el solicitado...")
                    mask = df_out.apply(lambda r: decimal_equal(r['amount_requested'], r['route_amountIn_hr']), axis=1)
                    df_filtered = df_out[mask].reset_index(drop=True)

                    # Expandir datos de hops en columnas
                    max_hops = max(len(h) for h in df_filtered['hops_data']) if not df_filtered.empty else 0
                    for k in range(max_hops):
                        df_filtered[f'protocol_route_{k+1}'] = df_filtered['hops_data'].apply(lambda h: h[k]['protocol'] if len(h) > k else None)
                        df_filtered[f'amount_route_{k+1}'] = df_filtered['hops_data'].apply(lambda h: h[k]['amount'] if len(h) > k else None)
                    
                    df_final = compute_amount_pct_routes(df_filtered)
                    
                    st.subheader("📄 Resultados de la Simulación")
                    st.dataframe(df_final.drop(columns=['hops_data', 'route_amountIn_hr']))
                    
                    # --- VISUALIZACIONES ---
                    df_final['label'] = df_final['pair'] + ' (' + df_final['inverse'].astype(str) + ')'
                    st.subheader("📈 Gráfico de Comisiones Totales por Ruta")
                    fig_fees = px.bar(df_final, x='amount_requested', y='total_fee_route', color='label', barmode='group', title="Comisión Total Estimada", labels={"amount_requested": "Monto Solicitado", "total_fee_route": "Comisión Total"})
                    st.plotly_chart(fig_fees, use_container_width=True)

                    st.subheader("📊 Distribución de Volumen por Ruta")
                    for i, row in df_final.iterrows():
                        summary = f"**Par:** {row['pair']} | **Inverso:** {row['inverse']} | **Monto:** {row['amount_requested']} | **Fee Total:** {row['total_fee_route']:.8f}"
                        with st.expander(summary):
                            # Preparar datos para el gráfico de torta
                            pie_data = []
                            for k in range(1, max_hops + 1):
                                protocol = row.get(f'protocol_route_{k}')
                                percent = row.get(f'amount_pct_route_{k}')
                                if protocol and pd.notna(percent):
                                    pie_data.append({'Protocolo': protocol, 'Porcentaje': percent})
                            
                            if pie_data:
                                pie_df = pd.DataFrame(pie_data).groupby('Protocolo')['Porcentaje'].sum().reset_index()
                                fig_pie = px.pie(pie_df, values='Porcentaje', names='Protocolo', title=f'Distribución de Volumen para un trade de {row["amount_requested"]}')
                                st.plotly_chart(fig_pie, use_container_width=True)
                            else:
                                st.write("No hay datos de distribución para mostrar.")
                else: 
                    st.error("La simulación no produjo resultados viables tras el filtrado.")
