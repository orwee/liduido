import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from decimal import Decimal, getcontext
import time

# --- Configuración General de la Página ---
st.set_page_config(
    page_title="Herramientas de Análisis DeFi",
    page_icon="🛠️",
    layout="wide"
)
st.title("🛠️ Herramientas de Análisis DeFi para HyperEVM")

# --- Configuración de Precisión Decimal ---
getcontext().prec = 48

# --- Definición de las Pestañas ---
tab1, tab2, tab3 = st.tabs([
    "📈 Análisis Histórico APY",
    "💧 Calculadora de Price Impact",
    "🛤️ Simulador de Rutas"
])

# ==============================================================================
# PESTAÑA 1: ANÁLISIS HISTÓRICO APY
# ==============================================================================
with tab1:
    st.header("Análisis Histórico de APY y Simulación de Tier")
    st.markdown("""
    Sube un archivo CSV con datos históricos de pools. La herramienta te permitirá:
    1.  Visualizar la evolución del APY de diferentes pools.
    2.  Simular cómo habría rendido el mejor pool de `gliquid` cada día con un `Fee Tier` diferente.
    """)

    # --- Funciones de Carga y Procesamiento (Pestaña 1) ---
    def parse_k_m_values_tab1(value):
        """Convierte valores como '10.5K' o '2M' a números."""
        value_str = str(value).strip().upper()
        if value_str.endswith('K'):
            return float(value_str[:-1]) * 1_000
        if value_str.endswith('M'):
            return float(value_str[:-1]) * 1_000_000
        return pd.to_numeric(value, errors='coerce')

    @st.cache_data(ttl=3600)
    def load_historical_data(uploaded_file):
        """Carga y procesa el CSV de datos históricos."""
        if uploaded_file is None:
            return pd.DataFrame()
        try:
            df = pd.read_csv(uploaded_file)
            df.columns = [col.lower() for col in df.columns]

            if 'date' not in df.columns:
                st.error("El CSV debe contener una columna 'date'.")
                return pd.DataFrame()
            df['date'] = pd.to_datetime(df['date'])

            cols_to_parse = ['volume_24h', 'volume_6h', 'volume_1h', 'fees_24h']
            for col in cols_to_parse:
                if col in df.columns:
                    df[col] = df[col].apply(parse_k_m_values_tab1)

            numeric_cols = ['tvl', 'apy_24h', 'tier']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            df.fillna(0, inplace=True)

            if 'blockchain' in df.columns:
                df['blockchain'] = df['blockchain'].str.lower()
                df = df[df['blockchain'] == 'hyperevm']
            
            return df
        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")
            return pd.DataFrame()

    # --- Interfaz de Usuario (Pestaña 1) ---
    uploaded_file_tab1 = st.file_uploader("Sube tu archivo de datos históricos (.csv)", type="csv", key="uploader_tab1")
    historical_df = load_historical_data(uploaded_file_tab1)

    if not historical_df.empty:
        st.subheader("1. Simulación para 'gliquid_test'")
        simulated_tier = st.slider(
            "Selecciona el Fee Tier para la simulación:",
            min_value=0.01, max_value=5.0, value=1.0, step=0.05, format="%.2f%%", key="slider_tab1"
        )

        required_columns = ['dex', 'volume_24h', 'tvl', 'apy_24h', 'pair']
        if not all(col in historical_df.columns for col in required_columns):
            st.error(f"El CSV debe contener las siguientes columnas: {', '.join(required_columns)}")
        else:
            st.subheader("2. Análisis y Comparativa")
            all_pairs = sorted(historical_df['pair'].str.lower().unique())
            default_selection = [p for p in all_pairs if "khype/whype" in p.lower()] if any("khype/whype" in p.lower() for p in all_pairs) else []
            
            selected_pairs = st.multiselect(
                "Selecciona los Pairs a visualizar:",
                options=all_pairs,
                default=default_selection,
                key="multiselect_tab1"
            )

            if selected_pairs:
                filtered_df = historical_df[historical_df['pair'].str.lower().isin([p.lower() for p in selected_pairs])].copy()
                gliquid_df = filtered_df[filtered_df['dex'].str.lower() == 'gliquid'].copy()
                other_dex_df = filtered_df[filtered_df['dex'].str.lower() != 'gliquid'].copy()
                
                best_gliquid_df = pd.DataFrame()
                if not gliquid_df.empty:
                    best_gliquid_indices = gliquid_df.groupby(['date', 'pair'])['apy_24h'].idxmax()
                    best_gliquid_df = gliquid_df.loc[best_gliquid_indices].copy()
                    best_gliquid_df['dex'] = 'gliquid (best)'

                all_simulation_rows = []
                if not best_gliquid_df.empty:
                    for _, best_row in best_gliquid_df.iterrows():
                        daily_tvl = best_row['tvl']
                        daily_volume = best_row['volume_24h']
                        new_apy = (daily_volume * simulated_tier / daily_tvl) * 365 if daily_tvl > 0 else 0
                        
                        new_row = best_row.copy()
                        new_row['dex'] = 'gliquid_test'
                        new_row['tier'] = simulated_tier
                        new_row['apy_24h'] = new_apy
                        all_simulation_rows.append(new_row)

                chart_df = pd.concat([other_dex_df, best_gliquid_df], ignore_index=True)
                if all_simulation_rows:
                    chart_df = pd.concat([chart_df, pd.DataFrame(all_simulation_rows)], ignore_index=True)

                chart_df['apy_24h'] *= 100  # convertir a porcentaje
                chart_df['identifier'] = chart_df['pair'] + " (" + chart_df['dex'] + ", Tier: " + chart_df['tier'].round(2).astype(str) + "%)"
                
                if st.checkbox("Mostrar tabla de datos del gráfico", value=True, key="checkbox_tab1"):
                    display_df = chart_df[['date', 'pair', 'dex', 'tier', 'tvl', 'volume_24h', 'apy_24h']].copy()
                    display_df['tvl'] = display_df['tvl'].map('{:,.0f}'.format)
                    display_df['volume_24h'] = display_df['volume_24h'].map('{:,.0f}'.format)
                    display_df['apy_24h'] = display_df['apy_24h'].map('{:,.2f}%'.format)
                    st.dataframe(display_df.sort_values(by=['date', 'pair']))

                fig = px.line(
                    chart_df, x='date', y='apy_24h', color='identifier',
                    title="Evolución Histórica del APY por Par",
                    labels={'date': 'Fecha', 'apy_24h': 'APY 24h (%)', 'identifier': 'Pool'},
                    markers=True
                )
                st.plotly_chart(fig, use_container_width=True)

