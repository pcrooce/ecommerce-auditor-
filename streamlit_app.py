import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
from io import BytesIO
import time
import re

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    st.warning("⚠️ Playwright no instalado. Instalar con: pip install playwright && playwright install chromium")

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except ImportError:
    st.error("Error: pip install openpyxl")

from bs4 import BeautifulSoup

st.set_page_config(page_title="Auditor Frávega", page_icon="🤖", layout="wide")

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

st.markdown('<div class="audit-header"><h1>🤖 Auditor Frávega v6.0 FIXED</h1><p>Versión corregida y funcional</p></div>', unsafe_allow_html=True)

if 'audit_results' not in st.session_state:
    st.session_state.audit_results = None

def detectar_columnas_fravega(df):
    resultado = {'url': None, 'precio': None, 'sku': None, 'cuotas': None}
    
    patrones_url = ['url fravega', 'url fvg', 'link fravega', 'link fvg', 'fravega url', 'fvg url', 'fravega link', 'fvg link']
    patrones_precio = ['pvp fravega', 'pvp fvg', 'precio fravega', 'precio fvg', 'fravega pvp', 'fvg pvp', 'fravega precio', 'fvg precio']
    patrones_cuotas = ['cuotas fvg', 'cuotas fravega', 'csi fvg', 'csi fravega', 'financiacion fvg', 'financiación fvg', 'fvg cuotas', 'fravega cuotas']
    
    for col in df.columns:
        col_lower = col.lower().strip()
        
        if resultado['url'] is None:
            for patron in patrones_url:
                if patron in col_lower:
                    resultado['url'] = col
                    break
        
        if resultado['precio'] is None:
            for patron in patrones_precio:
                if patron in col_lower:
                    resultado['precio'] = col
                    break
        
        if resultado['sku'] is None:
            if any(word in col_lower for word in ['sku', 'codigo', 'código']):
                resultado['sku'] = col
        
        if resultado['cuotas'] is None:
            for patron in patrones_cuotas:
                if patron in col_lower:
                    resultado['cuotas'] = col
                    break
    
    return resultado

def limpiar_precio(valor):
    if pd.isna(valor) or valor is None:
        return None
    
    precio_str = str(valor).replace('$', '').replace(' ', '').strip()
    
    if not precio_str:
        return None
    
    if '.' in precio_str and ',' in precio_str:
        precio_str = precio_str.replace('.', '').replace(',', '.')
    elif '.' in precio_str:
        if re.search(r'\.\d{3}', precio_str):
            precio_str = precio_str.replace('.', '')
    elif ',' in precio_str:
        if re.search(r',\d{2}$', precio_str):
            precio_str = precio_str.replace(',', '.')
    
    try:
        valor_float = float(re.sub(r'[^\d.]', '', precio_str))
        return valor_float if valor_float > 0 else None
    except:
        return None

def validar_url(url):
    if not url or not isinstance(url, str):
        return False, "URL vacía"
    
    url = url.strip()
    
    if not url.startswith('http'):
        return False, "URL incompleta - falta https://"
    
    if 'fravega.com' not in url.lower():
        return False, "No es URL de Frávega"
    
    if len(url) < 30:
        return False, "URL demasiado corta"
    
    return True, None

