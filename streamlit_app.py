import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import time
import requests
from bs4 import BeautifulSoup
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils.dataframe import dataframe_to_rows
except ImportError:
    st.error("Por favor instala openpyxl: pip install openpyxl")

# Configuración de la página
st.set_page_config(
    page_title="Auditor Automático de Publicaciones",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado mejorado
st.markdown("""
    <style>
    /* Estilos generales */
    .main {
        padding: 0rem 1rem;
    }
    
    /* Header principal con gradiente */
    .audit-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        text-align: center;
    }
    
    /* Métricas personalizadas */
    div[data-testid="metric-container"] {
        background-color: #f8f9fa;
        border: 2px solid #e9ecef;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0px;
        transition: transform 0.2s;
    }
    
    div[data-testid="metric-container"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    
    /* Botones mejorados */
    .stButton > button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 600;
        border-radius: 8px;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }
    
    /* Tabs mejorados */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f8f9fa;
        padding: 4px;
        border-radius: 10px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 6px;
        color: #495057;
        font-weight: 500;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #667eea;
        color: white;
    }
    
    /* Progress bar personalizado */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Headers de sección */
    .section-header {
        background: linear-gradient(90deg, #f8f9fa 0%, #e9ecef 100%);
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
        border-left: 4px solid #667eea;
    }
    </style>
    """, unsafe_allow_html=True)

# Título principal
st.markdown("""
    <div class="audit-header">
        <h1 style="text-align: center; color: white;">🤖 Sistema de Auditoría Automática</h1>
        <p style="text-align: center; color: white; margin-top: 10px;">
            Verificación automática de precios en tiendas online
        </p>
    </div>
    """, unsafe_allow_html=True)

# Inicializar estado de sesión
if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None

# CONFIGURACIÓN DE TIENDAS Y MAPEO DE COLUMNAS
TIENDAS_CONFIG = {
    "ICBC": {
        "base_url": "https://mall.icbc.com.ar",
        "columnas_busqueda": ["ICBC", "icbc", "Icbc"],  # Qué buscar en las columnas del Excel
        "formato_precio_web": "15000",  # Ejemplo de cómo viene el precio en la web
        "columna_url": "URL ICBC",
        "selector_precio": ["span.price-now", "div.precio-final", "span.price"],
        "selector_stock": ["span.stock-qty", "div.stock-disponible"]
    },
    "Tienda Ciudad": {
        "base_url": "https://tiendaciudad.com.ar",
        "columnas_busqueda": ["Ciudad", "ciudad", "CIUDAD", "Cdad"],
        "formato_precio_web": "15.000,00",  # Ejemplo de formato
        "columna_url": "URL Ciudad",
        "selector_precio": ["span.price", "span.precio-actual", "div.price-now"],
        "selector_stock": ["span.stock-disponible", "div.availability"]
    },
    "Supervielle": {
        "base_url": "https://tienda.supervielle.com.ar",
        "columnas_busqueda": ["Supervielle", "supervielle", "SUPERVIELLE", "Sup"],
        "formato_precio_web": "15000",
        "columna_url": "URL Supervielle",
        "selector_precio": ["span.price", "div.precio"],
        "selector_stock": ["div.stock", "span.disponibilidad"]
    },
    "Galicia": {
        "base_url": "https://tienda.galicia.com.ar",
        "columnas_busqueda": ["Galicia", "galicia", "GALICIA", "Gal"],
        "formato_precio_web": "15000",
        "columna_url": "URL Galicia",
        "selector_precio": ["span.precio", "div.price-box"],
        "selector_stock": ["span.stock", "div.availability"]
    },
    "Tienda BNA": {
        "base_url": "https://tiendabna.com.ar",
        "columnas_busqueda": ["BNA", "bna", "Bna"],
        "formato_precio_web": "15.000,00",
        "columna_url": "URL BNA",
        "selector_precio": ["span.price"],
        "selector_stock": ["span.stock"]
    },
    "Fravega": {
        "base_url": "https://www.fravega.com",
        "columnas_busqueda": ["Fravega", "fravega", "FRAVEGA", "Fvg", "FVG"],
        "formato_precio_web": "15000",
        "columna_url": "URL Fravega",
        "selector_precio": ["span.PriceLayout__Main", "span[data-test-id='price-value']"],
        "selector_stock": ["button.AddToCart"]
    },
    "Megatone": {
        "base_url": "https://www.megatone.net",
        "columnas_busqueda": ["Megatone", "megatone", "MEGATONE", "Meg", "MEG", "Mgt", "MGT"],
        "formato_precio_web": "15000",
        "columna_url": "URL Megatone",
        "selector_precio": ["span.price"],
        "selector_stock": ["div.stock"]
    }
}

# Lista de todas las tiendas
TODAS_LAS_TIENDAS = list(TIENDAS_CONFIG.keys())

def detectar_columnas_automaticamente(df, tienda):
    """Detecta automáticamente las columnas según la tienda seleccionada"""
    config = TIENDAS_CONFIG[tienda]
    columnas_detectadas = {
        'url': None,
        'precio': None,
        'sku': None,
        'stock': None
    }
    
    # Buscar columna de URL para la tienda específica
    for col in df.columns:
        # Buscar URL
        for busqueda in config['columnas_busqueda']:
            if busqueda in col:
                columnas_detectadas['url'] = col
                break
        
        # Buscar precio (que contenga la palabra de la tienda)
        if columnas_detectadas['precio'] is None:
            for busqueda in config['columnas_busqueda']:
                if busqueda in col and any(word in col.lower() for word in ['precio', 'price']):
                    columnas_detectadas['precio'] = col
                    break
    
    # Buscar SKU y Stock generales
    for col in df.columns:
        if columnas_detectadas['sku'] is None and any(word in col.lower() for word in ['sku', 'codigo', 'código', 'id']):
            columnas_detectadas['sku'] = col
        
        if columnas_detectadas['stock'] is None and any(word in col.lower() for word in ['stock', 'cantidad', 'inventory']):
            columnas_detectadas['stock'] = col
    
    return columnas_detectadas

def limpiar_y_convertir_precio(valor):
    """Convierte cualquier formato de precio a número"""
    if pd.isna(valor):
        return np.nan
    
    # Convertir a string
    precio_str = str(valor)
    
    # Eliminar símbolos de moneda y espacios
    precio_str = precio_str.replace('$', '').replace(' ', '')
    
    # Si tiene punto y coma, asumir formato argentino (1.234,56)
    if ',' in precio_str and '.' in precio_str:
        precio_str = precio_str.replace('.', '').replace(',', '.')
    # Si solo tiene coma, reemplazar por punto
    elif ',' in precio_str:
        precio_str = precio_str.replace(',', '.')
    
    # Eliminar cualquier caracter no numérico excepto el punto
    precio_str = re.sub(r'[^\d.]', '', precio_str)
    
    try:
        return float(precio_str)
    except:
        return np.nan

def crear_excel_formateado(df_results, tienda):
    """Crea un Excel con formato profesional - versión simplificada"""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        # Si no está instalado openpyxl, devolver Excel simple
        output = BytesIO()
        df_results.to_excel(output, index=False)
        output.seek(0)
        return output
    
    output = BytesIO()
    
    # Crear workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"
    
    # Título
    ws['A1'] = f'AUDITORÍA {tienda.upper()} - {datetime.now().strftime("%d/%m/%Y")}'
    ws['A1'].font = Font(bold=True, size=14)
    ws.merge_cells('A1:H1')
    
    # Espacio
    ws.append([])
    
    # Encabezados
    columnas = ['SKU', 'Precio Correcto', 'Precio Web', 'Variación %', 
                'Precio OK', 'Stock Web', 'Requiere Acción', 'URL']
    ws.append(columnas)
    
    # Formato encabezados
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
    
    for cell in ws[3]:
        cell.font = header_font
        cell.fill = header_fill
    
    # Agregar datos
    for _, row in df_results.iterrows():
        row_data = [
            row.get('sku', ''),
            row.get('precio_maestro', 0),
            row.get('precio_web', 0),
            row.get('variacion_precio_%', 0),
            'Sí' if row.get('precio_ok', False) else 'No',
            row.get('stock_web', ''),
            'Sí' if row.get('requiere_accion', False) else 'No',
            row.get('url', '')
        ]
        ws.append(row_data)
    
    # Aplicar formato básico
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Aplicar bordes y colores
    for row_num in range(4, ws.max_row + 1):
        for col_num in range(1, 9):  # Solo 8 columnas
            try:
                cell = ws.cell(row=row_num, column=col_num)
                cell.border = thin_border
                
                # Color para Precio OK
                if col_num == 5:  # Columna de Precio OK
                    if cell.value == 'Sí':
                        cell.fill = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
                    else:
                        cell.fill = PatternFill(start_color="FFB6C1", end_color="FFB6C1", fill_type="solid")
                
                # Color para Requiere Acción
                if col_num == 7:  # Columna Requiere Acción
                    if cell.value == 'Sí':
                        cell.fill = PatternFill(start_color="FFD700", end_color="FFD700", fill_type="solid")
            except:
                pass
    
    # Ajustar anchos de columna de forma simple
    ws.column_dimensions['A'].width = 15  # SKU
    ws.column_dimensions['B'].width = 15  # Precio Correcto
    ws.column_dimensions['C'].width = 15  # Precio Web
    ws.column_dimensions['D'].width = 12  # Variación
    ws.column_dimensions['E'].width = 10  # Precio OK
    ws.column_dimensions['F'].width = 12  # Stock Web
    ws.column_dimensions['G'].width = 15  # Requiere Acción
    ws.column_dimensions['H'].width = 40  # URL
    
    # Guardar
    wb.save(output)
    output.seek(0)
    
    return output

class WebScraper:
    """Clase para hacer web scraping de las tiendas"""
    
    def __init__(self, tienda_config):
        self.config = tienda_config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def limpiar_precio(self, precio_texto):
        """Limpia y convierte el precio a número"""
        if not precio_texto:
            return None
        
        # Eliminar símbolos de moneda y espacios
        precio_texto = re.sub(r'[$\s]', '', precio_texto)
        
        # Si tiene punto y coma, asumir formato argentino
        if ',' in precio_texto and '.' in precio_texto:
            precio_texto = precio_texto.replace('.', '').replace(',', '.')
        elif ',' in precio_texto:
            precio_texto = precio_texto.replace(',', '.')
        
        try:
            return float(re.sub(r'[^\d.]', '', precio_texto))
        except:
            return None
    
    def scrape_url(self, url):
        """Scrapea una URL específica"""
        resultado = {
            'url': url,
            'precio_web': None,
            'stock_web': None,
            'error': None,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Buscar precio
            for selector in self.config['selector_precio']:
                elemento = soup.select_one(selector)
                if elemento:
                    precio_texto = elemento.get_text(strip=True)
                    resultado['precio_web'] = self.limpiar_precio(precio_texto)
                    if resultado['precio_web']:
                        break
            
            # Buscar stock
            for selector in self.config['selector_stock']:
                elemento = soup.select_one(selector)
                if elemento:
                    texto = elemento.get_text(strip=True).lower()
                    if 'sin stock' in texto or 'agotado' in texto:
                        resultado['stock_web'] = 'No'
                    else:
                        resultado['stock_web'] = 'Si'
                    break
            
            if not resultado['stock_web']:
                resultado['stock_web'] = 'Desconocido'
            
        except Exception as e:
            resultado['error'] = str(e)
        
        return resultado

def realizar_scraping(df_tienda, tienda_config, progress_bar, status_text):
    """Realiza el scraping de todas las URLs de una tienda"""
    scraper = WebScraper(tienda_config)
    resultados = []
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(scraper.scrape_url, row['url']): idx 
                  for idx, row in df_tienda.iterrows() if pd.notna(row.get('url'))}
        
        completed = 0
        total_futures = len(futures)
        
        for future in as_completed(futures):
            completed += 1
            idx = futures[future]
            progress = min(completed / total_futures, 1.0)
            progress_bar.progress(progress)
            status_text.text(f"Escaneando URL {completed}/{total_futures}...")
            
            try:
                resultado = future.result()
                resultado['idx'] = idx
                resultados.append(resultado)
            except Exception as e:
                resultados.append({
                    'idx': idx,
                    'url': df_tienda.loc[idx, 'url'],
                    'error': str(e)
                })
    
    return resultados

# Sidebar mejorado
with st.sidebar:
    st.markdown("""
        <div style='text-align: center; padding: 1rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    border-radius: 10px; margin-bottom: 1rem;'>
            <h2 style='color: white; margin: 0;'>⚙️ Panel de Control</h2>
        </div>
    """, unsafe_allow_html=True)
    
    st.markdown("### 🏪 Tienda a Auditar")
    selected_store = st.selectbox(
        "Selecciona:",
        TODAS_LAS_TIENDAS,
        label_visibility="collapsed"
    )
    
    if selected_store in TIENDAS_CONFIG:
        st.success("✅ Tienda configurada")
        
        with st.expander("📋 Ver configuración", expanded=False):
            config = TIENDAS_CONFIG[selected_store]
            st.markdown(f"""
            **URL Base:** `{config['base_url']}`  
            **Busca columnas con:** {', '.join(config['columnas_busqueda'])}  
            **Formato precio web:** {config['formato_precio_web']}  
            """)
    
    st.markdown("---")
    
    st.markdown("### 📊 Parámetros")
    
    price_threshold = st.slider(
        "🎯 Tolerancia precio (%)",
        min_value=0,
        max_value=20,
        value=5,
        step=1,
        help="Diferencia máxima aceptable"
    )
    
    if price_threshold <= 2:
        st.info("🔍 Modo estricto")
    elif price_threshold <= 5:
        st.success("✅ Modo balanceado")
    else:
        st.warning("⚠️ Modo permisivo")
    
    st.markdown("---")
    
    st.markdown("### 🚀 Modo")
    
    modo_operacion = st.radio(
        "Tipo de auditoría:",
        [
            "🧪 Prueba (simulado)",
            "⚡ Rápida (10 productos)", 
            "📊 Completa"
        ],
        label_visibility="collapsed"
    )
    
    if "Prueba" in modo_operacion:
        modo_operacion = "Modo Prueba (simular)"
    elif "Rápida" in modo_operacion:
        modo_operacion = "Auditoría Rápida (primeros 10)"
    else:
        modo_operacion = "Auditoría Completa"
        max_productos = st.number_input(
            "Límite:",
            min_value=10,
            max_value=1000,
            value=100,
            step=10
        )
    
    if modo_operacion != "Auditoría Completa":
        max_productos = 100

# Área principal
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.markdown(f"""
        <div style='text-align: center; padding: 1rem; background: #f8f9fa; 
                    border-radius: 10px; border: 2px solid #667eea;'>
            <h2 style='color: #495057; margin: 0;'>Auditando: {selected_store}</h2>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Tabs principales
tab1, tab2, tab3, tab4 = st.tabs([
    "📁 **Cargar y Ejecutar**", 
    "📊 **Resultados**", 
    "📈 **Dashboard**", 
    "❓ **Ayuda**"
])

with tab1:
    st.markdown("### 📝 Proceso de Auditoría")
    
    uploaded_file = st.file_uploader(
        "Cargar archivo Excel con los datos maestros",
        type=['xlsx', 'xls'],
        help="Puede ser 'Auditoria General.xlsx' o cualquier archivo con la estructura correcta"
    )
    
    if uploaded_file:
        try:
            with st.spinner('📖 Leyendo archivo...'):
                df_maestro = pd.read_excel(uploaded_file)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📄 Archivo", uploaded_file.name[:20] + "...")
            with col2:
                st.metric("📊 Filas", f"{len(df_maestro):,}")
            with col3:
                st.metric("📋 Columnas", len(df_maestro.columns))
            
            # Detectar columnas automáticamente
            columnas_detectadas = detectar_columnas_automaticamente(df_maestro, selected_store)
            
            st.markdown("---")
            st.markdown("### ✅ Verificación de columnas detectadas")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if columnas_detectadas['url']:
                    st.success(f"✅ URL: `{columnas_detectadas['url']}`")
                    url_column = columnas_detectadas['url']
                else:
                    st.error("❌ No se detectó columna de URL")
                    posibles_url = [col for col in df_maestro.columns if 'url' in col.lower()]
                    url_column = st.selectbox("Selecciona manualmente:", posibles_url if posibles_url else df_maestro.columns)
                
                if columnas_detectadas['sku']:
                    st.success(f"✅ SKU: `{columnas_detectadas['sku']}`")
                    sku_column = columnas_detectadas['sku']
                else:
                    st.warning("⚠️ Selecciona columna SKU")
                    sku_column = st.selectbox("SKU/Código:", df_maestro.columns)
            
            with col2:
                if columnas_detectadas['precio']:
                    st.success(f"✅ Precio: `{columnas_detectadas['precio']}`")
                    precio_column = columnas_detectadas['precio']
                else:
                    st.warning("⚠️ Selecciona columna precio")
                    precio_columns = [col for col in df_maestro.columns if 'precio' in col.lower()]
                    precio_column = st.selectbox("Precio:", precio_columns if precio_columns else df_maestro.columns)
                
                if columnas_detectadas['stock']:
                    st.success(f"✅ Stock: `{columnas_detectadas['stock']}`")
                    stock_column = columnas_detectadas['stock']
                else:
                    st.info("ℹ️ Stock opcional")
                    stock_column = st.selectbox("Stock (opcional):", ['(ninguno)'] + list(df_maestro.columns))
                    if stock_column == '(ninguno)':
                        stock_column = None
            
            # Preparar datos
            df_tienda = df_maestro[df_maestro[url_column].notna()].copy()
            
            # Renombrar columnas
            rename_dict = {
                url_column: 'url',
                sku_column: 'sku'
            }
            if precio_column:
                rename_dict[precio_column] = 'precio_maestro'
            if stock_column:
                rename_dict[stock_column] = 'stock_maestro'
            
            df_tienda = df_tienda.rename(columns=rename_dict)
            
            # Limpiar y convertir precio maestro
            if 'precio_maestro' in df_tienda.columns:
                df_tienda['precio_maestro'] = df_tienda['precio_maestro'].apply(limpiar_y_convertir_precio)
            
            # Convertir stock si existe
            if 'stock_maestro' in df_tienda.columns:
                df_tienda['stock_maestro'] = pd.to_numeric(df_tienda['stock_maestro'], errors='coerce')
            
            # Aplicar límites
            if modo_operacion == "Auditoría Rápida (primeros 10)":
                df_tienda = df_tienda.head(10)
            elif modo_operacion == "Auditoría Completa":
                df_tienda = df_tienda.head(max_productos)
            else:  # Modo prueba
                df_tienda = df_tienda.head(10)
            
            st.markdown("---")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.info(f"**🏪 {selected_store}**")
            with col2:
                st.info(f"**📊 {len(df_tienda)} productos**")
            with col3:
                st.info(f"**⚡ {modo_operacion.split('(')[0].strip()}**")
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button(f"🚀 **INICIAR AUDITORÍA**", type="primary", use_container_width=True):
                    
                    if modo_operacion == "Modo Prueba (simular)":
                        st.markdown("#### 🧪 Simulando...")
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        resultados = []
                        total_items = len(df_tienda)
                        
                        for i, (idx, row) in enumerate(df_tienda.iterrows()):
                            variacion = np.random.uniform(-10, 10)
                            precio_maestro_val = row.get('precio_maestro', 10000)
                            if pd.isna(precio_maestro_val):
                                precio_maestro_val = 10000
                            
                            precio_web = float(precio_maestro_val * (1 + variacion/100))
                            
                            resultados.append({
                                'idx': idx,
                                'url': row['url'],
                                'precio_web': precio_web,
                                'stock_web': np.random.choice(['Si', 'No', 'Si', 'Si']),
                                'error': None if np.random.random() > 0.1 else "Error simulado",
                                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                            })
                            
                            progress = min((i + 1) / total_items, 1.0)
                            progress_bar.progress(progress)
                            status_text.text(f"Producto {i + 1}/{total_items}")
                            time.sleep(0.05)
                        
                        progress_bar.empty()
                        status_text.empty()
                        
                    else:
                        st.markdown("#### 🌐 Scraping real...")
                        
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        tienda_config = TIENDAS_CONFIG[selected_store]
                        resultados = realizar_scraping(df_tienda, tienda_config, progress_bar, status_text)
                        
                        progress_bar.empty()
                        status_text.empty()
                    
                    # Procesar resultados
                    st.success(f"✅ **¡Completado!** {len(resultados)} productos")
                    
                    for resultado in resultados:
                        idx = resultado['idx']
                        df_tienda.loc[idx, 'precio_web'] = resultado.get('precio_web')
                        df_tienda.loc[idx, 'stock_web'] = resultado.get('stock_web')
                        df_tienda.loc[idx, 'error_scraping'] = resultado.get('error')
                        df_tienda.loc[idx, 'timestamp'] = resultado.get('timestamp')
                    
                    # Calcular variaciones
                    df_tienda['variacion_precio_%'] = 0.0
                    df_tienda['precio_ok'] = False
                    df_tienda['requiere_accion'] = False
                    
                    mask = (df_tienda['precio_web'].notna()) & (df_tienda['precio_maestro'].notna()) & (df_tienda['precio_maestro'] != 0)
                    
                    if mask.any():
                        df_tienda.loc[mask, 'variacion_precio_%'] = (
                            (df_tienda.loc[mask, 'precio_web'] - df_tienda.loc[mask, 'precio_maestro']) / 
                            df_tienda.loc[mask, 'precio_maestro'] * 100
                        ).round(2)
                        
                        df_tienda.loc[mask, 'precio_ok'] = df_tienda.loc[mask, 'variacion_precio_%'].abs() <= price_threshold
                    
                    df_tienda['requiere_accion'] = (
                        (~df_tienda['precio_ok'] & df_tienda['precio_web'].notna()) | 
                        (df_tienda['stock_web'] == 'No')
                    )
                    
                    st.session_state.audit_results = df_tienda
                    
                    # Resumen
                    st.markdown("---")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("📋 Auditados", len(df_tienda))
                    
                    with col2:
                        errores = len(df_tienda[(df_tienda['precio_ok'] == False) & df_tienda['precio_web'].notna()])
                        st.metric("❌ Errores", errores)
                    
                    with col3:
                        sin_stock = len(df_tienda[df_tienda['stock_web'] == 'No'])
                        st.metric("📦 Sin Stock", sin_stock)
                    
                    st.success("✨ Ve a la pestaña **Resultados** para ver el detalle")
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
            st.info("Verifica que el archivo tenga las columnas necesarias para la tienda seleccionada")

with tab2:
    if st.session_state.audit_results is not None:
        df_results = st.session_state.audit_results
        
        st.markdown("### 📊 Resultados de la Auditoría")
        
        # Filtros
        col1, col2, col3 = st.columns(3)
        with col1:
            filtro = st.selectbox("Filtrar:", ["Todos", "Errores de precio", "Sin stock", "Requieren acción"])
        with col2:
            st.metric("Total auditados", len(df_results))
        with col3:
            if st.button("🔄 Actualizar"):
                st.rerun()
        
        # Aplicar filtros
        df_mostrar = df_results.copy()
        
        if filtro == "Errores de precio":
            df_mostrar = df_mostrar[(df_mostrar['precio_ok'] == False) & df_mostrar['precio_web'].notna()]
        elif filtro == "Sin stock":
            df_mostrar = df_mostrar[df_mostrar['stock_web'] == 'No']
        elif filtro == "Requieren acción":
            df_mostrar = df_mostrar[df_mostrar['requiere_accion'] == True]
        
        # Mostrar tabla
        columnas_mostrar = ['sku', 'precio_maestro', 'precio_web', 'variacion_precio_%', 
                           'precio_ok', 'stock_web', 'requiere_accion']
        
        # Agregar columna de error si existe
        if 'error_scraping' in df_mostrar.columns:
            columnas_mostrar.append('error_scraping')
        
        # Agregar URL para debug
        if st.checkbox("🔧 Mostrar URLs (debug)"):
            columnas_mostrar.append('url')
        
        # Asegurar que las columnas existan
        columnas_existentes = [col for col in columnas_mostrar if col in df_mostrar.columns]
        
        # Crear una copia para mostrar con formato seguro
        df_display = df_mostrar[columnas_existentes].copy()
        
        # Reemplazar NaN con valores por defecto antes de formatear
        if 'precio_maestro' in df_display.columns:
            df_display['precio_maestro'] = df_display['precio_maestro'].fillna(0)
        if 'precio_web' in df_display.columns:
            df_display['precio_web'] = df_display['precio_web'].fillna(0)
        if 'variacion_precio_%' in df_display.columns:
            df_display['variacion_precio_%'] = df_display['variacion_precio_%'].fillna(0)
        
        # Mostrar resumen de errores si existen
        if 'error_scraping' in df_display.columns:
            errores_unicos = df_display[df_display['error_scraping'].notna()]['error_scraping'].value_counts()
            if not errores_unicos.empty:
                st.warning(f"⚠️ Se encontraron {len(df_display[df_display['error_scraping'].notna()])} errores de scraping")
                with st.expander("Ver tipos de errores"):
                    for error, count in errores_unicos.items():
                        st.write(f"- {error[:100]}... ({count} veces)")
        
        # Mostrar sin formato si hay problemas
        try:
            st.dataframe(
                df_display.style.format({
                    'precio_maestro': lambda x: f'${x:,.0f}' if pd.notna(x) and x != 0 else '-',
                    'precio_web': lambda x: f'${x:,.0f}' if pd.notna(x) and x != 0 else '-',
                    'variacion_precio_%': lambda x: f'{x:.1f}%' if pd.notna(x) and x != 0 else '-'
                }, na_rep='-').applymap(
                    lambda x: 'background-color: #ffcccc' if x == '-' and x != 0 else '',
                    subset=['precio_web']
                ),
                use_container_width=True,
                height=400
            )
        except:
            # Si falla el formato, mostrar sin formato
            st.dataframe(df_display, use_container_width=True, height=400)
        
        # Exportar
        st.markdown("### 💾 Exportar")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            excel_file = crear_excel_formateado(df_results, selected_store)
            st.download_button(
                "📊 Excel Profesional",
                data=excel_file,
                file_name=f"Auditoria_{selected_store}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with col2:
            csv = df_mostrar.to_csv(index=False)
            st.download_button(
                "📄 CSV",
                data=csv,
                file_name=f"Auditoria_{selected_store}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    else:
        st.info("👆 Ejecuta una auditoría primero")

with tab3:
    if st.session_state.audit_results is not None:
        df = st.session_state.audit_results
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            accuracy = 0
            validos = df[df['precio_web'].notna()]
            if len(validos) > 0:
                accuracy = len(validos[validos['precio_ok'] == True]) / len(validos) * 100
            st.metric("Precisión", f"{accuracy:.1f}%")
        
        with col2:
            disponibilidad = len(df[df['stock_web'] == 'Si']) / len(df) * 100 if len(df) > 0 else 0
            st.metric("Disponibilidad", f"{disponibilidad:.1f}%")
        
        with col3:
            var_prom = df['variacion_precio_%'].abs().mean() if not df['variacion_precio_%'].isna().all() else 0
            st.metric("Var. Promedio", f"{var_prom:.1f}%")
        
        with col4:
            health = (accuracy * 0.6 + disponibilidad * 0.4)
            st.metric("Health Score", f"{health:.0f}/100")
        
        # Gráficos
        col1, col2 = st.columns(2)
        
        with col1:
            df_graf = df[df['variacion_precio_%'].notna()]
            if not df_graf.empty:
                fig = px.histogram(df_graf, x='variacion_precio_%', title='Distribución de Variaciones')
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            estados = pd.DataFrame({
                'Estado': ['OK', 'Error Precio', 'Sin Stock'],
                'Cantidad': [
                    len(df[(df['precio_ok'] == True)]),
                    len(df[(df['precio_ok'] == False) & df['precio_web'].notna()]),
                    len(df[df['stock_web'] == 'No'])
                ]
            })
            fig = px.pie(estados, values='Cantidad', names='Estado', title='Estado de Productos')
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("👆 Ejecuta una auditoría primero")

with tab4:
    st.markdown("""
    ### ❓ Preguntas Frecuentes
    
    **¿Qué archivo debo cargar?**
    - Cualquier Excel que contenga las columnas con URLs, precios y SKUs
    - Puede llamarse "Auditoria General.xlsx" o cualquier otro nombre
    
    **¿Cómo detecta las columnas?**
    - El sistema busca automáticamente columnas que contengan el nombre de la tienda
    - Por ejemplo, para ICBC busca columnas con "ICBC", "icbc", etc.
    
    **¿Qué significa el formato de precio?**
    - Se refiere a cómo viene el precio en la web (15.000 vs 15000)
    - NO se refiere a puntos de fidelidad o beneficios
    
    **¿Por qué algunos productos dan error?**
    - Puede ser que la URL no exista
    - La página cambió su estructura
    - Problemas de conexión
    
    ### 🔧 Solución de Problemas
    
    Si encuentras el error "Expected numeric dtype":
    1. Verifica que la columna de precios tenga números
    2. Revisa que no haya textos como "N/A" en precios
    3. El sistema limpia automáticamente símbolos $ y puntos
    """)

# Footer
st.markdown("---")
st.markdown(
    f"""<div style='text-align: center; color: gray;'>
        Sistema de Auditoría v1.0 | {datetime.now().strftime("%d/%m/%Y %H:%M")}
    </div>""",
    unsafe_allow_html=True
)
