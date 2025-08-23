import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime
import requests
from decimal import Decimal, getcontext
import time
import re

# ==============================================================================
# CONFIGURACIÓN GENERAL DE LA PÁGINA
# ==============================================================================
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
# PESTAÑA 1: ANÁLISIS HISTÓRICO APY
# ==============================================================================
with tab1:
    st.header("📈 Análisis Histórico de APY para HyperEVM")
    st.markdown("Selecciona un rango de fechas, y la app analizará los pares con datos de Gliquid disponibles en ese período.")

    # --- Funciones (Pestaña 1) ---
    def parse_k_m_values_tab1(value):
        value_str = str(value).strip().upper()
        if value_str.endswith('K'): return float(value_str[:-1]) * 1_000
        if value_str.endswith('M'): return float(value_str[:-1]) * 1_000_000
        return pd.to_numeric(value, errors='coerce')

    @st.cache_data(ttl=3600)
    def get_available_dates_tab1(data_folder="data"):
        if not os.path.isdir(data_folder): return []
        dates = []
        for filename in os.listdir(data_folder):
            if filename.endswith('.csv'):
                try:
                    dates.append(datetime.strptime(filename.replace('.csv', ''), "%d-%m-%y").date())
                except ValueError: continue
        return sorted(dates)

    @st.cache_data(ttl=600)
    def load_data_in_range_tab1(start_date, end_date, data_folder="data"):
        all_data = []
        for date_to_load in pd.date_range(start=start_date, end=end_date):
            filename = date_to_load.strftime("%d-%m-%y") + ".csv"
            file_path = os.path.join(data_folder, filename)
            if os.path.exists(file_path):
                try:
                    df = pd.read_csv(file_path)
                    df['date'] = pd.to_datetime(date_to_load)
                    all_data.append(df)
                except Exception as e:
                    st.warning(f"No se pudo cargar {filename}: {e}")
        
        if not all_data: return pd.DataFrame()

        combined_df = pd.concat(all_data, ignore_index=True)
        combined_df.columns = [col.lower() for col in combined_df.columns]
        
        for col in ['volume_24h', 'fees_24h']:
            if col in combined_df.columns: combined_df[col] = combined_df[col].apply(parse_k_m_values_tab1)
        for col in ['tvl', 'apy_24h', 'tier']:
             if col in combined_df.columns: combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce')

        combined_df = combined_df.fillna(0)
        if 'blockchain' in combined_df.columns:
            combined_df = combined_df[combined_df['blockchain'].str.lower() == 'hyperevm']
        return combined_df

    # --- Interfaz de Usuario (Pestaña 1) ---
    available_dates = get_available_dates_tab1()
    if not available_dates:
        st.error("No se encontraron archivos CSV en la carpeta 'data'. Asegúrate de que exista y contenga datos.")
    else:
        st.sidebar.header("Filtros de Análisis Histórico")
        date_range = st.sidebar.date_input(
            "Selecciona el rango de fechas:", value=(available_dates[0], available_dates[-1]),
            min_value=available_dates[0], max_value=available_dates[-1],
        )

        if len(date_range) == 2:
            start_date, end_date = date_range
            historical_df = load_data_in_range_tab1(start_date, end_date)

            if not historical_df.empty:
                simulated_tier = st.sidebar.slider("Fee Tier para Simulación:", 0.01, 5.0, 1.0, 0.05, format="%.2f%%")
                
                gliquid_pairs = historical_df[historical_df['dex'].str.lower() == 'gliquid']['pair'].str.lower().unique()
                if not any(gliquid_pairs):
                    st.warning("No hay datos de 'Gliquid' en el rango de fechas seleccionado.")
                else:
                    selected_pairs = st.multiselect("Selecciona Pairs (solo con datos de Gliquid):", options=sorted(gliquid_pairs), default=list(gliquid_pairs)[:1])

                    if selected_pairs:
                        filtered_df = historical_df[historical_df['pair'].str.lower().isin(selected_pairs)]
                        gliquid_df = filtered_df[filtered_df['dex'].str.lower() == 'gliquid']
                        other_dex_df = filtered_df[filtered_df['dex'].str.lower() != 'gliquid']
                        best_gliquid_df = gliquid_df.loc[gliquid_df.groupby(['date', 'pair'])['apy_24h'].idxmax()].copy()
                        best_gliquid_df['dex'] = 'gliquid (best)'
                        
                        sim_rows = []
                        for _, row in best_gliquid_df.iterrows():
                            new_apy = (row['volume_24h'] * (simulated_tier / 100) / row['tvl']) * 365 if row['tvl'] > 0 else 0
                            new_row = row.copy(); new_row.update({'dex': 'gliquid_test', 'tier': simulated_tier, 'apy_24h': new_apy * 100})
                            sim_rows.append(new_row)
                        
                        chart_df = pd.concat([other_dex_df, best_gliquid_df, pd.DataFrame(sim_rows)], ignore_index=True)
                        chart_df['identifier'] = chart_df['pair'] + " (" + chart_df['dex'] + ", Tier: " + chart_df['tier'].round(2).astype(str) + "%)"

                        st.subheader("Evolución Histórica del APY")
                        fig = px.line(chart_df, x='date', y='apy_24h', color='identifier', labels={'date': 'Fecha', 'apy_24h': 'APY 24h (%)'}, markers=True)
                        st.plotly_chart(fig, use_container_width=True)

                        with st.expander("Mostrar tabla de datos del gráfico"):
                            st.dataframe(chart_df[['date', 'pair', 'dex', 'tier', 'tvl', 'volume_24h', 'apy_24h']].sort_values(by=['date', 'pair']))

