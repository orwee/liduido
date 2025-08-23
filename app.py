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

# ==============================================================================
# CONFIGURACIÓN GENERAL DE LA PÁGINA
# ==============================================================================
st.set_page_config(
    page_title="Análisis Gliquid",
    page_icon="📊",
    layout="wideimport streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime
import requests
from decimal import Decimal, getcontext
import time
import io
import json
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
    def parse_k_m_values(value):
        value_str = str(value).strip().upper()
        if value_str.endswith('K'): return float(value_str[:-1]) * 1_000
        if value_str.endswith('M'): return float(value_str[:-1]) * 1_000_000
        return pd.to_numeric(value, errors='coerce')

    @st.cache_data(ttl=3600)
    def get_available_dates(data_folder="data"):
        """Escanea la carpeta de datos para encontrar el rango de fechas de los archivos CSV."""
        if not os.path.isdir(data_folder):
            return []
        dates = []
        for filename in os.listdir(data_folder):
            if filename.endswith('.csv'):
                try:
                    date_obj = datetime.strptime(filename.replace('.csv', ''), "%d-%m-%y").date()
                    dates.append(date_obj)
                except ValueError:
                    continue
        return sorted(dates)

    @st.cache_data(ttl=600)
    def load_data_in_range(start_date, end_date, data_folder="data"):
        """Carga y procesa datos solo para el rango de fechas seleccionado."""
        all_data = []
        loaded_files = []
        date_range = pd.date_range(start=start_date, end=end_date)
        
        for date_to_load in date_range:
            filename = date_to_load.strftime("%d-%m-%y") + ".csv"
            file_path = os.path.join(data_folder, filename)
            if os.path.exists(file_path):
                try:
                    df = pd.read_csv(file_path)
                    df['date'] = pd.to_datetime(date_to_load)
                    all_data.append(df)
                    loaded_files.append(filename)
                except Exception as e:
                    st.warning(f"No se pudo cargar {filename}: {e}")
        
        if not all_data:
            return pd.DataFrame(), []

        combined_df = pd.concat(all_data, ignore_index=True)
        combined_df.columns = [col.lower() for col in combined_df.columns]
        
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

    # --- Interfaz de Usuario (Pestaña 1) ---
    available_dates = get_available_dates()
    if not available_dates:
        st.error("No se encontraron archivos CSV en la carpeta 'data'. Asegúrate de que la carpeta exista y contenga tus datos.")
    else:
        st.sidebar.header("Filtros de Análisis Histórico")
        date_range = st.sidebar.date_input(
            "Selecciona el rango de fechas a analizar:",
            value=(available_dates[0], available_dates[-1]),
            min_value=available_dates[0],
            max_value=available_dates[-1],
        )

        if len(date_range) == 2:
            start_date, end_date = date_range
            historical_df, loaded_files = load_data_in_range(start_date, end_date)

            if not historical_df.empty:
                simulated_tier = st.sidebar.slider("Fee Tier para Simulación:", 0.01, 5.0, 1.0, 0.05, format="%.2f%%")
                
                # Filtrar pares que SÍ tienen registros de Gliquid
                gliquid_pairs = historical_df[historical_df['dex'].str.lower() == 'gliquid']['pair'].str.lower().unique()
                all_pairs = sorted([p for p in historical_df['pair'].str.lower().unique() if p in gliquid_pairs])

                if not all_pairs:
                    st.warning("No se encontraron datos de 'Gliquid' para ningún par en el rango de fechas seleccionado.")
                else:
                    selected_pairs = st.multiselect("Selecciona los Pairs a visualizar (solo se muestran pares con datos de Gliquid):", options=all_pairs, default=all_pairs[0] if all_pairs else [])

                    if selected_pairs:
                        # (La lógica de procesamiento y gráficos se mantiene igual)
                        filtered_df = historical_df[historical_df['pair'].str.lower().isin(selected_pairs)].copy()
                        gliquid_df = filtered_df[filtered_df['dex'].str.lower() == 'gliquid'].copy()
                        other_dex_df = filtered_df[filtered_df['dex'].str.lower() != 'gliquid'].copy()
                        best_gliquid_df = pd.DataFrame()
                        if not gliquid_df.empty:
                            best_gliquid_indices = gliquid_df.groupby(['date', 'pair'])['apy_24h'].idxmax()
                            best_gliquid_df = gliquid_df.loc[best_gliquid_indices].copy()
                            best_gliquid_df['dex'] = 'gliquid (best)'
                        all_simulation_rows = []
                        if not best_gliquid_df.empty:
                            for index, row in best_gliquid_df.iterrows():
                                new_apy = (row['volume_24h'] * (simulated_tier / 100) / row['tvl']) * 365 if row['tvl'] > 0 else 0
                                new_row = row.copy(); new_row['dex'], new_row['tier'], new_row['apy_24h'] = 'gliquid_test', simulated_tier, new_apy * 100
                                all_simulation_rows.append(new_row)
                        chart_df = pd.concat([other_dex_df, best_gliquid_df, pd.DataFrame(all_simulation_rows)], ignore_index=True)
                        chart_df['identifier'] = chart_df['pair'] + " (" + chart_df['dex'] + ", Tier: " + chart_df['tier'].round(2).astype(str) + "%)"

                        st.subheader("Evolución Histórica del APY por Par")
                        fig = px.line(chart_df, x='date', y='apy_24h', color='identifier', labels={'date': 'Fecha', 'apy_24h': 'APY 24h (%)'}, markers=True)
                        st.plotly_chart(fig, use_container_width=True)

                        with st.expander("Mostrar tabla de datos del gráfico"):
                            st.dataframe(chart_df[['date', 'pair', 'dex', 'tier', 'tvl', 'volume_24h', 'apy_24h']].sort_values(by=['date', 'pair']))
                    else:
                        st.info("Selecciona al menos un par para generar el gráfico.")
            else:
                st.warning("No se encontraron datos para el rango de fechas seleccionado.")

# ==============================================================================
# PESTAÑA 2: ANÁLISIS DE PRICE IMPACT
# ==============================================================================
with tab2:
    st.header("💧 Análisis de Price Impact para Pools de Gliquid")
    st.markdown("Compara la liquidez de diferentes pools analizando el impacto en precio para distintos montos de trade.")

    # --- Funciones (Pestaña 2) --- (Se mantienen las mismas)
    getcontext().prec = 36
    BASE_POOLS_URL_TAB2 = "https://api.liqd.ag/pools"
    BASE_ROUTE_URL_TAB2 = "https://api.liqd.ag/v2/route"
    PAUSE_BETWEEN_REQS_TAB2 = 0.35
    
    def parse_price_impact(value):
        """Convierte un string de porcentaje a un float, o devuelve NaN si no es válido."""
        if isinstance(value, str):
            value = value.strip().replace('%', '')
            return pd.to_numeric(value, errors='coerce')
        return pd.to_numeric(value, errors='coerce')

    # (La función `analyze_pair_tab2` se mantiene igual que en la versión anterior)
    def analyze_pair_tab2(tokenA, tokenB, pair_name, inverse_flag, log_area, amounts_to_analyze):
        # ... (código sin cambios)
        return [] # Placeholder

    # --- Interfaz de Usuario (Pestaña 2) ---
    uploaded_file_tab2 = st.file_uploader("Sube tu archivo CSV con los pares de Gliquid.", type="csv", key="uploader_tab2")
    
    if uploaded_file_tab2:
        df_gliquid_tab2 = pd.read_csv(uploaded_file_tab2, dtype=str)
        df_gliquid_tab2 = df_gliquid_tab2[df_gliquid_tab2["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])
        
        if not df_gliquid_tab2.empty:
            selected_pair_tab2 = st.selectbox("Selecciona el Par a analizar:", df_gliquid_tab2['pair'].unique(), key="pair_select_tab2")
            amounts_input_tab2 = st.text_input("Define los montos a simular:", "100, 1000, 10000", key="amounts_tab2")

            if st.button(f"🚀 Iniciar Análisis de Liquidez para {selected_pair_tab2}"):
                # ... (La lógica de análisis se mantiene igual)
                
                # --- NUEVA VISUALIZACIÓN DE RESULTADOS ---
                # Placeholder para el resultado del análisis
                # all_rows = run_analysis(...)
                # df_res = pd.DataFrame(all_rows)

                # if not df_res.empty:
                    # st.subheader("📈 Gráfico Comparativo de Liquidez")
                    # df_plot = df_res.copy()
                    # amount_cols = [c for c in df_plot.columns if c.startswith('amount_')]
                    # for col in amount_cols:
                    #     df_plot[col] = parse_price_impact(df_plot[col])
                    
                    # df_plot['pool_label'] = df_plot['protocol'] + ' (' + df_plot['inverse'] + ')'
                    # df_melted = df_plot.melt(id_vars=['pool_label'], value_vars=amount_cols, var_name='Monto', value_name='Price Impact (%)')
                    # df_melted.dropna(subset=['Price Impact (%)'], inplace=True)

                    # fig = px.bar(df_melted, x='Monto', y='Price Impact (%)', color='pool_label', barmode='group', title=f"Comparación de Price Impact para {selected_pair_tab2}")
                    # st.plotly_chart(fig, use_container_width=True)
                    
                    # st.subheader("📄 Tabla de Resultados (Price Impact %)")
                    # df_pivot = df_plot.pivot_table(index='pool_label', columns='Monto', values=amount_cols[0] if len(amount_cols)==1 else amount_cols)
                    # st.dataframe(df_pivot.style.format("{:.4f}%").background_gradient(cmap='Reds'))
                # else:
                #     st.error("El análisis no produjo resultados.")
                st.warning("La lógica de análisis y visualización de esta pestaña está lista para ser implementada.")

# ==============================================================================
# PESTAÑA 3: SIMULACIÓN DE RUTAS
# ==============================================================================
with tab3:
    st.header("🔬 Simulación de Rutas Óptimas")
    st.markdown("Encuentra la ruta de trading más eficiente y visualiza sus comisiones y pasos detallados.")
    
    # --- Funciones (Pestaña 3) --- (Se mantienen las mismas)
    getcontext().prec = 48
    BASE_ROUTE_URL_TAB3 = "https://api.liqd.ag/v2/route"
    # ... (resto de funciones de la pestaña 3 sin cambios)

    # --- Interfaz de Usuario (Pestaña 3) ---
    uploaded_file_tab3 = st.file_uploader("Sube tu archivo CSV.", type="csv", key="uploader_tab3")
    
    if uploaded_file_tab3:
        df_gliquid_tab3 = pd.read_csv(uploaded_file_tab3, dtype=str)
        df_gliquid_tab3 = df_gliquid_tab3[df_gliquid_tab3["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])

        if not df_gliquid_tab3.empty:
            pair_options = df_gliquid_tab3['pair'].unique()
            selected_pairs_tab3 = st.multiselect("Selecciona Pares a analizar:", pair_options, default=pair_options[0] if len(pair_options) > 0 else None, key="pair_select_tab3")
            amounts_input_tab3 = st.text_input("Define montos a simular:", "100, 1000, 10000", key="amounts_tab3_sim")

            if st.button("🚀 Iniciar Simulación de Rutas", key="start_sim_tab3"):
                # ... (La lógica de análisis se mantiene igual)
                
                # --- NUEVA VISUALIZACIÓN DE RESULTADOS ---
                # Placeholder para el resultado del análisis
                # df_out = run_simulation(...)
                
                # if not df_out.empty:
                    # df_out['total_fee_route'] = pd.to_numeric(df_out['total_fee_route'], errors='coerce')
                    # df_out['label'] = df_out['pair'] + ' (' + df_out['inverse'] + ')'

                    # st.subheader("📈 Gráfico de Comisiones Totales por Ruta")
                    # fig = px.bar(df_out, x='amount_requested', y='total_fee_route', color='label', barmode='group', title="Comisión Total Estimada por Monto y Dirección")
                    # st.plotly_chart(fig, use_container_width=True)
                    
                    # st.subheader("📄 Resumen de Rutas y Detalles")
                    # summary_cols = ['pair', 'inverse', 'amount_requested', 'route_index', 'total_fee_route']
                    # for i, row in df_out.iterrows():
                    #     summary_text = f"**Par:** {row['pair']} | **Dirección:** {row['inverse']} | **Monto:** {row['amount_requested']} | **Comisión Total:** {row['total_fee_route']:.6f}"
                    #     with st.expander(summary_text):
                    #         hop_cols = [c for c in df_out.columns if c.startswith(('protocol', 'amount_route', 'price_impact', 'fee_bps', 'fee_amount'))]
                    #         hop_df = df_out.loc[[i], hop_cols].copy()
                    #         # Lógica para mostrar los hops de forma bonita
                    #         st.dataframe(hop_df)
                # else:
                #     st.error("La simulación no produjo resultados.")
                st.warning("La lógica de análisis y visualización de esta pestaña está lista para ser implementada.")
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
    st.markdown("Carga datos históricos, los filtra por la blockchain **hyperevm** y permite analizar el APY por par, incluyendo una simulación dinámica.")

    # --- Funciones de Carga y Procesamiento (Pestaña 1) ---
    def parse_k_m_values(value):
        """Convierte un valor de string con sufijo 'K' o 'M' a un número."""
        value_str = str(value).strip().upper()
        if value_str.endswith('K'):
            return float(value_str[:-1]) * 1_000
        if value_str.endswith('M'):
            return float(value_str[:-1]) * 1_000_000
        return pd.to_numeric(value, errors='coerce')

    @st.cache_data(ttl=600)
    def load_all_data(data_folder="data"):
        """Carga y combina archivos CSV de un rango de fechas."""
        all_data = []
        if not os.path.isdir(data_folder):
            st.error(f"Error: No se encontró la carpeta '{data_folder}'. Asegúrate de que exista y contenga tus archivos CSV.")
            return pd.DataFrame(), []

        filenames = sorted([f for f in os.listdir(data_folder) if f.endswith('.csv')])
        if not filenames:
            st.warning(f"No se encontraron archivos .csv en la carpeta '{data_folder}'.")
            return pd.DataFrame(), []

        start_date = datetime.strptime("10-08-25", "%d-%m-%y").date()
        end_date = datetime.strptime("16-08-25", "%d-%m-%y").date()
        loaded_files = []

        for filename in filenames:
            try:
                date_str = filename.replace('.csv', '')
                file_date = datetime.strptime(date_str, "%d-%m-%y").date()
                if start_date <= file_date <= end_date:
                    file_path = os.path.join(data_folder, filename)
                    df = pd.read_csv(file_path)
                    df['date'] = pd.to_datetime(date_str, format='%d-%m-%y')
                    all_data.append(df)
                    loaded_files.append(filename)
            except Exception:
                continue # Ignora archivos que no coincidan

        if not all_data:
            st.warning("No se encontraron archivos CSV en el rango de fechas especificado.")
            return pd.DataFrame(), []

        combined_df = pd.concat(all_data, ignore_index=True)
        combined_df.columns = [col.lower() for col in combined_df.columns]

        cols_to_parse = ['volume_24h', 'volume_6h', 'volume_1h', 'fees_24h']
        for col in cols_to_parse:
            if col in combined_df.columns:
                combined_df[col] = combined_df[col].apply(parse_k_m_values)

        numeric_cols = ['tvl', 'apy_24h', 'tier']
        for col in numeric_cols:
            if col in combined_df.columns:
                combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce')

        combined_df = combined_df.fillna(0)

        if 'blockchain' in combined_df.columns:
            combined_df['blockchain'] = combined_df['blockchain'].str.lower()
            combined_df = combined_df[combined_df['blockchain'] == 'hyperevm']
        else:
            st.error("Error: La columna 'blockchain' no se encontró en los archivos CSV.")
            return pd.DataFrame(), loaded_files

        return combined_df, loaded_files

    # --- Interfaz de Usuario (Pestaña 1) ---
    st.subheader("1. Simulación para 'gliquid_test'")
    simulated_tier = st.slider(
        "Selecciona el Fee Tier para la simulación:",
        min_value=0.01, max_value=5.0, value=1.0, step=0.05, format="%.2f%%", key="apy_slider"
    )

    historical_df, loaded_files = load_all_data()

    if loaded_files:
        with st.expander("Ver archivos cargados"):
            st.write(loaded_files)

    if not historical_df.empty:
        required_columns = ['dex', 'volume_24h', 'tvl', 'apy_24h', 'pair']
        missing_columns = [col for col in required_columns if col not in historical_df.columns]
        if missing_columns:
            st.error(f"Error: Faltan columnas en tus CSVs: **{', '.join(missing_columns)}**.")
            st.stop()

        st.subheader("2. Análisis y Comparativa")
        all_pairs = sorted(historical_df['pair'].str.lower().unique())
        default_selection = [all_pairs[0]] if all_pairs else []
        selected_pairs = st.multiselect("Selecciona los Pairs a visualizar:", options=all_pairs, default=default_selection)

        if selected_pairs:
            filtered_df = historical_df[historical_df['pair'].str.lower().isin(selected_pairs)].copy()
            gliquid_df = filtered_df[filtered_df['dex'].str.lower() == 'gliquid'].copy()
            other_dex_df = filtered_df[filtered_df['dex'].str.lower() != 'gliquid'].copy()

            best_gliquid_df = pd.DataFrame()
            if not gliquid_df.empty:
                best_gliquid_indices = gliquid_df.groupby(['date', 'pair'])['apy_24h'].idxmax()
                best_gliquid_df = gliquid_df.loc[best_gliquid_indices].copy()
                best_gliquid_df['dex'] = 'gliquid (best)'

            all_simulation_rows = []
            if not best_gliquid_df.empty:
                for index, row in best_gliquid_df.iterrows():
                    new_apy = (row['volume_24h'] * (simulated_tier / 100) / row['tvl']) * 365 if row['tvl'] > 0 else 0
                    new_row = row.copy()
                    new_row['dex'], new_row['tier'], new_row['apy_24h'] = 'gliquid_test', simulated_tier, new_apy * 100
                    all_simulation_rows.append(new_row)

            chart_df = pd.concat([other_dex_df, best_gliquid_df], ignore_index=True)
            if all_simulation_rows:
                chart_df = pd.concat([chart_df, pd.DataFrame(all_simulation_rows)], ignore_index=True)

            chart_df['identifier'] = chart_df['pair'] + " (" + chart_df['dex'] + ", Tier: " + chart_df['tier'].round(2).astype(str) + "%)"

            if st.checkbox("Mostrar tabla de datos del gráfico", value=True, key="show_table_tab1"):
                st.dataframe(chart_df[['date', 'pair', 'dex', 'tier', 'tvl', 'volume_24h', 'apy_24h']].sort_values(by=['date', 'pair']))

            fig = px.line(chart_df, x='date', y='apy_24h', color='identifier', title="Evolución Histórica del APY por Par", labels={'date': 'Fecha', 'apy_24h': 'APY 24h (%)', 'identifier': 'Pool'}, markers=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Selecciona al menos un par para generar el gráfico.")
    else:
        st.info("Esperando a que se carguen los datos de la carpeta 'data'...")

# ==============================================================================
# PESTAÑA 2: ANÁLISIS DE PRICE IMPACT
# ==============================================================================
with tab2:
    st.header("💧 Análisis de Price Impact para Pools de Gliquid")
    st.markdown("Analiza el impacto en el precio para diferentes volúmenes de trade en pools específicos de Gliquid.")

    # --- Configuración y Funciones (Pestaña 2) ---
    getcontext().prec = 36
    BASE_POOLS_URL_TAB2 = "https://api.liqd.ag/pools"
    BASE_ROUTE_URL_TAB2 = "https://api.liqd.ag/v2/route"
    PAUSE_BETWEEN_REQS_TAB2 = 0.35

    def call_route_tab2(tokenIn, tokenOut, amountIn, log_area, excludeDexes=None):
        params = {"tokenIn": tokenIn, "tokenOut": tokenOut, "amountIn": str(amountIn), "multiHop": "false", "slippage": "1.0"}
        if excludeDexes: params["excludeDexes"] = excludeDexes
        log_area.info(f"🔗 Simulando ruta para un monto de {amountIn}...")
        r = requests.get(BASE_ROUTE_URL_TAB2, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def analyze_pair_tab2(tokenA, tokenB, pair_name, inverse_flag, log_area, amounts_to_analyze):
        rows = []
        try:
            params = {"tokenA": tokenA, "tokenB": tokenB}
            log_area.info(f"🔗 Consultando pools para {tokenA}/{tokenB}...")
            r_pools = requests.get(BASE_POOLS_URL_TAB2, params=params, timeout=30)
            r_pools.raise_for_status()
            pools = r_pools.json().get("data", [])
        except Exception as e:
            st.warning(f"Error al obtener pools para {pair_name}: {e}")
            return rows

        if not pools:
            log_area.warning(f"No se encontraron pools para {pair_name}.")
            return rows

        router_indices = sorted({int(p.get("routerIndex")) for p in pools if p.get("routerIndex") is not None})
        for p in pools:
            poolAddress, routerIndex, protocol = p.get("poolAddress"), p.get("routerIndex"), p.get("protocol")
            log_area.info(f"--- Analizando Pool: {poolAddress} | Protocolo: {protocol} ---")
            exclude_str = ",".join([str(x) for x in router_indices if x != (int(routerIndex) if routerIndex is not None else -1)])
            base_row = {"pair": pair_name, "inverse": inverse_flag, "poolAddress": poolAddress, "protocol": protocol}
            for amt in amounts_to_analyze:
                col = f"amount_{amt}_avgPriceImpact"
                base_row[col] = "missing"
                time.sleep(PAUSE_BETWEEN_REQS_TAB2)
                try:
                    resp = call_route_tab2(tokenA, tokenB, amt, log_area, excludeDexes=exclude_str)
                    if avg_pi := resp.get("averagePriceImpact"): base_row[col] = avg_pi
                except Exception as e:
                    log_area.warning(f"Error en simulación (monto={amt}): {e}")
            rows.append(base_row)
        return rows

    # --- Interfaz de Usuario (Pestaña 2) ---
    st.subheader("1. Cargar archivo de datos de Pares")
    uploaded_file_tab2 = st.file_uploader("Sube tu archivo CSV con los pares de Gliquid.", type="csv", key="uploader_tab2")

    if uploaded_file_tab2 is not None:
        try:
            df_tokens_tab2 = pd.read_csv(uploaded_file_tab2, dtype=str)
            needed_cols_tab2 = ["dex", "pair", "tokenaddress", "quotetokenaddress"]
            if not all(c in df_tokens_tab2.columns for c in needed_cols_tab2):
                st.error(f"El CSV debe contener las columnas: {', '.join(needed_cols_tab2)}")
            else:
                df_gliquid_tab2 = df_tokens_tab2[df_tokens_tab2["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])
                if df_gliquid_tab2.empty:
                    st.warning("No se encontraron pares con 'dex' igual a 'gliquid' en el archivo.")
                else:
                    st.subheader("2. Seleccionar Par y Montos")
                    selected_pair_tab2 = st.selectbox("Selecciona el Par a analizar:", df_gliquid_tab2['pair'].unique())
                    amounts_input_tab2 = st.text_input("Define los montos a simular (separados por coma):", "0.1, 1, 10, 100, 1000", key="amounts_tab2")

                    if st.button(f"🚀 Iniciar Análisis para {selected_pair_tab2}"):
                        try:
                            amounts = [float(x.strip()) for x in amounts_input_tab2.split(',')]
                            if not amounts: raise ValueError("Lista de montos vacía.")
                        except Exception:
                            st.error("Error en el formato de los montos. Deben ser números separados por comas.")
                            st.stop()
                        
                        pair_row = df_gliquid_tab2[df_gliquid_tab2['pair'] == selected_pair_tab2].iloc[0]
                        pair_name, tokenA, tokenB = pair_row["pair"], pair_row["tokenaddress"], pair_row["quotetokenaddress"]
                        all_rows = []
                        log_area = st.empty()
                        with st.spinner(f"Analizando '{pair_name}'..."):
                            all_rows.extend(analyze_pair_tab2(tokenA, tokenB, pair_name, "NO", log_area, amounts))
                            all_rows.extend(analyze_pair_tab2(tokenB, tokenA, pair_name, "YES", log_area, amounts))
                        
                        if not all_rows:
                            st.error("El análisis no produjo resultados.")
                        else:
                            st.balloons()
                            st.success("🎉 ¡Análisis completado!")
                            df_res = pd.DataFrame(all_rows)
                            st.dataframe(df_res)
                            st.download_button(
                                "📥 Descargar resultados en CSV",
                                df_res.to_csv(index=False).encode('utf-8'),
                                f"PriceImpact_{pair_name.replace('/', '-')}.csv", "text/csv"
                            )
        except Exception as e:
            st.error(f"No se pudo procesar el archivo CSV. Error: {e}")

# ==============================================================================
# PESTAÑA 3: SIMULACIÓN DE RUTAS
# ==============================================================================
with tab3:
    st.header("🔬 Simulación de Rutas Óptimas")
    st.markdown("Simula la mejor ruta de trading para un par y monto, detallando cada paso (hop), protocolo y comisiones estimadas.")

    # --- Configuración y Funciones (Pestaña 3) ---
    getcontext().prec = 48
    BASE_ROUTE_URL_TAB3 = "https://api.liqd.ag/v2/route"
    PAUSE_BETWEEN_REQS_TAB3 = 0.35
    DEFAULT_FEE_BPS = Decimal("7.5")
    SPECIAL_PROTOCOLS_TAB3 = {"HyperSwapV2", "LaminarV3", "HybraFinanceV3", "ProjectX"}

    def call_route_tab3(tokenIn, tokenOut, amountIn, log_area):
        params = {"tokenIn": tokenIn, "tokenOut": tokenOut, "amountIn": str(amountIn), "multiHop": "false", "slippage": "1.0"}
        log_area.info(f"🔗 Consultando mejor ruta para {amountIn} de {tokenIn} a {tokenOut}...")
        r = requests.get(BASE_ROUTE_URL_TAB3, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def normalize_raw_amount_tab3(raw_amt):
        if raw_amt is None: return None
        try:
            s = str(raw_amt)
            return Decimal(s) if "." in s else Decimal(s) / (Decimal(10) ** 18 if len(s) > 18 else 1)
        except: return None

    def detect_fee_bps_from_hop(hop_dict):
        if not isinstance(hop_dict, dict): return None
        for k in ["feeBps", "fee", "feePercent", "poolFeeBps"]:
            if (v := hop_dict.get(k)) is not None:
                try:
                    if "%" in str(v): return (Decimal(str(v).strip('%')) / 100) * 10000
                    vv = Decimal(str(v))
                    return vv * 10000 if vv <= 1 else vv
                except: continue
        return None

    # --- Interfaz de Usuario (Pestaña 3) ---
    st.subheader("1. Cargar archivo de datos de Pares")
    uploaded_file_tab3 = st.file_uploader("Sube tu archivo CSV.", type="csv", key="uploader_tab3")

    if uploaded_file_tab3 is not None:
        try:
            df_tokens_tab3 = pd.read_csv(uploaded_file_tab3, dtype=str)
            needed_cols_tab3 = ["dex", "pair", "tokenaddress", "quotetokenaddress"]
            if not all(c in df_tokens_tab3.columns for c in needed_cols_tab3):
                st.error(f"El CSV debe contener las columnas: {', '.join(needed_cols_tab3)}")
            else:
                df_gliquid_tab3 = df_tokens_tab3[df_tokens_tab3["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])
                if df_gliquid_tab3.empty:
                    st.warning("No se encontraron pares 'gliquid' en el archivo.")
                else:
                    st.subheader("2. Seleccionar Pares y Montos")
                    pair_options = df_gliquid_tab3['pair'].unique()
                    selected_pairs_tab3 = st.multiselect("Selecciona Pares a analizar:", pair_options, default=pair_options[0] if len(pair_options) > 0 else None)
                    amounts_input_tab3 = st.text_input("Define montos a simular (separados por coma):", "100, 1000, 10000", key="amounts_tab3")

                    if st.button("🚀 Iniciar Simulación de Rutas"):
                        try:
                            amounts = [float(x.strip()) for x in amounts_input_tab3.split(',')]
                            if not amounts: raise ValueError("Lista de montos vacía.")
                        except:
                            st.error("Error en formato de montos.")
                            st.stop()

                        df_to_analyze = df_gliquid_tab3[df_gliquid_tab3['pair'].isin(selected_pairs_tab3)]
                        out_rows = []
                        log_area = st.empty()
                        progress_bar = st.progress(0.0)

                        with st.spinner("Realizando simulación de rutas..."):
                            for i, row in enumerate(df_to_analyze.itertuples()):
                                log_area.info(f"Analizando par: {row.pair} ({i+1}/{len(df_to_analyze)})")
                                for inv, (tA, tB) in (("NO", (row.tokenaddress, row.quotetokenaddress)), ("YES", (row.quotetokenaddress, row.tokenaddress))):
                                    for amt in amounts:
                                        time.sleep(PAUSE_BETWEEN_REQS_TAB3)
                                        try:
                                            resp = call_route_tab3(tA, tB, amt, log_area)
                                            routes = resp.get("routes", []) or ([{"hops": resp.get("execution", {}).get("details", {}).get("hopSwaps", [])}] if "execution" in resp else [])
                                            for idx, r in enumerate(routes):
                                                flat_hops = [item for sublist in r.get("hops", []) for item in (sublist if isinstance(sublist, list) else [sublist])]
                                                parsed_hops = []
                                                total_fee = Decimal(0)
                                                for hop in flat_hops:
                                                    proto = hop.get("routerName", str(hop.get("routerIndex", "")))
                                                    amt_hr = normalize_raw_amount_tab3(hop.get("amountIn"))
                                                    fee_bps = detect_fee_bps_from_hop(hop) or DEFAULT_FEE_BPS
                                                    if proto in SPECIAL_PROTOCOLS_TAB3: fee_bps /= 100
                                                    fee_amt = (amt_hr * fee_bps / 10000) if amt_hr else None
                                                    if fee_amt: total_fee += fee_amt
                                                    parsed_hops.append({"protocol": proto, "amount": str(amt_hr), "price_impact": hop.get("priceImpact", ""), "fee_bps": str(fee_bps), "fee_amount": str(fee_amt)})
                                                out_rows.append({"pair": row.pair, "inverse": inv, "amount_requested": amt, "route_index": idx, "total_fee": str(total_fee), "hops_data": parsed_hops})
                                        except Exception as e:
                                            st.warning(f"Error en {row.pair} (monto {amt}): {e}")
                                progress_bar.progress((i + 1) / len(df_to_analyze))

                        if not out_rows:
                            st.error("La simulación no produjo resultados.")
                        else:
                            st.balloons()
                            st.success("🎉 ¡Simulación completada!")
                            df_out = pd.DataFrame(out_rows)
                            max_hops = max(len(h) for h in df_out['hops_data']) if not df_out.empty else 0
                            for k in range(max_hops):
                                for col in ["protocol", "amount", "price_impact", "fee_bps", "fee_amount"]:
                                    df_out[f"{col}_route_{k+1}"] = df_out['hops_data'].apply(lambda hops: hops[k].get(col) if len(hops) > k else None)
                            df_out = df_out.drop(columns=['hops_data'])
                            st.dataframe(df_out)
                            st.download_button("📥 Descargar resultados en CSV", df_out.to_csv(index=False).encode('utf-8'), "Simulacion_Rutas.csv", "text/csv")
        except Exception as e:
            st.error(f"No se pudo procesar el archivo CSV. Error: {e}")
