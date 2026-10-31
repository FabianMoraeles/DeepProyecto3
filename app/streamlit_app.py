from dataclasses import replace
from datetime import datetime
import html
import json
import os
from pathlib import Path
import uuid

import streamlit as st
from dotenv import load_dotenv
from datoclaro.io import ROOT, read_jsonl
from .runtime import db_path
from datoclaro.execution import execute
from .catalog import catalog, DEMOS, LABELS
from .config import Config
from .pipeline import predict, demo_predict
from .verify import export_csv, chart_spec


def markup(text):
    st.markdown(text, unsafe_allow_html=True)


def kpi(label, value, detail):
    markup(f'<div class="kpi"><div class="label">{html.escape(str(label))}</div><div class="value">{html.escape(str(value))}</div><div class="detail">{html.escape(str(detail))}</div></div>')


def chart(frame, spec):
    with st.spinner('Preparando visualización…'):
        import plotly.express as px
    if not spec or spec['x'] not in frame or spec['y'] not in frame:
        return
    display = frame.head(30).copy()
    if spec['type'] == 'line':
        fig = px.line(display.sort_values(spec['x']), x=spec['x'], y=spec['y'], markers=True)
        fig.update_traces(line_color='#408b6b', line_width=3, marker_size=7)
    else:
        display[spec['x']] = display[spec['x']].fillna('Sin dato').astype(str)
        fig = px.bar(display, x=spec['y'], y=spec['x'], orientation='h', text_auto='.3s')
        fig.update_traces(marker_color='#78a884', marker_line_width=0, textposition='outside', cliponaxis=False)
        fig.update_yaxes(autorange='reversed')
    fig.update_layout(template='plotly_white', height=max(320, min(620, len(display)*30+90)),
                      margin=dict(l=0,r=45,t=12,b=25), font=dict(family='Arial', size=12, color='#687c75'),
                      paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                      xaxis=dict(gridcolor='#e9eeea', zeroline=False), yaxis=dict(gridcolor='#e9eeea'), showlegend=False)
    st.plotly_chart(fig, width='stretch', config={'displaylogo':False, 'modeBarButtonsToRemove':['lasso2d','select2d']})
    if len(frame) > 30:
        st.caption('El gráfico muestra las primeras 30 filas; la tabla y la descarga contienen el resultado completo.')


def show_result(item):
    with st.spinner('Preparando tabla de resultados…'):
        import pandas as pd
    result = item['output']
    st.markdown('### '+item['question'])
    st.caption(f"{LABELS[item['db_id']][0]} · {item['time']} · {result.get('model', 'Sin modelo')}")
    if result['status'] in ('clarification', 'refused'):
        st.info(result.get('message', 'La consulta no está permitida.'))
        return
    if result['status'] != 'ok':
        st.error(result.get('error') or 'No se completó la consulta. Intenta una pregunta más concreta.')
        return
    raw = result['result']
    if not raw['rows']:
        st.info('No hay resultados para estas condiciones. Prueba con otros filtros.')
    # Desambiguar encabezados duplicados para la representación, manteniendo el original al exportar.
    names, seen = [], {}
    for column in raw['columns']:
        seen[column] = seen.get(column, 0)+1
        names.append(column if seen[column] == 1 else f'{column} ({seen[column]})')
    frame = pd.DataFrame(raw['rows'], columns=names)
    markup('<div class="answer-box">'+html.escape(result.get('explanation', ''))+'</div>')
    a,b,c = st.columns(3)
    with a: kpi('FILAS EN EL RESULTADO', f"{len(frame):,}", 'Resultado completo de la consulta')
    with b: kpi('TIEMPO DE RESPUESTA', f"{result.get('latency_ms',0)/1000:.2f} s", 'Generación y ejecución')
    with c: kpi('MODO', 'Guiado' if result['model']=='demo-editorial' else 'IA', 'Consulta de solo lectura')
    tabs = st.tabs(['Visualización', 'Tabla de datos', 'Consulta y fuentes'])
    with tabs[0]:
        spec = result.get('chart')
        if spec:
            chart(frame, spec)
        else:
            st.caption('Este resultado se representa mejor como tabla.')
            st.dataframe(frame, hide_index=True, width='stretch')
    with tabs[1]:
        search = st.text_input('Filtrar filas del resultado', placeholder='Escribe para buscar…', key='filter_'+item['id'])
        filtered = frame
        if search and not frame.empty:
            filtered = frame[frame.astype(str).apply(lambda col: col.str.contains(search, case=False, regex=False)).any(axis=1)]
        st.dataframe(filtered, hide_index=True, width='stretch')
        st.caption(f'{len(filtered):,} de {len(frame):,} filas · el filtro de pantalla no altera la consulta original.')
        st.download_button('Descargar CSV', export_csv(list(filtered.columns), filtered.values.tolist()),
                           file_name='datoclaro-resultados.csv', mime='text/csv', icon=':material/download:', key='csv_'+item['id'])
    with tabs[2]:
        st.code(result['sql'], language='sql')
        st.caption('La consulta se ejecutó sobre una copia local de BIRD, abierta en modo de solo lectura.')
        sources = result.get('sources', {})
        if sources:
            st.write('Tablas recuperadas: '+', '.join(sources.get('tables', [])))
            st.caption('Ejemplos kb: '+(', '.join(sources.get('examples', [])) or 'Ninguno'))
            st.caption('Recuperación: '+sources.get('retrieval', '')+' · Reparación: '+('Sí' if result.get('repaired') else 'No'))
        cost = result.get('cost_usd')
        st.caption('Costo API: '+(f'USD {cost:.6f}' if cost is not None else 'No calculado; tarifas no configuradas o ejecución local.'))
        st.download_button('Descargar análisis reproducible', json.dumps(item, ensure_ascii=False, indent=2, default=str),
                           'datoclaro-analisis.json', 'application/json', key='json_'+item['id'])


