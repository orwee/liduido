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
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Carga, combina y procesa archivos CSV de un directorio dentro de un rango de fechas.
    Filtra los datos para la blockchain 'hyperevm'.

    Args:
        data_folder: La ruta a la carpeta que contiene los archivos CSV.
        start_date: La fecha de inicio para el filtro.
        end_date: La fecha de fin para el filtro.

    Returns:
        Un DataFrame de pandas con los datos combinados y una lista de los archivos cargados.
    """
    all_data = []
    loaded_files = []

    if not os.path.isdir(data_folder):
        st.error(f"Error: No se encontró la carpeta '{data_folder}'.")
        return pd.DataFrame(), []

    filenames = sorted([f for f in os.listdir(data_folder) if f.endswith('.csv')])
    if not filenames:
        st.warning(f"No se encontraron archivos .csv en la carpeta '{data_folder}'.")
        return pd.DataFrame(), []

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
        except (ValueError, FileNotFoundError):
            # Ignora archivos que no tengan el formato de fecha esperado o no se puedan leer
            continue

    if not all_data:
        st.warning("No se encontraron archivos CSV en el rango de fechas especificado.")
        return pd.DataFrame(), []

    # Combina y procesa el DataFrame
    combined_df = pd.concat(all_data, ignore_index=True)
    combined_df.columns = [col.strip().lower() for col in combined_df.columns]

    # Procesa columnas con sufijos 'K'/'M'
    for col in ['volume_24h', 'volume_6h', 'volume_1h', 'fees_24h']:
        if col in combined_df.columns:
            combined_df[col] = combined_df[col].apply(parse_k_m_values)

    # Convierte columnas a numérico
    for col in ['tvl', 'apy_24h', 'tier']:
        if col in combined_df.columns:
            combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce')

    combined_df = combined_df.fillna(0)

    # Filtra por blockchain
    if 'blockchain' in combined_df.columns:
        combined_df['blockchain'] = combined_df['blockchain'].str.lower()
        combined_df = combined_df[combined_df['blockchain'] == 'hyperevm']
    else:
        st.error("La columna 'blockchain' es necesaria pero no se encontró.")
        return pd.DataFrame(), loaded_files

    return combined_df, loaded_files


# ------------------------------------------------------------------------------
# Funciones para las Pestañas 2 y 3: Simulación y API
# ------------------------------------------------------------------------------

def call_api(endpoint: str, params: Dict[str, Any], log_area: st.container) -> Dict[str, Any]:
    """
    Realiza una llamada a la API de Gliquid y devuelve la respuesta JSON.

    Args:
        endpoint: El endpoint de la API a consultar (p. ej., '/pools').
        params: Un diccionario con los parámetros de la petición.
        log_area: El contenedor de Streamlit para mostrar logs.

    Returns:
        La respuesta de la API como un diccionario.
    """
    url = f"{API_BASE_URL}{endpoint}"
    log_area.info(f"🔗 Consultando API: {url} con parámetros: {params}")
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()  # Lanza una excepción para errores HTTP (4xx o 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        log_area.error(f"Error en la llamada a la API: {e}")
        return {}


def analyze_pair_price_impact(
    token_a: str, token_b: str, pair_name: str, inverse: bool, amounts: List[float], log_area: st.container
) -> List[Dict[str, Any]]:
    """
    Analiza el price impact para un par de tokens en ambas direcciones.

    Args:
        token_a: Dirección del primer token.
        token_b: Dirección del segundo token.
        pair_name: Nombre del par para mostrar en los resultados.
        inverse: Flag para indicar si la dirección es B -> A.
        amounts: Lista de montos a simular.
        log_area: Contenedor de Streamlit para logs.

    Returns:
        Una lista de diccionarios, cada uno representando los resultados para un pool.
    """
    results = []
    pools_response = call_api("/pools", {"tokenA": token_a, "tokenB": token_b}, log_area)
    pools = pools_response.get("data", [])

    if not pools:
        log_area.warning(f"No se encontraron pools para {pair_name}.")
        return []

    # Obtiene todos los índices de routers para poder excluirlos selectivamente
    router_indices = sorted({int(p["routerIndex"]) for p in pools if p.get("routerIndex") is not None})

    for pool in pools:
        pool_address = pool.get("poolAddress")
        protocol = pool.get("protocol")
        router_index = pool.get("routerIndex")
        log_area.info(f"--- Analizando Pool: {pool_address} ({protocol}) ---")

        # Excluye todos los routers excepto el actual para aislar el análisis
        exclude_dexes = ",".join([str(idx) for idx in router_indices if idx != int(router_index)])
        
        row_data = {"pair": pair_name, "inverse": "YES" if inverse else "NO", "poolAddress": pool_address, "protocol": protocol}

        for amount in amounts:
            time.sleep(PAUSE_BETWEEN_REQUESTS)
            route_params = {
                "tokenIn": token_a, "tokenOut": token_b, "amountIn": str(amount),
                "multiHop": "false", "slippage": "1.0", "excludeDexes": exclude_dexes
            }
            route_response = call_api("/v2/route", route_params, log_area)
            
            col_name = f"amount_{amount}_avgPriceImpact"
            row_data[col_name] = route_response.get("averagePriceImpact", "N/A")
        
        results.append(row_data)
        
    return results


def normalize_raw_amount(raw_amt: Any) -> Optional[Decimal]:
    """Normaliza un monto 'raw', usualmente dividiendo por 10**18."""
    if raw_amt is None:
        return None
    try:
        s_amt = str(raw_amt)
        # Asume 18 decimales si no hay punto decimal
        return Decimal(s_amt) / (Decimal(10) ** 18)
    except Exception:
        return None


def detect_fee_bps_from_hop(hop_data: Dict[str, Any]) -> Optional[Decimal]:
    """Extrae la comisión en BPS de un 'hop' de la respuesta de la API."""
    fee_keys = ["feeBps", "fee", "feePercent", "poolFeeBps"]
    for key in fee_keys:
        if (value := hop_data.get(key)) is not None:
            try:
                # Convierte porcentajes a BPS
                if "%" in str(value):
                    return (Decimal(str(value).strip('%')) / 100) * 10000
                
                decimal_value = Decimal(str(value))
                # Si el valor es pequeño (ej. 0.003), asume que es una tasa directa y conviértelo a BPS
                return decimal_value * 10000 if decimal_value <= 1 else decimal_value
            except Exception:
                continue
    return None


# ==============================================================================
# 3. INTERFAZ DE USUARIO (STREAMLIT)
# ==============================================================================

def setup_page():
    """Configura los ajustes generales de la página de Streamlit."""
    st.set_page_config(
        page_title="Análisis Gliquid",
        page_icon="📊",
        layout="wide"
    )
    st.title("📊 Panel de Análisis Gliquid")
    st.markdown("Navega entre las diferentes herramientas de análisis usando las pestañas.")


def display_historical_apy_tab():
    """Muestra el contenido de la pestaña 'Análisis Histórico APY'."""
    st.header("📈 Análisis Histórico de APY para HyperEVM")
    st.markdown("Carga datos históricos, los filtra por la blockchain **hyperevm** y permite analizar el APY por par, incluyendo una simulación dinámica.")

    # --- Controles del Usuario ---
    st.subheader("1. Configuración de Datos y Simulación")
    col1, col2 = st.columns(2)
    with col1:
        start_date_input = st.date_input("Fecha de inicio", datetime(2025, 8, 10).date())
    with col2:
        end_date_input = st.date_input("Fecha de fin", datetime(2025, 8, 16).date())

    simulated_tier = st.slider(
        "Selecciona el Fee Tier para la simulación de 'gliquid_test':",
        min_value=0.01, max_value=5.0, value=1.0, step=0.05, format="%.2f%%"
    )

    # --- Carga y Procesamiento de Datos ---
    historical_df, loaded_files = load_and_process_historical_data(DATA_FOLDER, start_date_input, end_date_input)

    if loaded_files:
        with st.expander("Ver archivos cargados"):
            st.write(loaded_files)

    if historical_df.empty:
        st.info("Esperando a que se carguen los datos o selecciona un rango de fechas con datos.")
        return

    required_columns = ['dex', 'volume_24h', 'tvl', 'apy_24h', 'pair']
    if not all(col in historical_df.columns for col in required_columns):
        st.error(f"Error: Faltan columnas esenciales en los CSVs. Se necesitan: {', '.join(required_columns)}")
        return

    # --- Visualización y Gráficos ---
    st.subheader("2. Análisis y Comparativa")
    all_pairs = sorted(historical_df['pair'].str.lower().unique())
    selected_pairs = st.multiselect("Selecciona los Pairs a visualizar:", options=all_pairs, default=all_pairs[0] if all_pairs else [])

    if not selected_pairs:
        st.info("Selecciona al menos un par para generar el gráfico.")
        return
        
    # --- Lógica de filtrado y simulación ---
    filtered_df = historical_df[historical_df['pair'].str.lower().isin(selected_pairs)].copy()
    gliquid_df = filtered_df[filtered_df['dex'].str.lower() == 'gliquid'].copy()
    other_dex_df = filtered_df[filtered_df['dex'].str.lower() != 'gliquid'].copy()

    # Selecciona solo el mejor APY de Gliquid por día y par
    best_gliquid_df = pd.DataFrame()
    if not gliquid_df.empty:
        best_gliquid_indices = gliquid_df.loc[gliquid_df.groupby(['date', 'pair'])['apy_24h'].idxmax()]
        best_gliquid_df = best_gliquid_indices.copy()
        best_gliquid_df['dex'] = 'gliquid (best)'

    # Genera datos simulados basados en el mejor Gliquid
    simulation_rows = []
    if not best_gliquid_df.empty:
        sim_df = best_gliquid_df.copy()
        sim_df['apy_24h'] = sim_df.apply(
            lambda row: ((row['volume_24h'] * (simulated_tier / 100)) / row['tvl'] * 365 * 100) if row['tvl'] > 0 else 0,
            axis=1
        )
        sim_df['dex'] = 'gliquid_test'
        sim_df['tier'] = simulated_tier
        simulation_rows = sim_df.to_dict('records')

    # Combina todos los datos para el gráfico
    chart_df = pd.concat([other_dex_df, best_gliquid_df, pd.DataFrame(simulation_rows)], ignore_index=True)
    chart_df['identifier'] = chart_df.apply(
        lambda row: f"{row['pair']} ({row['dex']}, Tier: {row['tier']:.2f}%)", axis=1
    )

    if st.checkbox("Mostrar tabla de datos del gráfico", value=True):
        display_cols = ['date', 'pair', 'dex', 'tier', 'tvl', 'volume_24h', 'apy_24h']
        st.dataframe(chart_df[display_cols].sort_values(by=['date', 'pair']))

    fig = px.line(
        chart_df, x='date', y='apy_24h', color='identifier',
        title="Evolución Histórica del APY por Par",
        labels={'date': 'Fecha', 'apy_24h': 'APY 24h (%)', 'identifier': 'Pool'},
        markers=True
    )
    st.plotly_chart(fig, use_container_width=True)


def display_price_impact_tab():
    """Muestra el contenido de la pestaña 'Análisis de Price Impact'."""
    st.header("💧 Análisis de Price Impact para Pools de Gliquid")
    st.markdown("Analiza el impacto en el precio para diferentes volúmenes de trade en pools específicos de Gliquid.")

    st.subheader("1. Cargar archivo de Pares")
    uploaded_file = st.file_uploader("Sube tu archivo CSV con los pares de Gliquid.", type="csv", key="uploader_tab2")

    if uploaded_file is None:
        st.info("Por favor, carga un archivo CSV para comenzar.")
        return

    try:
        df_tokens = pd.read_csv(uploaded_file, dtype=str)
        required_cols = ["dex", "pair", "tokenaddress", "quotetokenaddress"]
        if not all(c in df_tokens.columns for c in required_cols):
            st.error(f"El CSV debe contener las columnas: {', '.join(required_cols)}")
            return
    except Exception as e:
        st.error(f"No se pudo procesar el archivo CSV. Error: {e}")
        return

    df_gliquid = df_tokens[df_tokens["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])
    if df_gliquid.empty:
        st.warning("No se encontraron pares con 'dex' igual a 'gliquid' en el archivo.")
        return

    st.subheader("2. Seleccionar Par y Montos")
    selected_pair = st.selectbox("Selecciona el Par a analizar:", df_gliquid['pair'].unique())
    amounts_input = st.text_input("Define los montos a simular (separados por coma):", "0.1, 1, 10, 100, 1000")

    if st.button(f"🚀 Iniciar Análisis para {selected_pair}"):
        try:
            amounts = [float(x.strip()) for x in amounts_input.split(',') if x.strip()]
            if not amounts: raise ValueError("La lista de montos no puede estar vacía.")
        except ValueError:
            st.error("Formato de montos inválido. Deben ser números separados por comas.")
            return

        pair_row = df_gliquid[df_gliquid['pair'] == selected_pair].iloc[0]
        pair_name, token_a, token_b = pair_row["pair"], pair_row["tokenaddress"], pair_row["quotetokenaddress"]
        
        all_results = []
        log_area = st.empty()
        
        with st.spinner(f"Analizando '{pair_name}'..."):
            # Analizar A -> B
            log_area.info(f"Analizando dirección: {pair_name.split('/')[0]} -> {pair_name.split('/')[1]}")
            all_results.extend(analyze_pair_price_impact(token_a, token_b, pair_name, False, amounts, log_area))
            
            # Analizar B -> A (inverso)
            log_area.info(f"Analizando dirección: {pair_name.split('/')[1]} -> {pair_name.split('/')[0]}")
            all_results.extend(analyze_pair_price_impact(token_b, token_a, pair_name, True, amounts, log_area))

        if not all_results:
            st.error("El análisis no produjo resultados.")
        else:
            st.balloons()
            st.success("🎉 ¡Análisis completado!")
            df_res = pd.DataFrame(all_results)
            st.dataframe(df_res)
            st.download_button(
                label="📥 Descargar resultados en CSV",
                data=df_res.to_csv(index=False).encode('utf-8'),
                file_name=f"PriceImpact_{pair_name.replace('/', '-')}.csv",
                mime="text/csv"
            )


def display_route_simulation_tab():
    """Muestra el contenido de la pestaña 'Simulación de Rutas'."""
    st.header("🔬 Simulación de Rutas Óptimas")
    st.markdown("Simula la mejor ruta de trading para un par y monto, detallando cada paso (hop), protocolo y comisiones estimadas.")
    
    DEFAULT_FEE_BPS = Decimal("7.5") # Comisión por defecto si no se encuentra en la API
    SPECIAL_PROTOCOLS = {"HyperSwapV2", "LaminarV3", "HybraFinanceV3", "ProjectX"}

    st.subheader("1. Cargar archivo de Pares")
    uploaded_file = st.file_uploader("Sube tu archivo CSV.", type="csv", key="uploader_tab3")

    if uploaded_file is None:
        st.info("Por favor, carga un archivo CSV para continuar.")
        return
        
    try:
        df_tokens = pd.read_csv(uploaded_file, dtype=str)
        required_cols = ["dex", "pair", "tokenaddress", "quotetokenaddress"]
        if not all(c in df_tokens.columns for c in required_cols):
            st.error(f"El CSV debe contener las columnas: {', '.join(required_cols)}")
            return
    except Exception as e:
        st.error(f"No se pudo procesar el archivo CSV. Error: {e}")
        return

    df_gliquid = df_tokens[df_tokens["dex"].astype(str).str.lower() == "gliquid"].drop_duplicates(subset=["pair"])
    if df_gliquid.empty:
        st.warning("No se encontraron pares con 'dex' igual a 'gliquid' en el archivo.")
        return

    st.subheader("2. Seleccionar Pares y Montos")
    pair_options = df_gliquid['pair'].unique()
    selected_pairs = st.multiselect("Selecciona Pares a analizar:", pair_options, default=pair_options[0] if len(pair_options) > 0 else None)
    amounts_input = st.text_input("Define montos a simular (separados por coma):", "100, 1000, 10000")

    if st.button("🚀 Iniciar Simulación de Rutas"):
        try:
            amounts = [float(x.strip()) for x in amounts_input.split(',') if x.strip()]
            if not amounts: raise ValueError("La lista de montos no puede estar vacía.")
        except ValueError:
            st.error("Formato de montos inválido. Deben ser números separados por comas.")
            return

        df_to_analyze = df_gliquid[df_gliquid['pair'].isin(selected_pairs)]
        output_rows = []
        log_area = st.empty()
        progress_bar = st.progress(0.0)
        total_simulations = len(df_to_analyze) * 2 * len(amounts)
        sim_count = 0

        with st.spinner("Realizando simulación de rutas..."):
            for _, row in df_to_analyze.iterrows():
                directions = [
                    (False, (row.tokenaddress, row.quotetokenaddress)),  # Directo
                    (True, (row.quotetokenaddress, row.tokenaddress))   # Inverso
                ]
                for is_inverse, (token_in, token_out) in directions:
                    for amount in amounts:
                        sim_count += 1
                        log_area.info(f"Simulando: Par {row.pair}, Monto {amount}, Inverso: {'Sí' if is_inverse else 'No'}")
                        time.sleep(PAUSE_BETWEEN_REQUESTS)
                        
                        try:
                            params = {"tokenIn": token_in, "tokenOut": token_out, "amountIn": str(amount), "multiHop": "false", "slippage": "1.0"}
                            response = call_api("/v2/route", params, log_area)
                            
                            routes = response.get("routes", [])
                            if not routes and "execution" in response: # Fallback para otra estructura de respuesta
                                routes = [{"hops": response["execution"].get("details", {}).get("hopSwaps", [])}]

                            for route_idx, route in enumerate(routes):
                                flat_hops = [hop for sublist in route.get("hops", []) for hop in (sublist if isinstance(sublist, list) else [sublist])]
                                parsed_hops_data, total_fee = [], Decimal(0)

                                for hop in flat_hops:
                                    protocol = hop.get("routerName", str(hop.get("routerIndex", "")))
                                    amount_in = normalize_raw_amount(hop.get("amountIn"))
                                    fee_bps = detect_fee_bps_from_hop(hop) or DEFAULT_FEE_BPS
                                    
                                    if protocol in SPECIAL_PROTOCOLS: fee_bps /= 100
                                    
                                    fee_amount = (amount_in * fee_bps / 10000) if amount_in else None
                                    if fee_amount: total_fee += fee_amount
                                    
                                    parsed_hops_data.append({
                                        "protocol": protocol, "amount": str(amount_in), "price_impact": hop.get("priceImpact", ""),
                                        "fee_bps": str(fee_bps), "fee_amount": str(fee_amount)
                                    })
                                
                                output_rows.append({
                                    "pair": row.pair, "inverse": "YES" if is_inverse else "NO",
                                    "amount_requested": amount, "route_index": route_idx,
                                    "total_fee_estimated": str(total_fee), "hops_data": parsed_hops_data
                                })
                        except Exception as e:
                            st.warning(f"Error en simulación para {row.pair} (monto {amount}): {e}")
                        
                        progress_bar.progress(sim_count / total_simulations)

        if not output_rows:
            st.error("La simulación no produjo resultados.")
        else:
            st.balloons()
            st.success("🎉 ¡Simulación completada!")
            df_out = pd.DataFrame(output_rows)
            
            # Expande los datos de los hops en columnas separadas para mejor visualización/exportación
            max_hops = max(len(h) for h in df_out['hops_data']) if not df_out.empty else 0
            for i in range(max_hops):
                for col in ["protocol", "amount", "price_impact", "fee_bps", "fee_amount"]:
                    df_out[f"hop_{i+1}_{col}"] = df_out['hops_data'].apply(lambda hops: hops[i].get(col) if len(hops) > i else None)
            
            df_out = df_out.drop(columns=['hops_data'])
            st.dataframe(df_out)
            st.download_button(
                "📥 Descargar resultados en CSV",
                df_out.to_csv(index=False).encode('utf-8'),
                "Simulacion_Rutas.csv", "text/csv"
            )


def main():
    """Función principal que ejecuta la aplicación Streamlit."""
    setup_page()

    # --- Creación de Pestañas ---
    tab1, tab2, tab3 = st.tabs([
        "Análisis Histórico APY",
        "Análisis de Price Impact",
        "Simulación de Rutas"
    ])

    with tab1:
        display_historical_apy_tab()

    with tab2:
        display_price_impact_tab()

    with tab3:
        display_route_simulation_tab()


if __name__ == "__main__":
    main()