# ==============================================================================
# PESTAÑA 2: ANÁLISIS DE PRICE IMPACT
# ==============================================================================
with tab2:
    st.header("💧 Análisis de Price Impact para Pools de Gliquid")
    st.markdown("Compara la liquidez de pools analizando el impacto en precio para distintos montos de trade.")

    getcontext().prec = 36
    BASE_POOLS_URL_TAB2 = "https://api.liqd.ag/pools"
    BASE_ROUTE_URL_TAB2 = "https://api.liqd.ag/v2/route"
    PAUSE_BETWEEN_REQS_TAB2 = 0.35

    def parse_price_impact_tab2(value):
        if isinstance(value, str): value = value.strip().replace('%', '')
        return pd.to_numeric(value, errors='coerce')

    @st.cache_data(ttl=300)
    def analyze_pair_tab2(tokenA, tokenB, pair_name, inverse_flag, amounts_to_analyze):
        rows = []
        try:
            r_pools = requests.get(BASE_POOLS_URL_TAB2, params={"tokenA": tokenA, "tokenB": tokenB}, timeout=30)
            r_pools.raise_for_status()
            pools = r_pools.json().get("data", [])
        except Exception as e:
            st.warning(f"Error al obtener pools para {pair_name}: {e}")
            return []

        router_indices = sorted({int(p.get("routerIndex")) for p in pools if p.get("routerIndex") is not None})
        for p in pools:
            exclude_str = ",".join([str(x) for x in router_indices if x != p.get("routerIndex")])
            base_row = {"pair": pair_name, "inverse": "YES" if inverse_flag else "NO", "poolAddress": p.get("poolAddress"), "protocol": p.get("protocol")}
            for amt in amounts_to_analyze:
                time.sleep(PAUSE_BETWEEN_REQS_TAB2)
                try:
                    params = {"tokenIn": tokenA, "tokenOut": tokenB, "amountIn": str(amt), "multiHop": "false", "slippage": "1.0", "excludeDexes": exclude_str}
                    resp = requests.get(BASE_ROUTE_URL_TAB2, params=params, timeout=30).json()
                    base_row[f"amount_{amt}"] = resp.get("averagePriceImpact")
                except: base_row[f"amount_{amt}"] = "Error"
            rows.append(base_row)
        return rows

    uploaded_file_tab2 = st.file_uploader("Sube tu archivo CSV de pares.", type="csv", key="uploader_tab2")
    if uploaded_file_tab2:
        df_gliquid_tab2 = pd.read_csv(uploaded_file_tab2, dtype=str)
        df_gliquid_tab2 = df_gliquid_tab2[df_gliquid_tab2["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])
        
        selected_pair_tab2 = st.selectbox("Selecciona el Par a analizar:", df_gliquid_tab2['pair'].unique(), key="pair_select_tab2")
        amounts_input_tab2 = st.text_input("Define montos (separados por coma):", "100, 1000, 10000", key="amounts_tab2")

        if st.button(f"🚀 Iniciar Análisis de Liquidez para {selected_pair_tab2}"):
            try: amounts = [float(x.strip()) for x in amounts_input_tab2.split(',')]
            except: st.error("Formato de montos incorrecto."); st.stop()
            
            pair_row = df_gliquid_tab2[df_gliquid_tab2['pair'] == selected_pair_tab2].iloc[0]
            tokenA, tokenB = pair_row["tokenaddress"], pair_row["quotetokenaddress"]
            
            with st.spinner(f"Analizando '{selected_pair_tab2}'..."):
                all_rows = analyze_pair_tab2(tokenA, tokenB, selected_pair_tab2, False, amounts)
                all_rows.extend(analyze_pair_tab2(tokenB, tokenA, selected_pair_tab2, True, amounts))
            
            if all_rows:
                st.success("🎉 Análisis completado!")
                df_res = pd.DataFrame(all_rows)
                for col in [f"amount_{a}" for a in amounts]: df_res[col] = df_res[col].apply(parse_price_impact_tab2)
                df_res['pool_label'] = df_res['protocol'] + ' (' + df_res['inverse'] + ')'

                st.subheader("📈 Gráfico Comparativo de Liquidez")
                df_melted = df_res.melt(id_vars=['pool_label'], value_vars=[f"amount_{a}" for a in amounts], var_name='Monto', value_name='Price Impact (%)').dropna()
                df_melted['Monto'] = df_melted['Monto'].str.replace('amount_', '')
                fig = px.bar(df_melted, x='Monto', y='Price Impact (%)', color='pool_label', barmode='group', title=f"Comparación de Price Impact para {selected_pair_tab2}")
                st.plotly_chart(fig, use_container_width=True)
                
                st.subheader("📄 Tabla de Resultados (Price Impact %)")
                st.dataframe(df_res.set_index('pool_label')[[f"amount_{a}" for a in amounts]].style.format("{:.4f}%").background_gradient(cmap='Reds'))
            else: st.error("El análisis no produjo resultados.")

# ==============================================================================
# PESTAÑA 3: SIMULACIÓN DE RUTAS
# ==============================================================================
with tab3:
    st.header("🔬 Simulación de Rutas Óptimas")
    st.markdown("Encuentra la ruta de trading más eficiente y visualiza sus comisiones y pasos detallados.")
    
    getcontext().prec = 48
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
                    for i, row in enumerate(df_to_analyze.itertuples()):
                        for inv, (tA, tB) in (("NO", (row.tokenaddress, row.quotetokenaddress)), ("YES", (row.quotetokenaddress, row.tokenaddress))):
                            for amt in amounts:
                                time.sleep(PAUSE_BETWEEN_REQS_TAB3)
                                try:
                                    params = {"tokenIn": tA, "tokenOut": tB, "amountIn": str(amt), "multiHop": "true"}
                                    resp = requests.get(BASE_ROUTE_URL_TAB3, params=params, timeout=30).json()
                                    routes = resp.get("routes", [])
                                    for idx, r in enumerate(routes):
                                        flat_hops = [item for sublist in r.get("hops", []) for item in (sublist if isinstance(sublist, list) else [sublist])]
                                        parsed_hops, total_fee = [], Decimal(0)
                                        for hop in flat_hops:
                                            proto = hop.get("routerName", str(hop.get("routerIndex", "")))
                                            amt_hr = normalize_raw_amount_tab3(hop.get("amountIn"))
                                            fee_bps = detect_fee_bps_from_hop(hop) or DEFAULT_FEE_BPS
                                            if proto in SPECIAL_PROTOCOLS_TAB3: fee_bps /= 100
                                            fee_amt = (amt_hr * fee_bps / 10000) if amt_hr else None
                                            if fee_amt: total_fee += fee_amt
                                            parsed_hops.append({"Protocolo": proto, "Monto": f"{amt_hr:.6f}", "Impacto Precio": hop.get("priceImpact", ""), "Fee (bps)": f"{fee_bps:.4f}", "Monto Fee": f"{fee_amt:.8f}" if fee_amt else "N/A"})
                                        out_rows.append({"pair": row.pair, "inverse": inv, "amount_requested": amt, "route_index": idx, "total_fee_route": total_fee, "hops_data": parsed_hops})
                                except Exception as e: st.warning(f"Error en {row.pair} (monto {amt}): {e}")
                        progress_bar.progress((i + 1) / len(df_to_analyze))
                
                if out_rows:
                    st.success("🎉 Simulación completada!")
                    df_out = pd.DataFrame(out_rows)
                    df_out['label'] = df_out['pair'] + ' (' + df_out['inverse'] + ')'

                    st.subheader("📈 Gráfico de Comisiones Totales por Ruta")
                    fig = px.bar(df_out, x='amount_requested', y='total_fee_route', color='label', barmode='group', title="Comisión Total Estimada por Monto y Dirección", labels={"amount_requested": "Monto Solicitado", "total_fee_route": "Comisión Total (en token de entrada)"})
                    st.plotly_chart(fig, use_container_width=True)

                    st.subheader("📄 Resumen de Rutas y Detalles")
                    for i, row in df_out.iterrows():
                        summary = f"**Par:** {row['pair']} | **Dirección:** {row['inverse']} | **Monto:** {row['amount_requested']} | **Comisión Total:** {row['total_fee_route']:.8f}"
                        with st.expander(summary):
                            st.dataframe(pd.DataFrame(row['hops_data']))
                else: st.error("La simulación no produjo resultados.")