def scrape_fravega(url):
    es_valida, error_url = validar_url(url)
    if not es_valida:
        return {
            'url': url, 'titulo': None, 'precio_web': None, 'precio_tachado': None,
            'descuento_%': None, 'categoria': None, 'cuotas_web': None,
            'estado_producto': 'Error', 'estado_scraping': f'❌ {error_url}'
        }
    
    if not PLAYWRIGHT_AVAILABLE:
        return {
            'url': url, 'titulo': None, 'precio_web': None, 'precio_tachado': None,
            'descuento_%': None, 'categoria': None, 'cuotas_web': None,
            'estado_producto': 'Error', 'estado_scraping': '❌ Playwright no disponible'
        }
    
    resultado = {
        'url': url, 'titulo': None, 'precio_web': None, 'precio_tachado': None,
        'descuento_%': None, 'categoria': None, 'cuotas_web': None,
        'estado_producto': 'Activo', 'estado_scraping': '✅ OK'
    }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1920, 'height': 1080})
            
            try:
                page.goto(url, wait_until='networkidle', timeout=30000)
                page.wait_for_timeout(3000)
            except Exception as e:
                browser.close()
                resultado['estado_producto'] = 'Error'
                resultado['estado_scraping'] = f'❌ No cargó: {str(e)[:30]}'
                return resultado
            
            soup = BeautifulSoup(page.content(), 'html.parser')
            
            # CORRECCIÓN 1: Verificar botón inhabilitado PRIMERO
            inhabilitado = False
            try:
                boton = page.locator("button[data-test-id='product-buy-button']").first
                boton.wait_for(timeout=5000)
                if boton.is_disabled() or boton.get_attribute('disabled'):
                    inhabilitado = True
            except:
                inhabilitado = True
            
            # Título
            try:
                titulo = page.locator("h1[data-test-id='product-title']").text_content(timeout=5000)
                if titulo:
                    resultado['titulo'] = titulo.strip()
            except:
                pass
            
            # CORRECCIÓN 2: Categorías - solo tomar la última y excluir "Frávega"
            try:
                cats_elems = page.locator("span[itemprop='name']").all()
                cats_validas = []
                for elem in cats_elems:
                    texto = elem.text_content().strip()
                    # Excluir explícitamente "Frávega", "Fravega", "Inicio", "Home"
                    if texto and texto.lower() not in ['frávega', 'fravega', 'inicio', 'home']:
                        cats_validas.append(texto)
                
                # Tomar la ÚLTIMA categoría válida
                if cats_validas:
                    resultado['categoria'] = cats_validas[-1]
            except:
                pass
            
            # CORRECCIÓN 3: Si está inhabilitado, marcar correctamente y NO scrapear precios
            if inhabilitado:
                resultado['estado_producto'] = 'Inhabilitado'
                resultado['estado_scraping'] = '⚠️ Botón de compra deshabilitado'
                resultado['cuotas_web'] = None  # Importante: None, no 1
                browser.close()
                return resultado
            
            # Precio (solo si está habilitado)
            try:
                precio = page.locator("span.sc-1d9b1d9e-0.sc-faa1a185-3").first.text_content(timeout=5000)
                resultado['precio_web'] = limpiar_precio(precio)
            except:
                pass
            
            # Precio tachado
            try:
                tachado = page.locator("span.sc-e081bce1-0.sc-faa1a185-4").first.text_content(timeout=5000)
                resultado['precio_tachado'] = limpiar_precio(tachado)
            except:
                pass
            
            # Descuento
            try:
                desc = page.locator("span.sc-e2aca368-0").first.text_content(timeout=5000)
                match = re.search(r'(\d+)', desc)
                if match:
                    resultado['descuento_%'] = float(match.group(1))
            except:
                pass
            
            # CORRECCIÓN 4: Cuotas - SOLO primeras 2 imágenes (Visa y Mastercard)
            try:
                divs = soup.find_all('div', class_=lambda x: x and 'sc-3cba7521-0' in x)
                
                for div in divs:
                    span = div.find('span', class_=lambda x: x and 'sc-3cba7521-10' in x)
                    if not span:
                        continue
                    
                    match = re.search(r'(\d+)\s*cuotas?', span.get_text(), re.I)
                    if not match:
                        continue
                    
                    num = int(match.group(1))
                    
                    imgs_container = div.find('div', class_=lambda x: x and 'sc-3cba7521-3' in x)
                    if imgs_container:
                        imagenes = imgs_container.find_all('img', src=True)
                        
                        # CRÍTICO: Solo verificar las primeras 2 imágenes
                        if len(imagenes) >= 2:
                            img1_src = imagenes[0].get('src', '').lower()
                            img2_src = imagenes[1].get('src', '').lower()
                            
                            # Verificar que al menos una de las primeras 2 sea Visa o Mastercard
                            es_visa_master = ('d91d7904a8578' in img1_src or '54c0d769ece1b' in img1_src or
                                            'd91d7904a8578' in img2_src or '54c0d769ece1b' in img2_src)
                            
                            if es_visa_master:
                                resultado['cuotas_web'] = num
                                break
                
                # Si no encontró cuotas con Visa/Master, es contado
                if resultado['cuotas_web'] is None:
                    resultado['cuotas_web'] = 1
            except Exception as e:
                resultado['cuotas_web'] = 1
                resultado['estado_scraping'] = f'⚠️ OK (error cuotas: {str(e)[:20]})'
            
            # CORRECCIÓN 5: Validar que se haya scrapeado el precio
            if not resultado['precio_web']:
                resultado['estado_scraping'] = '⚠️ No se obtuvo el precio'
            
            browser.close()
    
    except Exception as e:
        resultado['estado_producto'] = 'Error'
        resultado['estado_scraping'] = f'❌ {str(e)[:40]}'
    
    return resultado