def analyze(db_id, question, mode):
    with st.status('Conectando tu pregunta con los datos…', expanded=True) as status:
        st.write('Identificando tablas y relaciones relevantes')
        if mode == 'Demostración guiada':
            output = demo_predict(db_id, question)
        else:
            cfg = Config.from_env()
            provider = 'ollama' if mode == 'Ollama local' else 'anthropic'
            if provider != cfg.provider:
                cfg = replace(cfg, provider=provider, model='qwen2.5-coder:7b-instruct' if provider=='ollama' else 'claude-haiku-5-5')
            output = predict({'id': 'ui-'+uuid.uuid4().hex, 'db_id': db_id, 'question': question, 'language': 'es'}, cfg)
        st.write('Comprobando la consulta y preparando la respuesta')
        status.update(label='Análisis listo' if output['status']=='ok' else 'Revisa la respuesta', state='complete' if output['status'] in ('ok','clarification') else 'error', expanded=False)
    item = {'id': uuid.uuid4().hex, 'db_id':db_id, 'question':question, 'output':output, 'time':datetime.now().strftime('%H:%M')}
    st.session_state.history = ([item]+st.session_state.history)[:20]
    st.session_state.result = item


def workspace(db_id, mode):
    markup('''<div class="hero"><div><div class="eyebrow">TU ESPACIO DE DESCUBRIMIENTO</div>
      <h1>Menos consultas.<br><em>Más respuestas.</em></h1>
      <p>Conversa con tus datos y transforma una pregunta en una perspectiva clara.</p></div>
      <div class="art" aria-hidden="true"><div class="art-card"><div class="art-label">DE LA PREGUNTA AL HALLAZGO</div>
      <div class="art-title">Cada dato cuenta una historia</div><div class="bars"><i style="height:34%"></i><i style="height:55%"></i><i style="height:42%"></i><i style="height:78%"></i><i style="height:65%"></i><i style="height:96%"></i></div></div>
      <div class="float-chip">✧ &nbsp; Pregunta. Explora. Comprende.</div></div></div>''')
    a,b,c = st.columns(3)
    schema = catalog()[db_id]
    with a: kpi('FUENTE SELECCIONADA', LABELS[db_id][0], 'BIRD · datos públicos')
    with b: kpi('TABLAS CONECTADAS', len(schema['tables']), 'Esquemas y relaciones disponibles')
    with c: kpi('ESPACIO DE ANÁLISIS', 'Solo lectura', 'Consultas trazables y exportables')
    markup('<div class="section-title">¿Qué quieres descubrir?</div><div class="section-sub">Empieza con una pregunta. Nosotros nos encargamos de la consulta.</div>')
    examples = [d for d in DEMOS if d['db_id']==db_id]
    if mode == 'Demostración guiada':
        st.caption('Modo guiado · consultas preparadas que se ejecutan sobre datos reales. Las preguntas libres requieren Claude u Ollama.')
    cols = st.columns(3)
    for i, demo in enumerate(examples):
        with cols[i%3]:
            if st.button(demo['title']+' ↗', key='demo_'+str(i), width='stretch', help=demo['question']):
                st.session_state.question = demo['question']
    with st.form('question_form', clear_on_submit=False):
        question = st.text_area('Tu pregunta', key='question', placeholder='Por ejemplo: ¿qué condados tienen más escuelas?', height=100, max_chars=2000, label_visibility='collapsed')
        left,right = st.columns([3,1])
        with left: st.caption(f'◉  {LABELS[db_id][0]}  ·  Respuestas basadas en datos')
        with right: submitted = st.form_submit_button('Analizar pregunta', type='primary', width='stretch', icon=':material/arrow_forward:')
    if submitted:
        analyze(db_id, question, mode)
    current = st.session_state.get('result')
    if current and current['db_id']==db_id:
        st.divider()
        show_result(current)
    else:
        markup('<div class="empty"><div class="symbol">⌁</div><b>Tu próximo hallazgo empieza aquí</b><br><small>Elige una sugerencia o escribe tu pregunta para explorar.</small></div>')


