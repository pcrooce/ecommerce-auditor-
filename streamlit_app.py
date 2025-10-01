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

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    st.warning("⚠️ Playwright no instalado. Frávega requiere Playwright para funcionar.")

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
except ImportError:
    st.error("Instala: pip install openpyxl")

st.set_page_config(
    page_title="Auditor Frávega",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
.main {padding: 0rem 1rem;}
.audit-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 2.5rem; border-radius: 15px; color: white;
    margin-bottom: 2rem; box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    text-align: center;
}
div[data-testid="metric-container"] {
    background-color: #f8f9fa; border: 2px solid #e9ecef;
    padding: 15px; border-radius: 10px; margin: 10px 0px;
}
.stButton > button {
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    color: white; border: none; padding: 0.5rem 1rem;
    font-weight: 600; border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="audit-header">
    <h1>🤖 Auditor Frávega v6.2</h1>
    <p>Sistema profesional con validaciones completas</p>
</div>
""", unsafe_allow_html=True)

if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None

def detectar_columnas_fravega(df):
    """Detecta columnas automáticamente con mapeo expandido"""
    resultado = {'url': None, 'precio': None, 'sku': None, 'cuotas': None}
    
    # Patrones para URL
    patrones_url = [
        'url fravega', 'url fvg', 'link fravega', 'link fvg',
        'fravega url', 'fvg url', 'fravega link', 'fvg link'
    ]
    
    # Patrones para Precio
    patrones_precio = [
        'pvp fravega', 'pvp fvg', 'precio fravega', 'precio fvg',
        'fravega pvp', 'fvg pvp', 'fravega precio', 'fvg precio'
    ]
    
    # Patrones para Cuotas
    patrones_cuotas = [
        'cuotas fvg', 'cuotas fravega', 'csi fvg', 'csi fravega',
        'financiacion fvg', 'financiación fvg', 'financiacion fravega',
        'fvg cuotas', 'fravega cuotas'
    ]
    
    for col in df.columns:
        col_lower = col.lower().strip()
        
        # Detectar URL
        if resultado['url'] is None:
            for patron in patrones_url:
                if patron in col_lower:
                    resultado['url'] = col
                    break
        
        # Detectar Precio
        if resultado['precio'] is None:
            for patron in patrones_precio:
                if patron in col_lower:
                    resultado['precio'] = col
                    break
        
        # Detectar SKU
        if resultado['sku'] is None:
            if any(word in col_lower for word in ['sku', 'codigo', 'código']):
                resultado['sku'] = col
        
        # Detectar Cuotas
        if resultado['cuotas'] is None:
            for patron in patrones_cuotas:
                if patron in col_lower:
                    resultado['cuotas'] = col
                    break
    
    return resultado

def limpiar_precio(valor):
    if pd.isna(valor):
        return None
    
    precio_str = str(valor).replace('$', '').replace(' ', '').strip()
    
    if not precio_str or precio_str == '':
        return None
    
    if '.' in precio_str and ',' in precio_str:
        precio_str = precio_str.replace('.', '').replace(',', '.')
    elif '.' in precio_str:
        if re.search(r'\.\d{3}', precio_str):
            precio_str = precio_str.replace('.', '')
        elif not re.search(r'\.\d{2}$', precio_str):
            precio_str = precio_str.replace('.', '')
    elif ',' in precio_str:
        if re.search(r',\d{2}$', precio_str):
            precio_str = precio_str.replace(',', '.')
        else:
            precio_str = precio_str.replace(',', '')
    
    try:
        valor_float = float(re.sub(r'[^\d.]', '', precio_str))
        return valor_float if valor_float > 0 else None
    except:
        return None

def validar_url(url):
    """Valida que la URL sea correcta y completa"""
    if not url or not isinstance(url, str):
        return False, "URL vacía o inválida"
    
    url = url.strip()
    
    if not url.startswith('http://') and not url.startswith('https://'):
        return False, "URL incompleta - debe comenzar con https://"
    
    if 'fravega.com' not in url.lower():
        return False, "URL no es de Frávega"
    
    if len(url) < 30:
        return False, "URL demasiado corta - posiblemente incompleta"
    
    return True, None

class FravegaScraper:
    def __init__(self):
        pass
    
    def scrape_url(self, url):
        """Scrapea Frávega con validaciones completas"""
        
        # VALIDACIÓN 1: URL
        es_valida, error_url = validar_url(url)
        if not es_valida:
            return {
                'url': url,
                'titulo': None,
                'precio_web': None,
                'precio_tachado': None,
                'descuento_%': None,
                'categoria': None,
                'cuotas_web': None,
                'estado_producto': 'Error',
                'estado_scraping': f'❌ {error_url}',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        resultado = {
            'url': url,
            'titulo': None,
            'precio_web': None,
            'precio_tachado': None,
            'descuento_%': None,
            'categoria': None,
            'cuotas_web': None,
            'estado_producto': 'Activo',
            'estado_scraping': '✅ OK',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        if not PLAYWRIGHT_AVAILABLE:
            resultado['estado_producto'] = 'Error'
            resultado['estado_scraping'] = '❌ Playwright no disponible'
            return resultado
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = context.new_page()
                
                try:
                    page.goto(url, wait_until='networkidle', timeout=30000)
                    page.wait_for_timeout(3000)
                except Exception as e:
                    browser.close()
                    resultado['estado_producto'] = 'Error'
                    resultado['estado_scraping'] = f'❌ No se pudo cargar la página: {str(e)[:50]}'
                    return resultado
                
                page_content = page.content()
                soup = BeautifulSoup(page_content, 'html.parser')
                
                # PASO 1: Verificar si el botón está inhabilitado
                producto_inhabilitado = False
                try:
                    boton = page.locator("button[data-test-id='product-buy-button']").first
                    boton.wait_for(timeout=5000)
                    
                    is_disabled = boton.is_disabled()
                    has_disabled_attr = boton.get_attribute('disabled') is not None
                    
                    if is_disabled or has_disabled_attr:
                        producto_inhabilitado = True
                except:
                    # Si no hay botón, asumir que no está disponible
                    producto_inhabilitado = True
                
                # PASO 2: Extraer título y categoría SIEMPRE
                try:
                    titulo = page.locator("h1[data-test-id='product-title']").text_content(timeout=5000)
                    if titulo:
                        resultado['titulo'] = titulo.strip()
                except:
                    pass
                
                try:
                    categorias_elems = page.locator("span[itemprop='name']").all()
                    categorias_validas = []
                    for elem in categorias_elems:
                        texto = elem.text_content().strip()
                        if texto and texto.lower() not in ['frávega', 'fravega', 'inicio', 'home']:
                            categorias_validas.append(texto)
                    
                    if categorias_validas:
                        resultado['categoria'] = categorias_validas[-1]
                except:
                    pass
                
                # PASO 3: Si está inhabilitado, marcar y salir
                if producto_inhabilitado:
                    resultado['estado_producto'] = 'Inhabilitado'
                    resultado['estado_scraping'] = '⚠️ Botón de compra deshabilitado'
                    resultado['cuotas_web'] = None
                    browser.close()
                    return resultado
                
                # PASO 4: Extraer precio (solo si está habilitado)
                try:
                    precio = page.locator("span.sc-1d9b1d9e-0.sc-faa1a185-3").first.text_content(timeout=5000)
                    resultado['precio_web'] = limpiar_precio(precio)
                except:
                    pass
                
                try:
                    tachado = page.locator("span.sc-e081bce1-0.sc-faa1a185-4").first.text_content(timeout=5000)
                    resultado['precio_tachado'] = limpiar_precio(tachado)
                except:
                    pass
                
                try:
                    descuento = page.locator("span.sc-e2aca368-0").first.text_content(timeout=5000)
                    match = re.search(r'(\d+)', descuento)
                    if match:
                        resultado['descuento_%'] = float(match.group(1))
                except:
                    pass
                
                # PASO 5: Extraer cuotas (solo si está habilitado)
                cuotas_encontradas = False
                try:
                    cuotas_divs = soup.find_all('div', class_=lambda x: x and 'sc-3cba7521-0' in x)
                    
                    for div in cuotas_divs:
                        cuotas_span = div.find('span', class_=lambda x: x and 'sc-3cba7521-10' in x)
                        
                        if not cuotas_span:
                            continue
                        
                        texto = cuotas_span.get_text()
                        match = re.search(r'(\d+)\s*cuotas?', texto, re.IGNORECASE)
                        
                        if not match:
                            continue
                        
                        num_cuotas = int(match.group(1))
                        
                        img_container = div.find('div', class_=lambda x: x and 'sc-3cba7521-3' in x)
                        
                        if img_container:
                            imagenes = img_container.find_all('img', src=True)
                            
                            # CRÍTICO: Solo las primeras 2 imágenes (Visa y Mastercard)
                            if len(imagenes) >= 2:
                                es_visa_master = False
                                for img in imagenes[:2]:
                                    src = img.get('src', '').lower()
                                    if 'd91d7904a8578' in src or '54c0d769ece1b' in src:
                                        es_visa_master = True
                                        break
                                
                                if es_visa_master:
                                    resultado['cuotas_web'] = num_cuotas
                                    cuotas_encontradas = True
                                    break
                    
                    # Si no encontró cuotas con Visa/Master, es pago al contado
                    if not cuotas_encontradas:
                        resultado['cuotas_web'] = 1
                        
                except Exception as e:
                    resultado['cuotas_web'] = 1
                    resultado['estado_scraping'] = f'⚠️ OK pero error en cuotas: {str(e)[:30]}'
                
                # VALIDACIÓN FINAL: Verificar que se hayan scrapeado datos críticos
                if not resultado['precio_web']:
                    resultado['estado_scraping'] = '⚠️ No se pudo obtener el precio'
                
                browser.close()
                
        except Exception as e:
            resultado['estado_producto'] = 'Error'
            resultado['estado_scraping'] = f'❌ Error: {str(e)[:50]}'
        
        return resultado

def realizar_scraping(df_tienda, progress_bar, status_text):
    scraper = FravegaScraper()
    resultados = []
    
    # Scraping secuencial para Playwright (más estable)
    for idx, row in df_tienda.iterrows():
        if pd.notna(row.get('url')):
            resultado = scraper.scrape_url(row['url'])
            resultado['idx'] = idx
            resultados.append(resultado)
            
            progress_bar.progress(min((idx + 1) / len(df_tienda), 1.0))
            status_text.text(f"Escaneando {idx + 1}/{len(df_tienda)}...")
    
    return resultados

def crear_excel_formateado(df_results):
    output = BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"
    
    ws['A1'] = f'AUDITORÍA FRÁVEGA - {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    ws['A1'].font = Font(bold=True, size=14)
    ws.merge_cells('A1:O1')
    
    columnas = ['SKU', 'Título', 'Precio Maestro', 'Precio Web', 'Precio Tachado',
               'Descuento %', 'Variación %', 'Precio OK', 'Cuotas Maestro', 'Cuotas Web',
               'Cuotas OK', 'Categoría', 'Estado Producto', 'Estado Scraping', 'URL']
    
    ws.append([])
    ws.append(columnas)
    
    for cell in ws[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    for _, row in df_results.iterrows():
        row_data = [
            row.get('sku'),
            row.get('titulo'),
            row.get('precio_maestro'),
            row.get('precio_web'),
            row.get('precio_tachado'),
            row.get('descuento_%'),
            row.get('variacion_precio_%'),
            'Sí' if row.get('precio_ok') else 'No',
            row.get('cuotas_maestro'),
            row.get('cuotas_web'),
            'Sí' if row.get('cuotas_correctas') else 'No',
            row.get('categoria'),
            row.get('estado_producto'),
            row.get('estado_scraping'),
            row.get('url')
        ]
        ws.append(row_data)
    
    # CORRECCIÓN: Auto-ajustar ancho de columnas correctamente
    for col_idx in range(1, len(columnas) + 1):
        max_length = 0
        column_letter = ws.cell(row=3, column=col_idx).column_letter
        
        for row_idx in range(3, ws.max_row + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            try:
                if cell.value:
                    cell_length = len(str(cell.value))
                    if cell_length > max_length:
                        max_length = cell_length
            except:
                pass
        
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width
    
    wb.save(output)
    output.seek(0)
    return output

with st.sidebar:
    st.markdown("""
        <div style='text-align: center; padding: 1rem; 
             background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
             border-radius: 10px; margin-bottom: 1rem;'>
            <h2 style='color: white; margin: 0;'>⚙️ Configuración</h2>
        </div>
    """, unsafe_allow_html=True)
    
    if not PLAYWRIGHT_AVAILABLE:
        st.error("⚠️ Playwright requerido")
        st.info("Instalar: pip install playwright && playwright install chromium")
    else:
        st.success("✅ Playwright listo")
    
    price_threshold = st.slider("🎯 Tolerancia de precio (%)", 0, 20, 5, 1)
    
    modo_operacion = st.radio("🚀 Modo de operación", [
        "🧪 Prueba (simulado)",
        "⚡ Rápida (10 productos)", 
        "📊 Completa"
    ])
    
    if "Prueba" in modo_operacion:
        max_productos = 10
    elif "Rápida" in modo_operacion:
        max_productos = 10
    else:
        max_productos = st.number_input("Límite de productos:", 10, 1000, 100, 10)

tab1, tab2, tab3 = st.tabs(["📁 Cargar Datos", "📊 Resultados", "📈 Dashboard"])

with tab1:
    st.markdown("### 📝 Nueva Auditoría")
    
    uploaded_file = st.file_uploader("Cargar archivo Excel maestro", type=['xlsx', 'xls'])
    
    if uploaded_file:
        df_maestro = pd.read_excel(uploaded_file)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("📄 Archivo", uploaded_file.name[:20] + "...")
        col2.metric("📊 Filas totales", f"{len(df_maestro):,}")
        col3.metric("📋 Columnas", len(df_maestro.columns))
        
        columnas_detectadas = detectar_columnas_fravega(df_maestro)
        
        st.markdown("### ✅ Detección Automática de Columnas")
        
        # Validar que se detectaron todas las columnas necesarias
        todas_detectadas = all([
            columnas_detectadas['url'],
            columnas_detectadas['sku'],
            columnas_detectadas['precio'],
            columnas_detectadas['cuotas']
        ])
        
        if todas_detectadas:
            col1, col2 = st.columns(2)
            
            with col1:
                st.success(f"✅ URL: `{columnas_detectadas['url']}`")
                st.success(f"✅ SKU: `{columnas_detectadas['sku']}`")
            
            with col2:
                st.success(f"✅ Precio: `{columnas_detectadas['precio']}`")
                st.success(f"✅ Cuotas: `{columnas_detectadas['cuotas']}`")
            
            url_column = columnas_detectadas['url']
            sku_column = columnas_detectadas['sku']
            precio_column = columnas_detectadas['precio']
            cuotas_column = columnas_detectadas['cuotas']
            
        else:
            st.warning("⚠️ No se pudieron detectar todas las columnas automáticamente. Seleccione manualmente:")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if columnas_detectadas['url']:
                    st.success(f"✅ URL detectada: `{columnas_detectadas['url']}`")
                    url_column = columnas_detectadas['url']
                else:
                    st.error("❌ URL no detectada")
                    url_column = st.selectbox("Seleccionar columna URL:", df_maestro.columns, key='url')
                
                if columnas_detectadas['sku']:
                    st.success(f"✅ SKU detectado: `{columnas_detectadas['sku']}`")
                    sku_column = columnas_detectadas['sku']
                else:
                    st.error("❌ SKU no detectado")
                    sku_column = st.selectbox("Seleccionar columna SKU:", df_maestro.columns, key='sku')
            
            with col2:
                if columnas_detectadas['precio']:
                    st.success(f"✅ Precio detectado: `{columnas_detectadas['precio']}`")
                    precio_column = columnas_detectadas['precio']
                else:
                    st.error("❌ Precio no detectado")
                    precio_column = st.selectbox("Seleccionar columna Precio:", df_maestro.columns, key='precio')
                
                if columnas_detectadas['cuotas']:
                    st.success(f"✅ Cuotas detectadas: `{columnas_detectadas['cuotas']}`")
                    cuotas_column = columnas_detectadas['cuotas']
                else:
                    st.error("❌ Cuotas no detectadas")
                    cuotas_column = st.selectbox("Seleccionar columna Cuotas:", df_maestro.columns, key='cuotas')
        
        df_tienda = df_maestro[df_maestro[url_column].notna()].copy()
        
        rename_dict = {
            url_column: 'url',
            sku_column: 'sku',
            precio_column: 'precio_maestro',
            cuotas_column: 'cuotas_maestro'
        }
        
        df_tienda = df_tienda.rename(columns=rename_dict)
        df_tienda['precio_maestro'] = df_tienda['precio_maestro'].apply(limpiar_precio)
        df_tienda['cuotas_maestro'] = pd.to_numeric(df_tienda['cuotas_maestro'], errors='coerce')
        
        df_tienda = df_tienda.head(max_productos)
        
        st.markdown("---")
        
        if st.button("🚀 INICIAR AUDITORÍA", type="primary", use_container_width=True):
            
            if "Prueba" in modo_operacion:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                resultados = []
                for i, (idx, row) in enumerate(df_tienda.iterrows()):
                    variacion = np.random.uniform(-10, 10)
                    precio_maestro_val = row.get('precio_maestro', 10000)
                    if pd.isna(precio_maestro_val) or precio_maestro_val == 0:
                        precio_maestro_val = 10000
                    
                    precio_web = float(precio_maestro_val * (1 + variacion/100))
                    
                    # Simular diferentes estados
                    estados = ['Activo', 'Activo', 'Activo', 'Inhabilitado', 'Error']
                    estado = np.random.choice(estados, p=[0.7, 0.1, 0.1, 0.05, 0.05])
                    
                    if estado == 'Inhabilitado':
                        resultado = {
                            'idx': idx,
                            'url': row['url'],
                            'titulo': f"Producto Ejemplo {i+1}",
                            'precio_web': None,
                            'precio_tachado': None,
                            'descuento_%': None,
                            'categoria': "Electrodomésticos",
                            'cuotas_web': None,
                            'estado_producto': 'Inhabilitado',
                            'estado_scraping': '⚠️ Botón de compra deshabilitado'
                        }
                    elif estado == 'Error':
                        resultado = {
                            'idx': idx,
                            'url': row['url'],
                            'titulo': None,
                            'precio_web': None,
                            'precio_tachado': None,
                            'descuento_%': None,
                            'categoria': None,
                            'cuotas_web': None,
                            'estado_producto': 'Error',
                            'estado_scraping': '❌ URL incompleta'
                        }
                    else:
                        resultado = {
                            'idx': idx,
                            'url': row['url'],
                            'titulo': f"Producto Ejemplo {i+1}",
                            'precio_web': precio_web,
                            'precio_tachado': precio_web * 1.3,
                            'descuento_%': np.random.randint(10, 40),
                            'categoria': "Electrodomésticos",
                            'cuotas_web': np.random.choice([1, 3, 6, 9, 12]),
                            'estado_producto': 'Activo',
                            'estado_scraping': '✅ OK'
                        }
                    
                    resultados.append(resultado)
                    
                    progress_bar.progress((i + 1) / len(df_tienda))
                    status_text.text(f"Simulando {i + 1}/{len(df_tienda)}...")
                    time.sleep(0.1)
                
                progress_bar.empty()
                status_text.empty()
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                resultados = realizar_scraping(df_tienda, progress_bar, status_text)
                
                progress_bar.empty()
                status_text.empty()
            
            # Procesar resultados
            for resultado in resultados:
                idx = resultado['idx']
                df_tienda.loc[idx, 'titulo'] = resultado.get('titulo')
                df_tienda.loc[idx, 'precio_web'] = resultado.get('precio_web')
                df_tienda.loc[idx, 'precio_tachado'] = resultado.get('precio_tachado')
                df_tienda.loc[idx, 'descuento_%'] = resultado.get('descuento_%')
                df_tienda.loc[idx, 'categoria'] = resultado.get('categoria')
                df_tienda.loc[idx, 'cuotas_web'] = resultado.get('cuotas_web')
                df_tienda.loc[idx, 'estado_producto'] = resultado.get('estado_producto')
                df_tienda.loc[idx, 'estado_scraping'] = resultado.get('estado_scraping')
            
            # Calcular variación de precio (solo para productos activos con precio)
            mask = (
                (df_tienda['precio_web'].notna()) & 
                (df_tienda['precio_maestro'].notna()) & 
                (df_tienda['precio_maestro'] > 0) &
                (df_tienda['estado_producto'] == 'Activo')
            )
            
            df_tienda['variacion_precio_%'] = None
            
            if mask.any():
                df_tienda.loc[mask, 'variacion_precio_%'] = (
                    (df_tienda.loc[mask, 'precio_web'] - df_tienda.loc[mask, 'precio_maestro']) / 
                    df_tienda.loc[mask, 'precio_maestro'] * 100
                ).round(2)
            
            # Precio OK solo si hay precio y está dentro del umbral
            df_tienda['precio_ok'] = False
            if mask.any():
                df_tienda.loc[mask, 'precio_ok'] = (
                    abs(df_tienda.loc[mask, 'variacion_precio_%']) <= price_threshold
                )
            
            # Cuotas OK solo si ambas tienen valor
            mask_cuotas = (
                (df_tienda['cuotas_web'].notna()) &
                (df_tienda['cuotas_maestro'].notna()) &
                (df_tienda['estado_producto'] == 'Activo')
            )
            
            df_tienda['cuotas_correctas'] = None
            if mask_cuotas.any():
                df_tienda.loc[mask_cuotas, 'cuotas_correctas'] = (
                    df_tienda.loc[mask_cuotas, 'cuotas_web'] == df_tienda.loc[mask_cuotas, 'cuotas_maestro']
                )
            
            st.session_state.audit_results = df_tienda
            
            st.success(f"✅ Auditoría completada: {len(df_tienda)} productos procesados")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("✅ Activos OK", len(df_tienda[df_tienda['precio_ok'] == True]))
            col2.metric("❌ Errores precio", len(df_tienda[df_tienda['precio_ok'] == False]))
            col3.metric("⚠️ Inhabilitados", len(df_tienda[df_tienda['estado_producto'] == 'Inhabilitado']))
            col4.metric("🔴 Errores scraping", len(df_tienda[df_tienda['estado_producto'] == 'Error']))

with tab2:
    if st.session_state.audit_results is not None:
        df_results = st.session_state.audit_results
        
        st.markdown("### 📊 Resultados de la Auditoría")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            filtros = ["Todos", "Solo activos", "Errores de precio", "Inhabilitados", "Errores técnicos", "Cuotas incorrectas"]
            filtro = st.selectbox("Filtrar por:", filtros)
        
        df_mostrar = df_results.copy()
        
        if filtro == "Solo activos":
            df_mostrar = df_mostrar[df_mostrar['estado_producto'] == 'Activo']
        elif filtro == "Errores de precio":
            df_mostrar = df_mostrar[(df_mostrar['precio_ok'] == False) & (df_mostrar['estado_producto'] == 'Activo')]
        elif filtro == "Inhabilitados":
            df_mostrar = df_mostrar[df_mostrar['estado_producto'] == 'Inhabilitado']
        elif filtro == "Errores técnicos":
            df_mostrar = df_mostrar[df_mostrar['estado_producto'] == 'Error']
        elif filtro == "Cuotas incorrectas":
            df_mostrar = df_mostrar[df_mostrar['cuotas_correctas'] == False]
        
        columnas_mostrar = [
            'sku', 'titulo', 'precio_maestro', 'precio_web', 'precio_tachado',
            'descuento_%', 'variacion_precio_%', 'precio_ok',
            'cuotas_maestro', 'cuotas_web', 'cuotas_correctas',
            'categoria', 'estado_producto', 'estado_scraping'
        ]
        
        columnas_existentes = [col for col in columnas_mostrar if col in df_mostrar.columns]
        df_display = df_mostrar[columnas_existentes].copy()
        
        nombres = {
            'sku': 'SKU',
            'titulo': 'Título',
            'precio_maestro': 'Precio Maestro',
            'precio_web': 'Precio Web',
            'precio_tachado': 'Precio Tachado',
            'descuento_%': 'Descuento %',
            'variacion_precio_%': 'Variación %',
            'precio_ok': 'Precio OK',
            'cuotas_maestro': 'Cuotas Maestro',
            'cuotas_web': 'Cuotas Web',
            'cuotas_correctas': 'Cuotas OK',
            'categoria': 'Categoría',
            'estado_producto': 'Estado',
            'estado_scraping': 'Scraping'
        }
        
        df_display = df_display.rename(columns=nombres)
        
        if 'Precio OK' in df_display.columns:
            df_display['Precio OK'] = df_display['Precio OK'].map({True: '✅', False: '❌', None: '-'})
        
        if 'Cuotas OK' in df_display.columns:
            df_display['Cuotas OK'] = df_display['Cuotas OK'].map({True: '✅', False: '❌', None: '-'})
        
        st.dataframe(df_display, use_container_width=True, height=500)
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            excel_file = crear_excel_formateado(df_results)
            st.download_button(
                "📊 Descargar Excel Completo",
                data=excel_file,
                file_name=f"Auditoria_Fravega_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        with col2:
            csv = df_mostrar.to_csv(index=False)
            st.download_button(
                "📄 Descargar CSV",
                data=csv,
                file_name=f"Auditoria_Fravega_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
    else:
        st.info("Ejecuta una auditoría primero para ver los resultados")

with tab3:
    if st.session_state.audit_results is not None:
        df = st.session_state.audit_results
        
        st.markdown("### 📈 Análisis General")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total = len(df)
            st.metric("📦 Total Productos", total)
        
        with col2:
            activos = len(df[df['estado_producto'] == 'Activo'])
            activos_pct = (activos / total * 100) if total > 0 else 0
            st.metric("✅ Activos", f"{activos} ({activos_pct:.1f}%)")
        
        with col3:
            inhabilitados = len(df[df['estado_producto'] == 'Inhabilitado'])
            st.metric("⚠️ Inhabilitados", inhabilitados)
        
        with col4:
            errores = len(df[df['estado_producto'] == 'Error'])
            st.metric("🔴 Errores", errores)
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            estados_data = {
                'Estado': ['✅ Activos', '⚠️ Inhabilitados', '🔴 Errores'],
                'Cantidad': [
                    len(df[df['estado_producto'] == 'Activo']),
                    len(df[df['estado_producto'] == 'Inhabilitado']),
                    len(df[df['estado_producto'] == 'Error'])
                ]
            }
            
            fig = px.pie(
                estados_data,
                values='Cantidad',
                names='Estado',
                title='Distribución de Estados'
            )
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            df_activos = df[df['estado_producto'] == 'Activo']
            if not df_activos.empty and 'precio_ok' in df_activos.columns:
                precios_data = {
                    'Estado': ['✅ Precio OK', '❌ Precio Error'],
                    'Cantidad': [
                        len(df_activos[df_activos['precio_ok'] == True]),
                        len(df_activos[df_activos['precio_ok'] == False])
                    ]
                }
                
                fig = px.pie(
                    precios_data,
                    values='Cantidad',
                    names='Estado',
                    title='Validación de Precios (Solo Activos)'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin datos de precios para analizar")
        
        st.markdown("---")
        st.markdown("### 💳 Análisis de Cuotas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            df_cuotas = df[(df['cuotas_web'].notna()) & (df['estado_producto'] == 'Activo')]
            if not df_cuotas.empty:
                cuotas_count = df_cuotas['cuotas_web'].value_counts().sort_index()
                fig = px.bar(
                    x=cuotas_count.index,
                    y=cuotas_count.values,
                    title='Distribución de Cuotas en Web',
                    labels={'x': 'Número de Cuotas', 'y': 'Cantidad de Productos'}
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin datos de cuotas para analizar")
        
        with col2:
            df_cuotas_val = df[(df['cuotas_correctas'].notna()) & (df['estado_producto'] == 'Activo')]
            if not df_cuotas_val.empty:
                cuotas_ok = len(df_cuotas_val[df_cuotas_val['cuotas_correctas'] == True])
                cuotas_error = len(df_cuotas_val[df_cuotas_val['cuotas_correctas'] == False])
                
                fig = px.pie(
                    values=[cuotas_ok, cuotas_error],
                    names=['✅ Correctas', '❌ Incorrectas'],
                    title='Validación de Cuotas'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sin validaciones de cuotas disponibles")
    else:
        st.info("Ejecuta una auditoría primero para ver el dashboard")

st.markdown("---")
st.markdown(
    f"""<div style='text-align: center; color: gray;'>
        v6.2 | Frávega con validaciones completas | {datetime.now().strftime("%d/%m/%Y %H:%M")}
    </div>""",
    unsafe_allow_html=True
)