def crear_excel(df):
    output = BytesIO()
    wb = Workbook()
    ws = wb.active
    ws.title = "Resultados"
    
    ws['A1'] = f'AUDITORÍA FRÁVEGA - {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    ws['A1'].font = Font(bold=True, size=14)
    ws.merge_cells('A1:O1')
    
    cols = ['SKU', 'Título', 'Precio Maestro', 'Precio Web', 'Precio Tachado',
            'Descuento %', 'Variación %', 'Precio OK', 'Cuotas Maestro', 'Cuotas Web',
            'Cuotas OK', 'Categoría', 'Estado', 'Scraping', 'URL']
    
    ws.append([])
    ws.append(cols)
    
    for cell in ws[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="667EEA", end_color="667EEA", fill_type="solid")
        cell.alignment = Alignment(horizontal='center')
    
    for _, row in df.iterrows():
        ws.append([
            row.get('sku'), row.get('titulo'), row.get('precio_maestro'),
            row.get('precio_web'), row.get('precio_tachado'), row.get('descuento_%'),
            row.get('variacion_precio_%'),
            'Sí' if row.get('precio_ok') == True else 'No' if row.get('precio_ok') == False else '-',
            row.get('cuotas_maestro'), row.get('cuotas_web'),
            'Sí' if row.get('cuotas_correctas') == True else 'No' if row.get('cuotas_correctas') == False else '-',
            row.get('categoria'), row.get('estado_producto'),
            row.get('estado_scraping'), row.get('url')
        ])
    
    for idx in range(1, len(cols) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 15
    
    wb.save(output)
    output.seek(0)
    return output

with st.sidebar:
    st.markdown('<div style="text-align:center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding:1rem; border-radius:10px; margin-bottom:1rem;"><h2 style="color:white; margin:0;">⚙️ Config</h2></div>', unsafe_allow_html=True)
    
    if not PLAYWRIGHT_AVAILABLE:
        st.error("⚠️ Playwright NO disponible")
        st.info("Instalar: pip install playwright && playwright install chromium")
    else:
        st.success("✅ Playwright listo")
    
    tolerancia = st.slider("Tolerancia precio (%)", 0, 20, 5)
    
    modo = st.radio("Modo", ["🧪 Prueba", "⚡ Rápida (10)", "📊 Completa"])
    
    if "Prueba" in modo:
        max_prods = 10
    elif "Rápida" in modo:
        max_prods = 10
    else:
        max_prods = st.number_input("Límite:", 10, 1000, 100)

tab1, tab2, tab3 = st.tabs(["📁 Cargar", "📊 Resultados", "📈 Dashboard"])

with tab1:
    st.markdown("### 📝 Nueva Auditoría")
    
    archivo = st.file_uploader("Excel maestro", type=['xlsx', 'xls'])
    
    if archivo:
        df_maestro = pd.read_excel(archivo)
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Archivo", archivo.name[:15])
        col2.metric("Filas", len(df_maestro))
        col3.metric("Columnas", len(df_maestro.columns))
        
        cols_det = detectar_columnas_fravega(df_maestro)
        
        todas = all([cols_det['url'], cols_det['sku'], cols_det['precio'], cols_det['cuotas']])
        
        if todas:
            st.success("✅ Todas las columnas detectadas automáticamente")
            col1, col2 = st.columns(2)
            col1.info(f"📍 URL: **{cols_det['url']}**")
            col1.info(f"🏷️ SKU: **{cols_det['sku']}**")
            col2.info(f"💰 Precio: **{cols_det['precio']}**")
            col2.info(f"💳 Cuotas: **{cols_det['cuotas']}**")
            
            url_col = cols_det['url']
            sku_col = cols_det['sku']
            precio_col = cols_det['precio']
            cuotas_col = cols_det['cuotas']
        else:
            st.warning("⚠️ Seleccione columnas manualmente:")
            col1, col2 = st.columns(2)
            url_col = col1.selectbox("URL:", df_maestro.columns)
            sku_col = col1.selectbox("SKU:", df_maestro.columns)
            precio_col = col2.selectbox("Precio:", df_maestro.columns)
            cuotas_col = col2.selectbox("Cuotas:", df_maestro.columns)
        
        df = df_maestro[df_maestro[url_col].notna()].copy()
        df = df.rename(columns={url_col: 'url', sku_col: 'sku', precio_col: 'precio_maestro', cuotas_col: 'cuotas_maestro'})
        df['precio_maestro'] = df['precio_maestro'].apply(limpiar_precio)
        df['cuotas_maestro'] = pd.to_numeric(df['cuotas_maestro'], errors='coerce')
        df = df.head(max_prods)
        
        st.markdown("---")
        
        if st.button("🚀 INICIAR AUDITORÍA", type="primary", use_container_width=True):
            prog = st.progress(0)
            status = st.empty()
            
            if "Prueba" in modo:
                resultados = []
                for i, (idx, row) in enumerate(df.iterrows()):
                    var = np.random.uniform(-10, 10)
                    pm = row.get('precio_maestro', 10000)
                    if pd.isna(pm) or pm == 0:
                        pm = 10000
                    
                    pw = float(pm * (1 + var/100))
                    
                    estados = ['Activo', 'Activo', 'Inhabilitado', 'Error']
                    est = np.random.choice(estados, p=[0.7, 0.2, 0.05, 0.05])
                    
                    if est == 'Inhabilitado':
                        r = {'idx': idx, 'url': row['url'], 'titulo': f"Lavarropas Ejemplo {i+1}", 'precio_web': None,
                             'precio_tachado': None, 'descuento_%': None, 'categoria': "Lavarropas",
                             'cuotas_web': None, 'estado_producto': 'Inhabilitado',
                             'estado_scraping': '⚠️ Botón deshabilitado'}
                    elif est == 'Error':
                        r = {'idx': idx, 'url': row['url'], 'titulo': None, 'precio_web': None,
                             'precio_tachado': None, 'descuento_%': None, 'categoria': None,
                             'cuotas_web': None, 'estado_producto': 'Error',
                             'estado_scraping': '❌ URL incompleta'}
                    else:
                        r = {'idx': idx, 'url': row['url'], 'titulo': f"Lavarropas Ejemplo {i+1}", 'precio_web': pw,
                             'precio_tachado': pw * 1.3, 'descuento_%': float(np.random.randint(10, 40)),
                             'categoria': "Lavarropas", 'cuotas_web': int(np.random.choice([1,3,6,9,12])),
                             'estado_producto': 'Activo', 'estado_scraping': '✅ OK'}
                    
                    resultados.append(r)
                    prog.progress((i+1)/len(df))
                    status.text(f"Simulando {i+1}/{len(df)}")
                    time.sleep(0.1)
            else:
                resultados = []
                for i, (idx, row) in enumerate(df.iterrows()):
                    r = scrape_fravega(row['url'])
                    r['idx'] = idx
                    resultados.append(r)
                    prog.progress((i+1)/len(df))
                    status.text(f"Escaneando {i+1}/{len(df)}")
            
            prog.empty()
            status.empty()
            
            for r in resultados:
                idx = r['idx']
                df.loc[idx, 'titulo'] = r.get('titulo')
                df.loc[idx, 'precio_web'] = r.get('precio_web')
                df.loc[idx, 'precio_tachado'] = r.get('precio_tachado')
                df.loc[idx, 'descuento_%'] = r.get('descuento_%')
                df.loc[idx, 'categoria'] = r.get('categoria')
                df.loc[idx, 'cuotas_web'] = r.get('cuotas_web')
                df.loc[idx, 'estado_producto'] = r.get('estado_producto')
                df.loc[idx, 'estado_scraping'] = r.get('estado_scraping')
            
            # CORRECCIÓN 6: Calcular variación solo para productos activos con precio
            mask = ((df['precio_web'].notna()) & (df['precio_maestro'].notna()) & 
                    (df['precio_maestro'] > 0) & (df['estado_producto'] == 'Activo'))
            
            df['variacion_precio_%'] = None
            if mask.any():
                df.loc[mask, 'variacion_precio_%'] = ((df.loc[mask, 'precio_web'] - df.loc[mask, 'precio_maestro']) / 
                                                       df.loc[mask, 'precio_maestro'] * 100).round(2)
            
            # CORRECCIÓN 7: Precio OK solo si hay precio Y está en rango
            df['precio_ok'] = None
            if mask.any():
                df.loc[mask, 'precio_ok'] = abs(df.loc[mask, 'variacion_precio_%']) <= tolerancia
            
            # CORRECCIÓN 8: Cuotas OK solo si ambas existen
            mask_c = ((df['cuotas_web'].notna()) & (df['cuotas_maestro'].notna()) & 
                      (df['estado_producto'] == 'Activo'))
            df['cuotas_correctas'] = None
            if mask_c.any():
                df.loc[mask_c, 'cuotas_correctas'] = (df.loc[mask_c, 'cuotas_web'] == df.loc[mask_c, 'cuotas_maestro'])
            
            st.session_state.audit_results = df
            
            st.success(f"✅ Auditoría completada: {len(df)} productos")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("✅ Precio OK", len(df[df['precio_ok'] == True]))
            c2.metric("❌ Precio Error", len(df[df['precio_ok'] == False]))
            c3.metric("⚠️ Inhabilitados", len(df[df['estado_producto'] == 'Inhabilitado']))
            c4.metric("🔴 Errores", len(df[df['estado_producto'] == 'Error']))

with tab2:
    if st.session_state.audit_results is not None:
        df = st.session_state.audit_results
        
        st.markdown("### 📊 Resultados de la Auditoría")
        
        filtro = st.selectbox("Filtrar por:", ["Todos", "Solo activos", "Errores precio", "Inhabilitados", "Errores técnicos", "Cuotas incorrectas"])
        
        if filtro == "Solo activos":
            df_show = df[df['estado_producto'] == 'Activo']
        elif filtro == "Errores precio":
            df_show = df[(df['precio_ok'] == False) & (df['estado_producto'] == 'Activo')]
        elif filtro == "Inhabilitados":
            df_show = df[df['estado_producto'] == 'Inhabilitado']
        elif filtro == "Errores técnicos":
            df_show = df[df['estado_producto'] == 'Error']
        elif filtro == "Cuotas incorrectas":
            df_show = df[df['cuotas_correctas'] == False]
        else:
            df_show = df
        
        # CORRECCIÓN 9: Sin guiones bajos en nombres de columnas
        df_display = df_show[['sku', 'titulo', 'precio_maestro', 'precio_web', 'precio_tachado',
                              'descuento_%', 'variacion_precio_%', 'precio_ok',
                              'cuotas_maestro', 'cuotas_web', 'cuotas_correctas',
                              'categoria', 'estado_producto', 'estado_scraping']].copy()
        
        df_display = df_display.rename(columns={
            'sku': 'SKU', 'titulo': 'Título', 'precio_maestro': 'Precio Maestro',
            'precio_web': 'Precio Web', 'precio_tachado': 'Precio Tachado',
            'descuento_%': 'Descuento %', 'variacion_precio_%': 'Variación %',
            'precio_ok': 'Precio OK', 'cuotas_maestro': 'Cuotas Maestro',
            'cuotas_web': 'Cuotas Web', 'cuotas_correctas': 'Cuotas OK',
            'categoria': 'Categoría', 'estado_producto': 'Estado',
            'estado_scraping': 'Scraping'
        })
        
        # Convertir a símbolos
        if 'Precio OK' in df_display.columns:
            df_display['Precio OK'] = df_display['Precio OK'].map({True: '✅', False: '❌', None: '-'})
        
        if 'Cuotas OK' in df_display.columns:
            df_display['Cuotas OK'] = df_display['Cuotas OK'].map({True: '✅', False: '❌', None: '-'})
        
        st.dataframe(df_display, use_container_width=True, height=500)
        
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            excel = crear_excel(df)
            st.download_button("📊 Descargar Excel", excel, 
                             f"Fravega_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             use_container_width=True)
        with col2:
            csv = df.to_csv(index=False)
            st.download_button("📄 Descargar CSV", csv, 
                             f"Fravega_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                             use_container_width=True)
    else:
        st.info("Ejecuta una auditoría primero")

with tab3:
    if st.session_state.audit_results is not None:
        df = st.session_state.audit_results
        
        st.markdown("### 📈 Dashboard General")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📦 Total", len(df))
        c2.metric("✅ Activos", len(df[df['estado_producto'] == 'Activo']))
        c3.metric("⚠️ Inhabilitados", len(df[df['estado_producto'] == 'Inhabilitado']))
        c4.metric("🔴 Errores", len(df[df['estado_producto'] == 'Error']))
        
        col1, col2 = st.columns(2)
        
        with col1:
            est = {'Estado': ['Activos', 'Inhabilitados', 'Errores'],
                   'Cantidad': [len(df[df['estado_producto'] == 'Activo']),
                               len(df[df['estado_producto'] == 'Inhabilitado']),
                               len(df[df['estado_producto'] == 'Error'])]}
            fig = px.pie(est, values='Cantidad', names='Estado', title='Distribución de Estados')
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            activos = df[df['estado_producto'] == 'Activo']
            if not activos.empty and 'precio_ok' in activos.columns:
                prec = {'Estado': ['OK', 'Error'], 
                        'Cantidad': [len(activos[activos['precio_ok'] == True]),
                                   len(activos[activos['precio_ok'] == False])]}
                fig = px.pie(prec, values='Cantidad', names='Estado', title='Validación de Precios')
                st.plotly_chart(fig, use_container_width=True)
        
        st.markdown("---")
        st.markdown("### 💳 Análisis de Cuotas")
        
        col1, col2 = st.columns(2)
        
        with col1:
            cuotas_df = df[(df['cuotas_web'].notna()) & (df['estado_producto'] == 'Activo')]
            if not cuotas_df.empty:
                cuotas_count = cuotas_df['cuotas_web'].value_counts().sort_index()
                fig = px.bar(x=cuotas_count.index, y=cuotas_count.values,
                           title='Distribución de Cuotas', labels={'x': 'Cuotas', 'y': 'Cantidad'})
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            cuotas_val = df[(df['cuotas_correctas'].notna()) & (df['estado_producto'] == 'Activo')]
            if not cuotas_val.empty:
                ok = len(cuotas_val[cuotas_val['cuotas_correctas'] == True])
                error = len(cuotas_val[cuotas_val['cuotas_correctas'] == False])
                fig = px.pie(values=[ok, error], names=['✅ Correctas', '❌ Incorrectas'],
                           title='Validación de Cuotas')
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Ejecuta una auditoría primero")

st.markdown(f'<div style="text-align:center; color:gray;">v6.0 FIXED | Solo Frávega | {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>', unsafe_allow_html=True)