def datasets(db_id):
    with st.spinner('Preparando catálogo…'):
        import pandas as pd
    st.title('Conoce tus datos')
    st.write(LABELS[db_id][1])
    st.caption('BIRD Mini-Dev · CC BY-SA 4.0 · Edición fijada: 2025-07-04')
    tables = catalog()[db_id]['tables']
    table = st.selectbox('Explorar tabla', [t['name'] for t in tables])
    chosen = next(t for t in tables if t['name']==table)
    tab1,tab2 = st.tabs(['Estructura', 'Vista previa'])
    with tab1:
        st.dataframe(pd.DataFrame(chosen['columns']).rename(columns={'name':'Columna','type':'Tipo','not_null':'Obligatoria','primary_key':'Clave primaria'}), hide_index=True, width='stretch')
        if chosen['foreign_keys']:
            st.markdown('**Relaciones con otras tablas**')
            st.dataframe(chosen['foreign_keys'], hide_index=True, width='stretch')
    with tab2:
        st.caption('Muestra de hasta 20 filas del archivo local. No se envía al modelo.')
        if st.button('Cargar vista previa', icon=':material/table_view:'):
            try:
                output = execute(db_path(db_id), 'SELECT * FROM "'+table.replace('"','""')+'" LIMIT 20')
                if output['status']=='ok':
                    st.dataframe(pd.DataFrame(output['rows'], columns=output['columns']), hide_index=True, width='stretch')
                else: st.error(output.get('error') or output['status'])
            except (OSError, ValueError):
                st.error('Descarga los datos con python tasks.py fetch-data.')
    st.divider()
    st.markdown('#### Un catálogo para preguntas diferentes')
    pairs = st.columns(2)
    for i,(key,value) in enumerate(LABELS.items()):
        with pairs[i%2]:
            with st.container(border=True):
                st.markdown('**'+value[0]+'**')
                st.caption(value[1])
                st.caption(f"{len(catalog()[key]['tables'])} tablas · {key}")


def evaluations():
    with st.spinner('Preparando métricas…'):
        import pandas as pd
        import plotly.express as px
    st.title('Evidencia, no promesas')
    st.write('Calidad medida sobre consultas ejecutadas. Cada corrida conserva sus predicciones y configuración.')
    runs = []
    for path in sorted((ROOT/'artifacts/runs').glob('*/summary.json'), reverse=True):
        try:
            report = json.loads(path.read_text())
            manifest = json.loads((path.parent/'manifest.json').read_text())
            runs.append((path.parent,report,manifest))
        except (OSError, ValueError):
            continue
    if not runs:
        st.info('No hay corridas registradas. Ejecuta python tasks.py eval --baseline --split dev.')
        return
    choice = st.selectbox('Corrida', range(len(runs)), format_func=lambda i:runs[i][0].name)
    path, report, manifest = runs[choice]
    st.caption(f"Partición: {manifest.get('split')} · Idioma: {manifest.get('language')} · {manifest.get('config')}")
    cols = st.columns(3)
    with cols[0]: kpi('EXACTITUD POR EJECUCIÓN', f"{report['execution_accuracy']:.1%}" if report.get('execution_accuracy') is not None else 'Sin referencias', 'Sobre referencias ejecutables')
    with cols[1]: kpi('CASOS EVALUADOS', report.get('n',0), 'Predicciones ausentes cuentan como fallos')
    with cols[2]: kpi('COBERTURA DE REFERENCIAS', f"{report['reference_coverage']:.1%}" if report.get('reference_coverage') is not None else 'Sin casos', 'Consultas gold dentro de los límites')
    scores = pd.DataFrame(read_jsonl(path/'scores.jsonl'))
    if not scores.empty:
        bydb = scores.groupby('db_id', as_index=False).agg(Aciertos=('correct','sum'), Casos=('correct','size'))
        fig = px.bar(bydb, x='db_id', y='Aciertos', color_discrete_sequence=['#609f7b'], hover_data=['Casos'])
        fig.update_layout(template='plotly_white', xaxis_title=None, margin=dict(t=15,l=0,r=10,b=0))
        st.plotly_chart(fig, width='stretch')
        with st.expander('Resultados por caso'):
            st.dataframe(scores, hide_index=True, width='stretch')
    st.download_button('Descargar métricas', json.dumps(report, ensure_ascii=False, indent=2), 'metricas.json', 'application/json')
    with st.expander('Manifiesto de reproducibilidad'): st.json(manifest)
    st.caption('Una consulta ejecutable no garantiza una respuesta correcta. BIRD es público y puede estar presente en el preentrenamiento.')


