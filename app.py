import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime
import requests
from decimal import Decimal, getcontext
from pathlib import Path
import time
import io

# --- Configuración General de la Página ---
st.set_page_config(
    page_title="Análisis Gliquid",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Panel de Análisis de Gliquid")
st.markdown("Navega entre el análisis histórico de APY y el análisis de Price Impact usando las pestañas.")

# --- Creación de Pestañas ---
tab1, tab2 = st.tabs(["Análisis Histórico APY", "Análisis de Price Impact"])

# ==============================================================================
# Contenido de la Pestaña 1: ANÁLISIS HISTÓRICO APY (Tu código original)
# ==============================================================================
with tab1:
    st.header("📈 Análisis Histórico de APY para HyperEVM")
    st.markdown("Esta sección carga datos históricos (10-16 ago 2025), los filtra por la blockchain **hyperevm** y permite analizar el APY por par, incluyendo una simulación dinámica.")

    # --- Funciones de Carga y Procesamiento ---

    def parse_k_m_values(value):
        """
        Convierte un valor de string con sufijo 'K' (miles) o 'M' (millones) a un número flotante.
        """
        value_str = str(value).strip().upper()
        if value_str.endswith('K'):
            return float(value_str[:-1]) * 1_000
        if value_str.endswith('M'):
            return float(value_str[:-1]) * 1_000_000
        return pd.to_numeric(value, errors='coerce')

    @st.cache_data(ttl=600)
    def load_all_data(data_folder="data"):
        """
        Carga archivos CSV de un rango de fechas (2025), los combina y filtra por blockchain.
        """
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
            except ValueError:
                continue
            except Exception as e:
                st.warning(f"No se pudo procesar el archivo: {filename}. Error: {e}")
        
        if not all_data:
            st.warning("No se encontraron archivos CSV en el rango de fechas especificado (10-ago-2025 a 16-ago-2025).")
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

    # --- Interfaz de Usuario ---
    st.subheader("1. Simulación para 'gliquid_test'")
    simulated_tier = st.slider(
        "Selecciona el Fee Tier para la simulación:",
        min_value=0.01, max_value=5.0, value=1.0, step=0.05, format="%.2f%%"
    )

    # --- Lógica Principal ---
    historical_df, loaded_files = load_all_data()

    if loaded_files:
        with st.expander("Ver archivos cargados"):
            st.write(loaded_files)

    if not historical_df.empty:
        required_columns = ['address', 'dex', 'volume_24h', 'tvl', 'apy_24h', 'pair']
        missing_columns = [col for col in required_columns if col not in historical_df.columns]
        
        if missing_columns:
            st.error(f"Error: Faltan columnas en tus CSVs: **{', '.join(missing_columns)}**.")
            st.info(f"Columnas encontradas (en minúsculas): **{', '.join(historical_df.columns)}**")
            st.stop()

        st.subheader("2. Análisis y Comparativa")
        
        all_pairs = sorted(historical_df['pair'].str.lower().unique())
        default_selection = ['khype/whype'] if 'khype/whype' in all_pairs else []
        
        selected_pairs = st.multiselect(
            "Selecciona los Pairs a visualizar:",
            options=all_pairs,
            default=default_selection
        )

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
                for index, best_row_for_day in best_gliquid_df.iterrows():
                    daily_tvl = best_row_for_day['tvl']
                    daily_volume = best_row_for_day['volume_24h']
                    
                    # Se usa la fórmula: volumen * (tier/100) / tvl * 365
                    new_apy = (daily_volume * (simulated_tier / 100) / daily_tvl) * 365 if daily_tvl > 0 else 0
                    
                    new_row = best_row_for_day.copy()
                    new_row['dex'] = 'gliquid_test'
                    new_row['tier'] = simulated_tier
                    new_row['apy_24h'] = new_apy * 100 # Se multiplica por 100 para que sea porcentual
                    all_simulation_rows.append(new_row)

            chart_df = pd.concat([other_dex_df, best_gliquid_df], ignore_index=True)
            if all_simulation_rows:
                gliquid_test_df = pd.DataFrame(all_simulation_rows)
                chart_df = pd.concat([chart_df, gliquid_test_df], ignore_index=True)

            chart_df['identifier'] = chart_df['pair'].astype(str) + " (" + chart_df['dex'] + ", Tier: " + chart_df['tier'].round(2).astype(str) + "%)"
            
            if st.checkbox("Mostrar tabla de datos del gráfico", value=True):
                display_df = chart_df[['date', 'pair', 'dex', 'tier', 'tvl', 'volume_24h', 'apy_24h']].copy()
                display_df['tvl'] = display_df['tvl'].astype(int)
                display_df['volume_24h'] = display_df['volume_24h'].astype(int)
                display_df['apy_24h'] = display_df['apy_24h'].map('{:,.2f}%'.format)
                st.dataframe(display_df.sort_values(by=['date', 'pair']))

            fig = px.line(
                chart_df,
                x='date',
                y='apy_24h',
                color='identifier',
                title="Evolución Histórica del APY por Par",
                labels={'date': 'Fecha', 'apy_24h': 'APY 24h (%)', 'identifier': 'Pool'},
                markers=True
            )
            fig.update_layout(legend_title_text='Identificador del Pool')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Selecciona al menos un par para generar el gráfico.")
    else:
        st.info("Esperando a que se carguen los datos...")


# ==============================================================================
# Contenido de la Pestaña 2: ANÁLISIS DE PRICE IMPACT (Nuevo script)
# ==============================================================================
with tab2:
    st.header("💧 Análisis de Price Impact para Pools de Gliquid")
    st.markdown("Esta herramienta consulta la API de `liqd.ag` para analizar el impacto en el precio para diferentes volúmenes de trade en los pools de Gliquid.")

    # --- Configuración del script ---
    getcontext().prec = 36
    AMOUNTS = [0.1, 1, 10, 100, 1000, 10000, 100000]
    BASE_POOLS_URL = "https://api.liqd.ag/pools"
    BASE_ROUTE_URL = "https://api.liqd.ag/v2/route"
    PAUSE_BETWEEN_REQS = 0.35
    SPECIAL_PROTOCOLS = {"HyperSwapV2", "LaminarV3", "HybraFinanceV3", "ProjectX"}

    # --- Funciones de Utilidad (adaptadas para Streamlit) ---
    def parse_pct_str_to_fraction(s):
        if s is None: return None
        if isinstance(s, (int, float, Decimal)):
            try: return Decimal(str(s)) / Decimal(100)
            except Exception: return None
        s2 = str(s).strip()
        if s2.endswith("%"): s2 = s2[:-1]
        try: return Decimal(s2) / Decimal(100)
        except Exception: return None

    def show_prepared_url(method, url, params, log_area):
        sess = requests.Session()
        req = requests.Request(method, url, params=params)
        pre = sess.prepare_request(req)
        log_area.info(f"🔗 URL consultada: {pre.url}")
        return pre.url

    def normalize_raw_amount(raw_amt, token_addr, decimals_map):
        if raw_amt is None: return None
        try:
            s = str(raw_amt)
            if token_addr:
                key = token_addr.lower()
                if key in decimals_map and decimals_map[key] is not None:
                    dec = int(decimals_map[key])
                    return Decimal(s) / (Decimal(10) ** dec)
            if "." in s: return Decimal(s)
            if len(s) > 18: return Decimal(s) / (Decimal(10) ** 18)
            return Decimal(s)
        except Exception:
            try: return Decimal(str(raw_amt))
            except Exception: return None

    # --- Funciones de API (adaptadas para Streamlit) ---
    def fetch_pools(tokenA, tokenB, log_area):
        params = {"tokenA": tokenA, "tokenB": tokenB}
        log_area.info("Consultando pools...")
        show_prepared_url('GET', BASE_POOLS_URL, params, log_area)
        r = requests.get(BASE_POOLS_URL, params=params, timeout=30)
        r.raise_for_status()
        j = r.json()
        if isinstance(j, dict) and j.get("success") is False: raise RuntimeError(f"Error fetching pools: {j}")
        if isinstance(j, dict) and "data" in j: return j.get("data", [])
        if isinstance(j, list): return j
        raise RuntimeError("Respuesta inesperada de /pools")

    def call_route(tokenIn, tokenOut, amountIn, log_area, excludeDexes=None, multiHop=False, slippage=1.0):
        params = {"tokenIn": tokenIn, "tokenOut": tokenOut, "amountIn": str(amountIn), "multiHop": str(bool(multiHop)).lower(), "slippage": str(slippage)}
        if excludeDexes: params["excludeDexes"] = excludeDexes
        log_area.info(f"Consultando ruta para un monto de {amountIn}...")
        show_prepared_url('GET', BASE_ROUTE_URL, params, log_area)
        r = requests.get(BASE_ROUTE_URL, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    # --- Función principal de análisis (adaptada para Streamlit) ---
    def analyze_pair(tokenA, tokenB, pair_name, inverse_flag, log_area, progress_bar):
        rows = []
        try:
            pools = fetch_pools(tokenA, tokenB, log_area)
        except Exception as e:
            st.warning(f"Error al obtener pools para {pair_name} ({tokenA}/{tokenB}): {e}")
            return rows

        if not pools:
            log_area.warning(f"No se encontraron pools para {pair_name} ({tokenA}/{tokenB}).")
            return rows

        router_indices = sorted({int(p.get("routerIndex")) for p in pools if p.get("routerIndex") is not None})
        log_area.info(f"Routers detectados: {router_indices}")

        for i, p in enumerate(pools):
            progress_bar.progress((i + 1) / len(pools))
            
            poolAddress = p.get("poolAddress")
            routerIndex = int(p.get("routerIndex")) if p.get("routerIndex") is not None else None
            protocol = p.get("protocol")
            log_area.info(f"--- Analizando Pool: {poolAddress} | Protocolo: {protocol} ---")

            fee_bps_orig = p.get("fee")
            try: fee_bps_orig_d = Decimal(str(fee_bps_orig)) if fee_bps_orig is not None else Decimal(0)
            except Exception: fee_bps_orig_d = Decimal(0)
            
            fee_bps_adj = fee_bps_orig_d / Decimal(100) if protocol in SPECIAL_PROTOCOLS else fee_bps_orig_d
            fee_fraction_pool = (fee_bps_adj / Decimal(10000)) if fee_bps_adj is not None else Decimal(0)

            other_indices = [str(x) for x in router_indices if x != routerIndex]
            exclude_str = ",".join(other_indices) if other_indices else None

            base_row = {
                "pair": pair_name, "pair_tokenA": tokenA, "pair_tokenB": tokenB, "inverse": inverse_flag,
                "poolAddress": poolAddress, "protocol": protocol, "routerIndex": routerIndex,
                "feeBps_original": str(fee_bps_orig_d), "feeBps_adj": str(fee_bps_adj),
                "fee_Tier": str(fee_fraction_pool),
            }

            for amt in AMOUNTS:
                col_avg = f"amount_{amt}_avgPriceImpact"
                base_row[col_avg] = "missing"
                time.sleep(PAUSE_BETWEEN_REQS)
                try:
                    resp = call_route(tokenA, tokenB, amt, log_area, excludeDexes=exclude_str)
                    avgPriceImpact_str = resp.get("averagePriceImpact")
                    if avgPriceImpact_str is not None:
                        p_frac = parse_pct_str_to_fraction(avgPriceImpact_str)
                        if p_frac is not None and p_frac != Decimal(0):
                            base_row[col_avg] = avgPriceImpact_str
                except Exception as e:
                    log_area.warning(f"Error en simulación (monto={amt}, pool={poolAddress}): {e}")
            
            rows.append(base_row)
        return rows

    # --- Interfaz de la Pestaña 2 ---
    st.subheader("1. Cargar archivo de datos de Pares")
    uploaded_file = st.file_uploader(
        "Sube tu archivo CSV con los pares de Gliquid (debe contener las columnas 'dex', 'pair', 'tokenaddress', 'quotetokenaddress').",
        type="csv"
    )

    if uploaded_file is not None:
        if st.button("🚀 Iniciar Análisis de Price Impact"):
            df_tokens = pd.read_csv(uploaded_file, dtype=str)
            
            needed_cols = ["dex", "pair", "tokenaddress", "quotetokenaddress"]
            if not all(c in df_tokens.columns for c in needed_cols):
                st.error(f"El CSV debe contener las columnas: {', '.join(needed_cols)}")
            else:
                df_gliquid = df_tokens[df_tokens["dex"].astype(str) == "gliquid"].drop_duplicates(subset=["pair"]).reset_index(drop=True)
                
                if df_gliquid.empty:
                    st.warning("No se encontraron pares con 'dex' igual a 'Gliquid' en el archivo.")
                else:
                    st.success(f"Se encontraron {len(df_gliquid)} pares únicos de Gliquid para analizar.")
                    
                    all_rows = []
                    log_area = st.empty()
                    main_progress = st.progress(0.0)

                    with st.spinner("Realizando análisis... Esto puede tardar varios minutos."):
                        total_pairs = len(df_gliquid)
                        for idx, r in df_gliquid.iterrows():
                            pair_name, tokenA, tokenB = r["pair"], r["tokenaddress"], r["quotetokenaddress"]
                            
                            st.markdown(f"--- \n### Analizando Par: **{pair_name}** ({idx + 1}/{total_pairs})")
                            pair_progress = st.progress(0.0)
                            
                            # Normal
                            log_area.info(f"Ejecutando {pair_name}: {tokenA} / {tokenB} (inverse=NO)")
                            rows_normal = analyze_pair(tokenA, tokenB, pair_name, "NO", log_area, pair_progress)
                            all_rows.extend(rows_normal)
                            
                            # Inverso
                            log_area.info(f"Ejecutando {pair_name}: {tokenB} / {tokenA} (inverse=YES)")
                            rows_inverse = analyze_pair(tokenB, tokenA, pair_name, "YES", log_area, pair_progress)
                            all_rows.extend(rows_inverse)

                            main_progress.progress((idx + 1) / total_pairs)

                    if not all_rows:
                        st.error("El análisis no produjo resultados. Revisa los logs o el archivo de entrada.")
                    else:
                        st.balloons()
                        st.success("🎉 ¡Análisis completado!")
                        df_res = pd.DataFrame(all_rows)

                        # Ordenar y asegurar columnas
                        amount_cols = [f"amount_{amt}_avgPriceImpact" for amt in AMOUNTS]
                        meta_cols = ["pair", "pair_tokenA", "pair_tokenB", "inverse", "poolAddress", "protocol", "routerIndex", "fee_Tier"]
                        final_cols = meta_cols + amount_cols
                        for c in final_cols:
                            if c not in df_res.columns: df_res[c] = None
                        df_res = df_res[final_cols]
                        
                        st.subheader("2. Resultados del Análisis")
                        st.dataframe(df_res)
                        
                        # Botón de descarga
                        csv_buffer = io.StringIO()
                        df_res.to_csv(csv_buffer, index=False, encoding="utf-8")
                        
                        st.download_button(
                            label="📥 Descargar resultados en CSV",
                            data=csv_buffer.getvalue(),
                            file_name=f"Pools_Price_Impacts_Gliquid_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
