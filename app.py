import streamlit as st
import pandas as pd
import plotly.express as px
import os
from datetime import datetime

# --- Configuración de la página ---
st.set_page_config(
    page_title="Análisis Histórico de APY",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Análisis Histórico de APY para HyperEVM")
st.markdown("Esta aplicación carga datos históricos (10-16 ago 2025), los filtra por la blockchain **hyperevm** y permite analizar el APY por par.")

# --- Funciones de Carga y Procesamiento ---

@st.cache_data(ttl=600)
def load_all_data(data_folder="data"):
    """
    Carga archivos CSV de un rango de fechas (2025), los combina y filtra por blockchain.
    """
    all_data = []
    
    if not os.path.isdir(data_folder):
        st.error(f"Error: No se encontró la carpeta '{data_folder}'.")
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

    numeric_cols = ['volume_24h', 'tvl', 'apy_24h', 'tier']
    for col in numeric_cols:
        if col in combined_df.columns:
            combined_df[col] = pd.to_numeric(combined_df[col], errors='coerce').fillna(0)

    if 'blockchain' in combined_df.columns:
        combined_df['blockchain'] = combined_df['blockchain'].str.lower()
        combined_df = combined_df[combined_df['blockchain'] == 'hyperevm']
    else:
        st.error("Error: La columna 'blockchain' no se encontró en los archivos CSV.")
        return pd.DataFrame(), loaded_files
    
    return combined_df, loaded_files

def run_simulation(df, new_tier):
    """
    Para cada par, encuentra el 'gliquid' con el APY más alto y usa su TVL y volumen
    como base constante para la simulación de 'gliquid_test' en todos los días.
    """
    df['dex'] = df['dex'].str.lower()
    
    gliquid_df = df[df['dex'] == 'gliquid'].copy()
    if gliquid_df.empty:
        st.info("No se encontraron datos para el DEX 'gliquid' para realizar la simulación.")
        return df

    all_simulation_rows = []
    
    # --- CORRECCIÓN: Agrupar por 'pair' para que la simulación sea específica para cada uno ---
    for pair_name, pair_group in gliquid_df.groupby('pair'):
        if pair_group.empty:
            continue
            
        # Encontrar la mejor instancia de 'gliquid' para este par específico
        best_gliquid_for_pair = pair_group.loc[pair_group['apy_24h'].idxmax()]
        
        # Usar su TVL y Volumen como constantes para la simulación de este par
        constant_tvl = best_gliquid_for_pair['tvl']
        constant_volume = best_gliquid_for_pair['volume_24h']
        
        # Obtener las fechas únicas donde aparece este par
        unique_dates_for_pair = df[df['pair'] == pair_name]['date'].unique()
        
        for date in unique_dates_for_pair:
            # Calcular el APY simulado
            new_apy = (new_tier * constant_volume / constant_tvl) * 365 if constant_tvl > 0 else 0
            
            # Crear una nueva fila para cada día
            new_row = best_gliquid_for_pair.copy()
            new_row['date'] = date
            new_row['dex'] = 'gliquid_test'
            new_row['tier'] = new_tier
            new_row['tvl'] = constant_tvl
            new_row['volume_24h'] = constant_volume
            new_row['apy_24h'] = new_apy
            all_simulation_rows.append(new_row)

    if not all_simulation_rows:
        return df

    gliquid_test_df = pd.DataFrame(all_simulation_rows)
    
    return pd.concat([df, gliquid_test_df], ignore_index=True)


# --- Interfaz de Usuario ---

st.subheader("1. Simulación para 'gliquid_test'")
simulated_tier = st.slider(
    "Selecciona el Fee Tier para la simulación:",
    min_value=0.01, max_value=5.0, value=1.0, step=0.05, format="%.2f"
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

    analysis_df = run_simulation(historical_df, simulated_tier)
    
    analysis_df['identifier'] = analysis_df['address'].astype(str) + " (" + analysis_df['dex'] + ")"
    
    # --- CORRECCIÓN: Añadir una tabla de datos para depuración ---
    if st.checkbox("Mostrar tabla de datos generados"):
        st.dataframe(analysis_df)

    st.subheader("2. Análisis y Comparativa")
    
    all_pairs = sorted(analysis_df['pair'].str.lower().unique())
    default_selection = ['khype/whype'] if 'khype/whype' in all_pairs else []
    
    selected_pairs = st.multiselect(
        "Selecciona los Pairs a visualizar:",
        options=all_pairs,
        default=default_selection
    )

    if selected_pairs:
        chart_df = analysis_df[analysis_df['pair'].str.lower().isin(selected_pairs)]

        fig = px.line(
            chart_df,
            x='date',
            y='apy_24h',
            color='identifier',
            title="Evolución Histórica del APY por Par",
            labels={'date': 'Fecha', 'apy_24h': 'APY (%)', 'identifier': 'Address (DEX)'},
            markers=True
        )
        fig.update_layout(legend_title_text='Pools')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Selecciona al menos un par para generar el gráfico.")
