import streamlit as st
import pandas as pd
import io
import unicodedata
import requests
from datetime import datetime, timezone

st.set_page_config(page_title="CONCILIA PREFEITURA", page_icon="🔍", layout="wide")

st.markdown("""
<style>
.metric-card { background:#f8f9fa; border-radius:12px; padding:20px; text-align:center; border-left:5px solid #ccc; }
.card-verde { border-left-color:#28a745; }
.card-vermelho { border-left-color:#dc3545; }
.card-amarelo { border-left-color:#ffc107; }
.card-azul { border-left-color:#007bff; }
.card-titulo { font-size:14px; color:#666; margin-bottom:4px; }
.card-valor { font-size:32px; font-weight:bold; }
.status-ok { color:#28a745; font-weight:bold; }
.status-err { color:#dc3545; font-weight:bold; }
.status-warn { color:#ffc107; font-weight:bold; }
.status-div { color:#fd7e14; font-weight:bold; }
</style>
""", unsafe_allow_html=True)

def init_session():
    defaults = {
        'logado': False,
        'usuario': None,
        'nome_exibicao': None,
        'perfil': None,
        'resultado': None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def get_supabase_config():
    return {
        'url': st.secrets['supabase']['url'].rstrip('/'),
        'key': st.secrets['supabase']['key']
    }

def sb_headers(prefer=None):
    cfg = get_supabase_config()
    headers = {
        'apikey': cfg['key'],
        'Authorization': f"Bearer {cfg['key']}",
        'Content-Type': 'application/json'
    }
    if prefer:
        headers['Prefer'] = prefer
    return headers

def sb_table_url(table_name):
    cfg = get_supabase_config()
    return f"{cfg['url']}/rest/v1/{table_name}"

def sb_insert(table_name, payload, return_representation=True):
    prefer = 'return=representation' if return_representation else 'return=minimal'
    resp = requests.post(sb_table_url(table_name), headers=sb_headers(prefer=prefer), json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Erro Supabase INSERT em {table_name}: {resp.status_code} - {resp.text}")
    if return_representation:
        data = resp.json()
        return data if isinstance(data, list) else [data]
    return []

def sb_select(table_name, query='select=*'):
    resp = requests.get(f"{sb_table_url(table_name)}?{query}", headers=sb_headers(), timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Erro Supabase SELECT em {table_name}: {resp.status_code} - {resp.text}")
    return resp.json()

def autenticar(username, password):
    admin_user = st.secrets['auth']['admin_user']
    admin_name = st.secrets['auth']['admin_name']
    admin_password = st.secrets['auth']['admin_password']

    user_user = st.secrets['auth']['user_user']
    user_name = st.secrets['auth']['user_name']
    user_password = st.secrets['auth']['user_password']

    if username == admin_user and password == admin_password:
        return {'username': admin_user, 'nome_exibicao': admin_name, 'perfil': 'admin'}
    if username == user_user and password == user_password:
        return {'username': user_user, 'nome_exibicao': user_name, 'perfil': 'user'}
    return None

def salvar_historico(resultado, usuario, perfil, empresa, arquivo_omie, arquivo_pref):
    payload_conc = {
        'usuario': usuario,
        'perfil': perfil,
        'empresa': empresa,
        'arquivo_omie': arquivo_omie,
        'arquivo_pref': arquivo_pref,
        'total_nfes': int(len(resultado)),
        'conciliadas': int((resultado['Status'] == 'Conciliado').sum()),
        'divergencia_valor': int((resultado['Status'] == 'Divergência de Valor').sum()),
        'ausente_prefeitura': int((resultado['Status'] == 'Ausente na Prefeitura').sum()),
        'ausente_omie': int((resultado['Status'] == 'Ausente no OMIE').sum()),
        'criado_em': datetime.now(timezone.utc).isoformat()
    }

    inserted = sb_insert('conciliacoes', payload_conc, return_representation=True)
    conciliacao_id = inserted[0]['id']

    itens = []
    for _, r in resultado.iterrows():
        itens.append({
            'conciliacao_id': conciliacao_id,
            'nfe': str(r['NFE']) if pd.notna(r['NFE']) else None,
            'nome_omie': None if pd.isna(r.get('Nome_OMIE')) else str(r['Nome_OMIE']),
            'nome_pref': None if pd.isna(r.get('Nome_Pref')) else str(r['Nome_Pref']),
            'valor_omie': float(r['Valor_OMIE']) if pd.notna(r['Valor_OMIE']) else 0,
            'valor_pref': float(r['Valor_Pref']) if pd.notna(r['Valor_Pref']) else 0,
            'dif_valor': float(r['Dif_Valor']) if pd.notna(r['Dif_Valor']) else 0,
            'status': str(r['Status']),
            'empresa': empresa,
            'criado_em': datetime.now(timezone.utc).isoformat()
        })

    if itens:
        sb_insert('conciliacao_itens', itens, return_representation=False)

def carregar_historico():
    data = sb_select('conciliacoes', 'select=*&order=criado_em.desc')
    return pd.DataFrame(data)

def carregar_estudo_empresas():
    data = sb_select('conciliacao_itens', 'select=empresa,status&status=neq.Conciliado')
    df = pd.DataFrame(data)
    if df.empty:
        return df
    df = df[df['empresa'].notna() & (df['empresa'].astype(str).str.strip() != '')].copy()
    if df.empty:
        return df
    estudo = df.groupby('empresa').agg(
        total_itens_problema=('empresa', 'count'),
        divergencia_valor=('status', lambda x: (x == 'Divergência de Valor').sum()),
        ausente_prefeitura=('status', lambda x: (x == 'Ausente na Prefeitura').sum()),
        ausente_omie=('status', lambda x: (x == 'Ausente no OMIE').sum()),
    ).reset_index().sort_values(['total_itens_problema', 'empresa'], ascending=[False, True])
    return estudo

def clean_valor(v):
    if pd.isna(v) or v == '':
        return 0.0
    try:
        v = str(v).strip()
        v = v.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        result = float(v)
        return max(result, 0.0)
    except:
        return 0.0

def status_badge(s):
    cores = {
        'Conciliado': '<span class="status-ok">✅ Conciliado</span>',
        'Divergência de Valor': '<span class="status-div">🔶 Divergência de Valor</span>',
        'Ausente na Prefeitura': '<span class="status-err">❌ Ausente na Prefeitura</span>',
        'Ausente no OMIE': '<span class="status-warn">⚠️ Ausente no OMIE</span>',
    }
    return cores.get(s, s)

def normalize_col_name(name):
    text = str(name).strip().lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace('-', ' ').replace('_', ' ')
    text = ' '.join(text.split())
    return text

def resolve_columns(df, required_map, source_name):
    normalized_to_original = {normalize_col_name(col): col for col in df.columns}
    resolved = {}
    missing = []
    for target_col, aliases in required_map.items():
        found = None
        for alias in aliases:
            normalized_alias = normalize_col_name(alias)
            if normalized_alias in normalized_to_original:
                found = normalized_to_original[normalized_alias]
                break
        if found is None:
            missing.append(target_col)
        else:
            resolved[target_col] = found
    if missing:
        available = ', '.join(str(col) for col in df.columns)
        expected = ', '.join(missing)
        raise ValueError(f"Arquivo {source_name}: não encontrei as colunas obrigatórias ({expected}). Colunas disponíveis: {available}")
    return resolved

OMIE_REQUIRED_COLUMNS = {
    'NFE': ['Número da NFS-e', 'Numero da NFS-e', 'NFS-e', 'NFS e', 'Numero NFS-e'],
    'Nome_OMIE': ['Cliente (Nome Fantasia)', 'Cliente', 'Nome Fantasia', 'Razão Social'],
    'Valor_OMIE': ['Valor Líquido', 'Valor Liquido', 'Valor', 'Valor Total'],
}

PREF_REQUIRED_COLUMNS = {
    'NFE': ['Nº NFS-e', 'N° NFS-e', 'Numero NFS-e', 'Número NFS-e', 'NFS-e'],
    'Nome_Pref': ['Razão Social do Tomador', 'Razao Social do Tomador', 'Tomador', 'Razão Social'],
    'Valor_Pref': [' Valor dos Serviços ', 'Valor dos Serviços', 'Valor dos Servicos', 'Valor Serviço', 'Valor Servico'],
}

def processar_omie(file):
    df = pd.read_excel(file)
    cols = resolve_columns(df, OMIE_REQUIRED_COLUMNS, 'OMIE')
    df = df[df[cols['NFE']].notna()].copy()
    df[cols['NFE']] = pd.to_numeric(df[cols['NFE']], errors='coerce')
    df = df[df[cols['NFE']].notna()].copy()
    if len(df) == 0:
        raise ValueError('Nenhuma NFE válida encontrada no arquivo OMIE')
    df[cols['NFE']] = df[cols['NFE']].astype(int)
    df[cols['Valor_OMIE']] = pd.to_numeric(df[cols['Valor_OMIE']], errors='coerce').fillna(0).astype(float)
    agg = df.groupby(cols['NFE']).agg(
        Nome_OMIE=(cols['Nome_OMIE'], 'first'),
        Valor_OMIE=(cols['Valor_OMIE'], 'sum'),
    ).reset_index()
    agg.columns = ['NFE', 'Nome_OMIE', 'Valor_OMIE']
    agg['Valor_OMIE'] = agg['Valor_OMIE'].fillna(0).astype(float)
    return agg

def processar_pref(file):
    try:
        df = pd.read_csv(file, encoding='latin-1', sep=None, engine='python')
    except Exception:
        try:
            df = pd.read_csv(file, encoding='utf-8', sep=None, engine='python')
        except Exception as e:
            raise ValueError(f'Não consegui ler o arquivo CSV da Prefeitura. Erro: {e}')
    cols = resolve_columns(df, PREF_REQUIRED_COLUMNS, 'Prefeitura')
    df = df[df[cols['NFE']].notna()].copy()
    df[cols['NFE']] = pd.to_numeric(df[cols['NFE']], errors='coerce')
    df = df[df[cols['NFE']].notna()].copy()
    if len(df) == 0:
        raise ValueError('Nenhuma NFE válida encontrada no arquivo da Prefeitura')
    df[cols['NFE']] = df[cols['NFE']].astype(int)
    df[cols['Valor_Pref']] = df[cols['Valor_Pref']].apply(clean_valor).astype(float)
    return df[[cols['NFE'], cols['Nome_Pref'], cols['Valor_Pref']]].rename(columns={
        cols['NFE']: 'NFE',
        cols['Nome_Pref']: 'Nome_Pref',
        cols['Valor_Pref']: 'Valor_Pref'
    })

def conciliar(omie, pref):
    if omie.empty or pref.empty:
        raise ValueError('Um dos arquivos após processamento ficou vazio')
    merged = omie.merge(pref, on='NFE', how='outer', indicator=True)
    merged['Valor_OMIE'] = merged['Valor_OMIE'].fillna(0).astype(float)
    merged['Valor_Pref'] = merged['Valor_Pref'].fillna(0).astype(float)
    merged['Dif_Valor'] = (merged['Valor_OMIE'] - merged['Valor_Pref']).round(2)

    def get_status(row):
        if row['_merge'] == 'left_only':
            return 'Ausente na Prefeitura'
        if row['_merge'] == 'right_only':
            return 'Ausente no OMIE'
        if abs(row['Dif_Valor']) < 0.01:
            return 'Conciliado'
        return 'Divergência de Valor'

    merged['Status'] = merged.apply(get_status, axis=1)
    merged = merged.drop(columns=['_merge']).sort_values('NFE').reset_index(drop=True)
    return merged

def to_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Conciliação')
    return buf.getvalue()

init_session()

if not st.session_state['logado']:
    st.title('🔐 Login - Concilia Prefeitura')
    st.markdown('Acesse com seu usuário para usar o sistema.')

    with st.form('login_form'):
        perfil_login = st.selectbox('Selecione o acesso', ['Administrador', 'Equipe'])
        password = st.text_input('Senha', type='password')
        submit = st.form_submit_button('Entrar', use_container_width=True)

    if submit:
        username = 'vinicius' if perfil_login == 'Administrador' else 'Equipe'
        user = autenticar(username, password)

        if user:
            st.session_state['logado'] = True
            st.session_state['usuario'] = user['username']
            st.session_state['nome_exibicao'] = user['nome_exibicao']
            st.session_state['perfil'] = user['perfil']
            st.rerun()
        else:
            st.error('Usuário ou senha inválidos.')

    st.stop()

col_head1, col_head2 = st.columns([4, 1])
with col_head1:
    st.title('🔍 Conciliação OMIE × Prefeitura')
    st.markdown('Faça o upload dos dois arquivos e clique em **Conciliar** para identificar divergências automaticamente.')
    st.subheader('Feito por: Vinícius Sena')
    st.markdown('Qualquer erro ou problema, pode me chamar no TEAMS!')
with col_head2:
    st.write(f"**Usuário:** {st.session_state['nome_exibicao']}")
    st.write(f"**Perfil:** {st.session_state['perfil']}")
    if st.button('Sair', use_container_width=True):
        st.session_state['logado'] = False
        st.session_state['usuario'] = None
        st.session_state['nome_exibicao'] = None
        st.session_state['perfil'] = None
        st.session_state['resultado'] = None
        st.rerun()

st.divider()
abas = ['Conciliação', 'Histórico']
if st.session_state['perfil'] == 'admin':
    abas.append('Estudo por Empresa')
aba = st.radio('Menu', abas, horizontal=True)

if aba == 'Conciliação':
    empresa = st.text_input('Nome da empresa', placeholder='Ex.: Empresa XPTO')
    col1, col2 = st.columns(2)
    with col1:
        st.subheader('📄 Arquivo OMIE')
        file_omie = st.file_uploader('Selecione o Excel do OMIE', type=['xlsx', 'xls'], key='omie')
        if file_omie:
            st.success(f'✅ {file_omie.name} carregado!')
    with col2:
        st.subheader('🏛️ Extrato da Prefeitura')
        file_pref = st.file_uploader('Selecione o CSV da Prefeitura', type=['csv'], key='pref')
        if file_pref:
            st.success(f'✅ {file_pref.name} carregado!')

    st.divider()

    if file_omie and file_pref:
        if st.button('🚀 Conciliar Agora', type='primary', use_container_width=True):
            if not empresa.strip():
                st.error('Informe o nome da empresa antes de conciliar.')
            else:
                with st.spinner('Processando conciliação...'):
                    try:
                        omie = processar_omie(file_omie)
                        st.success(f'✅ OMIE processado: {len(omie)} NFEs válidas')
                        pref = processar_pref(file_pref)
                        st.success(f'✅ Prefeitura processado: {len(pref)} NFEs válidas')
                        resultado = conciliar(omie, pref)
                        st.session_state['resultado'] = resultado
                        salvar_historico(resultado, st.session_state['usuario'], st.session_state['perfil'], empresa.strip(), file_omie.name, file_pref.name)
                        st.success(f'✅ Conciliação completa: {len(resultado)} registros processados e histórico salvo')
                    except Exception as e:
                        st.error(f'❌ Erro: {e}')
    else:
        st.info('⬆️ Faça o upload dos dois arquivos para habilitar a conciliação.')

    if st.session_state['resultado'] is not None:
        resultado = st.session_state['resultado']
        total = len(resultado)
        ok = (resultado['Status'] == 'Conciliado').sum()
        div_val = (resultado['Status'] == 'Divergência de Valor').sum()
        aus_pref = (resultado['Status'] == 'Ausente na Prefeitura').sum()
        aus_omie = (resultado['Status'] == 'Ausente no OMIE').sum()

        st.subheader('📊 Resumo da Conciliação')
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.markdown(f"<div class='metric-card card-azul'><div class='card-titulo'>Total de NFEs</div><div class='card-valor'>{total}</div></div>", unsafe_allow_html=True)
        with c2:
            st.markdown(f"<div class='metric-card card-verde'><div class='card-titulo'>Conciliadas</div><div class='card-valor' style='color:#28a745'>{ok}</div></div>", unsafe_allow_html=True)
        with c3:
            st.markdown(f"<div class='metric-card card-vermelho'><div class='card-titulo'>Divergência Valor</div><div class='card-valor' style='color:#fd7e14'>{div_val}</div></div>", unsafe_allow_html=True)
        with c4:
            st.markdown(f"<div class='metric-card card-vermelho'><div class='card-titulo'>Ausente na Pref.</div><div class='card-valor' style='color:#dc3545'>{aus_pref}</div></div>", unsafe_allow_html=True)
        with c5:
            st.markdown(f"<div class='metric-card card-amarelo'><div class='card-titulo'>Ausente no OMIE</div><div class='card-valor' style='color:#ffc107'>{aus_omie}</div></div>", unsafe_allow_html=True)

        pct = int((ok / total) * 100) if total > 0 else 0
        st.markdown(f"<br>**Taxa de conciliação: {pct}%**", unsafe_allow_html=True)
        st.progress(pct / 100)

        st.divider()
        st.subheader('🔎 Detalhamento das NFEs')
        col_f1, col_f2 = st.columns([1, 3])
        with col_f1:
            filtro = st.selectbox('Filtrar por status:', ['Todos', 'Conciliado', 'Divergência de Valor', 'Ausente na Prefeitura', 'Ausente no OMIE'])
        with col_f2:
            busca = st.text_input('Buscar por NFE ou nome do cliente:')

        df_view = resultado.copy()
        if filtro != 'Todos':
            df_view = df_view[df_view['Status'] == filtro]
        if busca:
            mask = (
                df_view['NFE'].astype(str).str.contains(busca, case=False, na=False) |
                df_view['Nome_OMIE'].astype(str).str.contains(busca, case=False, na=False) |
                df_view['Nome_Pref'].astype(str).str.contains(busca, case=False, na=False)
            )
            df_view = df_view[mask]

        df_html = df_view.copy()
        df_html['Status'] = df_html['Status'].apply(status_badge)
        df_html['Valor_OMIE'] = df_html['Valor_OMIE'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        df_html['Valor_Pref'] = df_html['Valor_Pref'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
        df_html['Dif_Valor'] = df_html['Dif_Valor'].apply(lambda x: f"R$ {x:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.') if pd.notna(x) else '-')
        df_html = df_html.rename(columns={
            'NFE': 'Nº NFE',
            'Nome_OMIE': 'Cliente (OMIE)',
            'Nome_Pref': 'Tomador (Prefeitura)',
            'Valor_OMIE': 'Valor OMIE',
            'Valor_Pref': 'Valor Prefeitura',
            'Dif_Valor': 'Diferença',
        })
        st.markdown(df_html.to_html(escape=False, index=False), unsafe_allow_html=True)
        st.caption(f'Mostrando {len(df_view)} de {total} registros.')

        st.divider()
        st.subheader('📥 Exportar Resultado')
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.download_button(
                label='⬇️ Baixar Excel completo',
                data=to_excel(resultado),
                file_name='conciliacao_resultado.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True
            )
        with col_e2:
            erros = resultado[resultado['Status'] != 'Conciliado']
            st.download_button(
                label='⬇️ Baixar apenas erros/divergências',
                data=to_excel(erros),
                file_name='conciliacao_erros.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True,
                disabled=(len(erros) == 0)
            )

elif aba == 'Histórico':
    st.subheader('🕘 Histórico de Conciliações')
    try:
        hist = carregar_historico()
        if hist.empty:
            st.info('Nenhum histórico encontrado ainda.')
        else:
            if st.session_state['perfil'] != 'admin':
                hist = hist[hist['usuario'] == st.session_state['usuario']]
            st.dataframe(hist, use_container_width=True)
            st.download_button(
                label='⬇️ Baixar histórico em Excel',
                data=to_excel(hist),
                file_name='historico_conciliacoes.xlsx',
                mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                use_container_width=True
            )
    except Exception as e:
        st.error(f'Erro ao carregar histórico: {e}')

elif aba == 'Estudo por Empresa':
    if st.session_state['perfil'] != 'admin':
        st.error('Acesso restrito ao administrador.')
    else:
        st.subheader('🏢 Estudo de empresas com mais problemas')
        try:
            estudo = carregar_estudo_empresas()
            if estudo.empty:
                st.info('Ainda não há dados suficientes para análise por empresa.')
            else:
                st.dataframe(estudo, use_container_width=True)
                st.download_button(
                    label='⬇️ Baixar estudo por empresa',
                    data=to_excel(estudo),
                    file_name='estudo_empresas_problemas.xlsx',
                    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    use_container_width=True
                )
        except Exception as e:
            st.error(f'Erro ao carregar estudo por empresa: {e}')