def main():
    load_dotenv(ROOT/'.env')
    st.set_page_config(page_title='DatoClaro · Conversa con tus datos', page_icon='✳', layout='wide', initial_sidebar_state='expanded')
    markup('<style>'+(ROOT/'app/styles.css').read_text()+'</style>')
    if 'history' not in st.session_state: st.session_state.history = []
    # Secrets son del servidor; no se piden al visitante ni se escriben en el historial.
    try:
        for key in ('ANTHROPIC_API_KEY','DATOCLARO_MODEL','DATOCLARO_PROVIDER','DATOCLARO_RETRIEVAL','OLLAMA_HOST','DATOCLARO_PRICES_JSON'):
            if key in st.secrets and not os.getenv(key): os.environ[key]=str(st.secrets[key])
    except FileNotFoundError:
        pass
    with st.sidebar:
        markup('<div class="brand"><span class="brand-mark">✳</span> datoclaro<span style="color:#9ac18c">.</span></div><div class="brand-sub">INTELIGENCIA QUE SE ENTIENDE</div>')
        markup('<div class="nav-label">WORKSPACE</div>')
        page = st.radio('Navegación', ['Explorar','Catálogo de datos','Historial','Evaluación','Acerca del proyecto'], label_visibility='collapsed')
        st.divider()
        markup('<div class="nav-label">TU CONTEXTO</div>')
        db_id = st.selectbox('Fuente de datos', list(LABELS), format_func=lambda key:LABELS[key][0])
        options = ['Demostración guiada','Claude API','Ollama local']
        mode = st.selectbox('Motor de análisis', options, index=1 if os.getenv('ANTHROPIC_API_KEY') else 0)
        markup('<div class="side-note"><b>De la pregunta a la evidencia.</b><br>Cada respuesta conserva la consulta y los datos que la sustentan.</div>')
        st.caption('BIRD Mini-Dev · 11 bases públicas')
    markup(f'<div class="topline"><span>Workspace &nbsp; / &nbsp; <strong>{html.escape(page)}</strong></span><span class="status-pill">● &nbsp; {html.escape(mode)}</span></div>')
    if page == 'Explorar': workspace(db_id, mode)
    elif page == 'Catálogo de datos': datasets(db_id)
    elif page == 'Evaluación': evaluations()
    elif page == 'Historial':
        st.title('El camino de tus hallazgos')
        st.caption('Últimos 20 análisis de esta sesión. Se eliminan al cerrar o reiniciar la sesión.')
        if st.button('Borrar historial', icon=':material/delete:'):
            st.session_state.history=[]
            st.session_state.pop('result',None)
            st.rerun()
        if not st.session_state.history: st.info('Tus análisis aparecerán aquí.')
        for item in st.session_state.history:
            with st.expander(item['question'] or 'Pregunta vacía'): show_result(item)
    else:
        st.title('Claridad en cada respuesta.')
        st.write('DatoClaro convierte preguntas en español en consultas verificables sobre datos públicos. Está pensado para explorar información administrativa sin escribir SQL.')
        st.markdown('#### De una pregunta a un resultado')
        for title,desc in [('01 · Contexto','Recuperamos tablas, relaciones y ejemplos de una partición separada.'),('02 · Consulta','Claude u Ollama generan una consulta de lectura. El motor impide modificaciones.'),('03 · Evidencia','La tabla, el gráfico y el resumen provienen de la consulta ejecutada.')]:
            with st.container(border=True):
                st.markdown('**'+title+'**'); st.write(desc)
        st.info('Los datos son históricos. El sistema puede interpretar mal una pregunta. Verifica filtros y columnas antes de tomar decisiones; el dominio clínico no proporciona recomendaciones médicas.')
        st.markdown('[Procedencia BIRD](https://bird-bench.github.io/) · [Dataset y licencia](https://huggingface.co/datasets/birdsql/bird_mini_dev)')
        st.caption('En modo Claude se envían la pregunta, el esquema recuperado y ejemplos kb al proveedor. Las filas de resultado permanecen en el servidor. En Ollama se usa el host configurado por el operador.')
    markup('<div class="footer"><span>DatoClaro · Hecho para entender</span><span>Datos públicos. Respuestas verificables.</span></div>')