# ==============================================================================
# PESTAÑA 2: CALCULADORA DE PRICE IMPACT
# ==============================================================================
with tab2:
    st.header("Calculadora de Price Impact por Pool")
    st.markdown("""
    Sube un CSV con pares de tokens (`dex`, `pair`, `tokenaddress`, `quotetokenaddress`). 
    La herramienta consultará los pools de `gliquid` para esos pares y simulará swaps con diferentes montos para calcular el impacto en el precio.
    """)

    # --- Funciones (Pestaña 2) ---
    @st.cache_data(ttl=3600)
    def fetch_pools_tab2(tokenA, tokenB):
        r = requests.get("https://api.liqd.ag/pools", params={"tokenA": tokenA, "tokenB": tokenB}, timeout=30)
        r.raise_for_status()
        return r.json().get("data", [])

    @st.cache_data(ttl=3600)
    def call_route_tab2(tokenIn, tokenOut, amountIn, excludeDexes=None):
        params = {"tokenIn": tokenIn, "tokenOut": tokenOut, "amountIn": str(amountIn), "multiHop": "false", "slippage": "1.0"}
        if excludeDexes: params["excludeDexes"] = excludeDexes
        r = requests.get("https://api.liqd.ag/v2/route", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def run_price_impact_analysis(df_pairs, amounts):
        all_rows = []
        st.info(f"Se analizarán {len(df_pairs)} pares. Esto puede tardar varios minutos...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        total_steps = len(df_pairs) * 2 * len(amounts)
        current_step = 0

        for _, r in df_pairs.iterrows():
            pair_name, tA, tB = r["pair"], r["tokenaddress"], r["quotetokenaddress"]
            
            for inverse_flag, (tokenA, tokenB) in (("NO", (tA, tB)), ("YES", (tB, tA))):
                try:
                    pools = fetch_pools_tab2(tokenA, tokenB)
                    if not pools: 
                        continue
                    
                    router_indices = sorted({int(p.get("routerIndex")) for p in pools if p.get("routerIndex") is not None})
                    
                    for p in pools:
                        base_row = {"pair": pair_name, "inverse": inverse_flag, "poolAddress": p.get("poolAddress"), "protocol": p.get("protocol")}
                        routerIndex = int(p.get("routerIndex")) if p.get("routerIndex") is not None else None
                        exclude_str = ",".join([str(x) for x in router_indices if x != routerIndex]) or None

                        for amt in amounts:
                            current_step += 1
                            status_text.text(f"Analizando {pair_name} ({'Inverso' if inverse_flag == 'YES' else 'Normal'}) | Monto: {amt}")
                            try:
                                time.sleep(0.35)
                                resp = call_route_tab2(tokenA, tokenB, amt, excludeDexes=exclude_str)
                                base_row[f"amount_{amt}_avgPriceImpact"] = resp.get("averagePriceImpact", "N/A")
                            except Exception as e:
                                base_row[f"amount_{amt}_avgPriceImpact"] = f"Error: {e}"
                            progress_bar.progress(current_step / total_steps)
                        all_rows.append(base_row)
                except Exception as e:
                    st.warning(f"Error en par {pair_name} ({inverse_flag}): {e}")
        
        status_text.success("¡Análisis de Price Impact completado!")
        return pd.DataFrame(all_rows)

    # --- Interfaz de Usuario (Pestaña 2) ---
    uploaded_file_tab2 = st.file_uploader("Sube tu archivo de datos con pares de tokens (.csv)", type="csv", key="uploader_tab2")
    
    if uploaded_file_tab2:
        df_tokens = pd.read_csv(uploaded_file_tab2, dtype=str)
        needed_cols_tab2 = ["dex", "pair", "tokenaddress", "quotetokenaddress"]
        if not all(c in df_tokens.columns for c in needed_cols_tab2):
            st.error(f"El CSV debe contener las columnas: {', '.join(needed_cols_tab2)}")
        else:
            with st.form("price_impact_form"):
                amounts_str = st.text_input("Montos a simular (separados por coma)", "0.1, 1, 10, 100, 1000, 10000, 100000")
                run_button = st.form_submit_button("🚀 Ejecutar Análisis de Price Impact")

            if run_button:
                amounts = [float(a.strip()) for a in amounts_str.split(',')]
                df_gliquid = df_tokens[df_tokens["dex"] == "Gliquid"].drop_duplicates(subset=["pair"])
                
                if df_gliquid.empty:
                    st.warning("No se encontraron pares con DEX 'Gliquid' en el archivo.")
                else:
                    df_results = run_price_impact_analysis(df_gliquid, amounts)
                    st.dataframe(df_results)
                    csv = df_results.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Descargar Resultados (.csv)", data=csv, file_name="price_impact_results.csv", mime="text/csv")

# ==============================================================================
# PESTAÑA 3: SIMULADOR DE RUTAS
# ==============================================================================
with tab3:
    st.header("Simulador de Rutas de Swap")
    st.markdown("""
    Sube un CSV con pares de tokens. La herramienta simulará la mejor ruta de swap (multi-hop) 
    para diferentes montos, desglosando cada salto, protocolo y comisiones.
    """)

    # --- Funciones (Pestaña 3) ---
    @st.cache_data(ttl=3600)
    def call_route_tab3(tokenIn, tokenOut, amountIn):
        params = {"tokenIn": tokenIn, "tokenOut": tokenOut, "amountIn": str(amountIn), "multiHop": "true", "slippage": "1.0"}
        r = requests.get("https://api.liqd.ag/v2/route", params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def run_route_simulation(df_pairs, amounts):
        out_rows = []
        st.info(f"Se simularán rutas para {len(df_pairs)} pares. Esto puede tardar...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        total_steps = len(df_pairs) * 2 * len(amounts)
        current_step = 0

        for _, row_pair in df_pairs.iterrows():
            pair_name, tA, tB = row_pair["pair"], row_pair["tokenaddress"], row_pair["quotetokenaddress"]

            for inverse_flag, (tokenA, tokenB) in (("NO", (tA, tB)), ("YES", (tB, tA))):
                for amt in amounts:
                    current_step += 1
                    status_text.text(f"Simulando: {pair_name} ({'Inverso' if inverse_flag == 'YES' else 'Normal'}) | Monto: {amt}")
                    
                    try:
                        time.sleep(0.35)
                        resp = call_route_tab3(tokenA, tokenB, amt)
                        
                        row = {"pair": pair_name, "inverse": inverse_flag, "amount_requested": amt}
                        hopSwaps = resp.get("execution", {}).get("details", {}).get("hopSwaps", [])
                        
                        if hopSwaps:
                            for i, hop in enumerate(hopSwaps):
                                for j, swap in enumerate(hop):
                                    row[f"hop_{i+1}_protocol"] = swap.get("routerName", swap.get("routerIndex"))
                                    row[f"hop_{i+1}_amountIn"] = swap.get("amountIn")
                                    row[f"hop_{i+1}_priceImpact"] = swap.get("priceImpact")
                        out_rows.append(row)
                    except Exception as e:
                        out_rows.append({"pair": pair_name, "inverse": inverse_flag, "amount_requested": amt, "error": str(e)})
                    progress_bar.progress(current_step / total_steps)
        
        status_text.success("¡Simulación de rutas completada!")
        return pd.DataFrame(out_rows)

    # --- Interfaz de Usuario (Pestaña 3) ---
    uploaded_file_tab3 = st.file_uploader("Sube tu archivo de datos con pares de tokens (.csv)", type="csv", key="uploader_tab3")

    if uploaded_file_tab3:
        df_tokens_tab3 = pd.read_csv(uploaded_file_tab3, dtype=str)
        needed_cols_tab3 = ["dex", "pair", "tokenaddress", "quotetokenaddress"]
        if not all(c in df_tokens_tab3.columns for c in needed_cols_tab3):
            st.error(f"El CSV debe contener las columnas: {', '.join(needed_cols_tab3)}")
        else:
            with st.form("route_simulator_form"):
                amounts_str_tab3 = st.text_input("Montos a simular (separados por coma)", "0.1, 1, 10, 100, 1000", key="amounts_tab3")
                run_button_tab3 = st.form_submit_button("🚀 Ejecutar Simulación de Rutas")

            if run_button_tab3:
                amounts_tab3 = [float(a.strip()) for a in amounts_str_tab3.split(',')]
                df_gliquid_tab3 = df_tokens_tab3[df_tokens_tab3["dex"] == "Gliquid"].drop_duplicates(subset=["pair"])

                if df_gliquid_tab3.empty:
                    st.warning("No se encontraron pares con DEX 'Gliquid' en el archivo.")
                else:
                    df_results_tab3 = run_route_simulation(df_gliquid_tab3, amounts_tab3)
                    st.dataframe(df_results_tab3)
                    csv_tab3 = df_results_tab3.to_csv(index=False).encode('utf-8')
                    st.download_button("📥 Descargar Resultados (.csv)", data=csv_tab3, file_name="route_simulation_results.csv", mime="text/csv", key="download_tab3")
