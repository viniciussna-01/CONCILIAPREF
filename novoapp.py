# Código Completo Atualizado — CONCILIA PREFEITURA

import streamlit as st
import pandas as pd
import io
import unicodedata
import requests
from datetime import datetime, timezone
import plotly.graph_objects as go

st.set_page_config(
    page_title="CONCILIA PREFEITURA",
    page_icon="🔍",
    layout="wide"
)

# ==========================
# CSS
# ==========================
st.markdown("""
<style>
.metric-card {
    background:#f8f9fa;
    border-radius:12px;
    padding:20px;
    text-align:center;
    border-left:5px solid #ccc;
}

.card-verde { border-left-color:#28a745; }
.card-vermelho { border-left-color:#dc3545; }
.card-amarelo { border-left-color:#ffc107; }
.card-azul { border-left-color:#007bff; }
.card-roxo { border-left-color:#6f42c1; }

.card-titulo {
    font-size:14px;
    color:#666;
    margin-bottom:4px;
}

.card-valor {
    font-size:32px;
    font-weight:bold;
}

.status-ok {
    color:#28a745;
    font-weight:bold;
}

.status-err {
    color:#dc3545;
    font-weight:bold;
}

.status-warn {
    color:#ffc107;
    font-weight:bold;
}

.status-div {
    color:#fd7e14;
    font-weight:bold;
}
</style>
""", unsafe_allow_html=True)

# ==========================
# SESSION
# ==========================
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

# ==========================
# SUPABASE
# ==========================
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

    resp = requests.post(
        sb_table_url(table_name),
        headers=sb_headers(prefer=prefer),
        json=payload,
        timeout=30
    )

    if not resp.ok:
        raise RuntimeError(
            f"Erro Supabase INSERT em {table_name}: {resp.status_code} - {resp.text}"
        )

    if return_representation:
        data = resp.json()
        return data if isinstance(data, list) else [data]

    return []


def sb_select(table_name, query='select=*'):
    resp = requests.get(
        f"{sb_table_url(table_name)}?{query}",
        headers=sb_headers(),
        timeout=30
    )

    if not resp.ok:
        raise RuntimeError(
            f"Erro Supabase SELECT em {table_name}: {resp.status_code} - {resp.text}"
        )

    return resp.json()

# ==========================
# LOGIN
# ==========================
def autenticar(username, password):

    usuarios = {

        st.secrets['auth']['admin_user']: {
            'nome_exibicao': st.secrets['auth']['admin_name'],
            'senha': st.secrets['auth']['admin_password'],
            'perfil': 'admin'
        },

        st.secrets['auth']['daniela_user']: {
            'nome_exibicao': 'Daniela',
            'senha': st.secrets['auth']['daniela_password'],
            'perfil': 'user'
        },

        st.secrets['auth']['victor_user']: {
            'nome_exibicao': 'Victor',
            'senha': st.secrets['auth']['victor_password'],
            'perfil': 'user'
        },

        st.secrets['auth']['suelen_user']: {
            'nome_exibicao': 'Suelen',
            'senha': st.secrets['auth']['suelen_password'],
            'perfil': 'user'
        },
    }

    user = usuarios.get(username)

    if user and password == user['senha']:
        return {
            'username': username,
            'nome_exibicao': user['nome_exibicao'],
            'perfil': user['perfil']
        }

    return None

# ==========================
# HELPERS
# ==========================
def normalize_col_name(name):
    text = str(name).strip().lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace('-', ' ').replace('_', ' ')
    text = ' '.join(text.split())
    return text


def clean_valor(v):
    if pd.isna(v) or v == '':
        return 0.0

    try:
        if not isinstance(v, str):
            return float(v)

        text = v.strip()
        text = text.replace('R$', '')
        text = text.replace(' ', '')

        # Trata formatos brasileiros e internacionais sem multiplicar por 100.
        if ',' in text and '.' in text:
            if text.rfind(',') > text.rfind('.'):
                text = text.replace('.', '')
                text = text.replace(',', '.')
            else:
                text = text.replace(',', '')
        elif ',' in text:
            text = text.replace(',', '.')

        return float(text)

    except:
        return 0.0


def clean_documento(doc):

    if pd.isna(doc):
        return ''

    return ''.join(filter(str.isdigit, str(doc)))


def identificar_tipo_documento(doc):

    if doc == '':
        return 'POSSIVELMENTE ESTRANGEIRO'

    if set(doc) == {'0'}:
        return 'POSSIVELMENTE ESTRANGEIRO'

    if len(doc) == 11:
        return 'CPF'

    if len(doc) == 14:
        return 'CNPJ'

    return 'ESTRANGEIRO'


def identificar_tipo_documento(doc):

    if pd.isna(doc):
        return 'POSSIVELMENTE ESTRANGEIRO'

    doc = ''.join(filter(str.isdigit, str(doc)))

    if doc == '':
        return 'POSSIVELMENTE ESTRANGEIRO'

    if set(doc) == {'0'}:
        return 'POSSIVELMENTE ESTRANGEIRO'

    if len(doc) == 11:
        return 'CPF'

    if len(doc) == 14:
        return 'CNPJ'

    return 'ESTRANGEIRO'


def resolve_columns(df, required_map, source_name):

    normalized_to_original = {
        normalize_col_name(col): col
        for col in df.columns
    }

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
        raise ValueError(
            f"Arquivo {source_name}: não encontrei as colunas obrigatórias: {', '.join(missing)}"
        )

    return resolved


def find_column_by_aliases(columns, aliases):

    normalized_to_original = {
        normalize_col_name(col): col
        for col in columns
    }

    for alias in aliases:
        normalized_alias = normalize_col_name(alias)
        if normalized_alias in normalized_to_original:
            return normalized_to_original[normalized_alias]

    return None


def status_badge(s):

    cores = {
        'Conciliado': '<span class="status-ok">✅ Conciliado</span>',
        'Divergência de Valor': '<span class="status-div">🔶 Divergência</span>',
        'Ausente na Prefeitura': '<span class="status-err">❌ Ausente Prefeitura</span>',
        'Ausente no OMIE': '<span class="status-warn">⚠️ Ausente OMIE</span>',
        'NOTA CANCELADA': '<span class="status-err">🚫 Nota Cancelada</span>',
        'POSSIVELMENTE ESTRANGEIRO': '<span class="status-warn">🌎 Possivelmente Estrangeiro</span>',
        'ESTRANGEIRO': '<span class="status-warn">🌍 Estrangeiro</span>',
    }

    return cores.get(s, s)

# ==========================
# COLUNAS
# ==========================
OMIE_REQUIRED_COLUMNS = {

    'NFE': [
        'Número da NFS-e',
        'Numero da NFS-e',
        'NFS-e'
    ],

    'Nome_OMIE': [
        'Cliente (Nome Fantasia)',
        'Cliente (Razão Social)',
        'Cliente'
    ],

    'Valor_OMIE': [
        'Valor Líquido',
        'Valor'
    ]
}


PREF_REQUIRED_COLUMNS = {

    'NFE': [
        'Número (nNFSe)', 'Numero (nNFSe)', 'nNFSe',
        'Nº NFS-e', 'N° NFS-e', 'Numero NFS-e',
        'Número NFS-e', 'NFS-e',
    ],

    'Nome_Pref': [
        'Tomador (xNome)', 'xNome',
        'Razão Social do Tomador',
        'Razao Social do Tomador',
        'Tomador',
        'Razão Social',
    ],

    'Valor_Pref': [
        'Valor Líquido (R$) (vLiq)',
        'Valor Liquido (R$) (vLiq)',
        'vLiq',
        'Valor Serviço (R$) (vServ)',
        'vServ',
        ' Valor dos Serviços ',
        'Valor dos Serviços',
        'Valor dos Servicos',
        'Valor Serviço',
        'Valor Servico',
    ],

}

# ==========================
# PROCESSAR OMIE
# ==========================
def processar_omie(file):

    raw = pd.read_excel(file, header=None)

    header_row = None

    required_aliases = [
        alias
        for aliases in OMIE_REQUIRED_COLUMNS.values()
        for alias in aliases
    ]

    for i in range(min(50, len(raw))):

        row_values = [str(v).strip() for v in raw.iloc[i].tolist()]
        normalized = [normalize_col_name(v) for v in row_values]

        matches = sum(
            1 for alias in required_aliases
            if normalize_col_name(alias) in normalized
        )

        if matches >= 2:
            header_row = i
            break

    if header_row is None:
        preview_rows = []
        for i in range(min(10, len(raw))):
            row_values = [str(v).strip() for v in raw.iloc[i].tolist()]
            preview_rows.append(' | '.join(v for v in row_values if v and v != 'nan'))

        raise ValueError(
            'Cabeçalho do OMIE não encontrado. '
            'Verifique se o arquivo é a exportação correta do OMIE e se as colunas '
            f'estão em um formato reconhecível. Primeiras linhas: {preview_rows}'
        )

    file.seek(0)

    df = pd.read_excel(file, header=header_row)

    cols = resolve_columns(df, OMIE_REQUIRED_COLUMNS, 'OMIE')

    df = df[df[cols['NFE']].notna()].copy()

    df[cols['NFE']] = pd.to_numeric(
        df[cols['NFE']],
        errors='coerce'
    )

    df = df[df[cols['NFE']].notna()].copy()

    df[cols['NFE']] = df[cols['NFE']].astype(int)

    df[cols['Valor_OMIE']] = pd.to_numeric(
        df[cols['Valor_OMIE']],
        errors='coerce'
    ).fillna(0)

    agg = df.groupby(cols['NFE']).agg(
        Nome_OMIE=(cols['Nome_OMIE'], 'first'),
        Valor_OMIE=(cols['Valor_OMIE'], 'sum')
    ).reset_index()

    agg.columns = ['NFE', 'Nome_OMIE', 'Valor_OMIE']

    return agg

# ==========================
# PROCESSAR PREFEITURA
# ==========================
def processar_pref(file):

    file_name = str(getattr(file, 'name', '')).lower()

    if file_name.endswith(('.xlsx', '.xls')):
        try:
            df = pd.read_excel(file)
        except Exception as e:
            raise ValueError(
                f"Não consegui ler o arquivo Excel da Prefeitura. Erro: {e}"
            )
    else:
        try:
            df = pd.read_csv(file, encoding='utf-8-sig', sep=';')

        except Exception:

            try:
                file.seek(0)
                df = pd.read_csv(file, encoding='latin-1', sep=';')

            except Exception:

                try:
                    file.seek(0)
                    df = pd.read_csv(file, encoding='utf-8', sep=';')

                except Exception as e:
                    raise ValueError(
                        f"Não consegui ler o arquivo da Prefeitura (CSV/Excel). Erro: {e}"
                    )

    df.columns = [str(c).strip() for c in df.columns]

    if 'Tipo de Registro' in df.columns:

        df = df[
            df['Tipo de Registro']
            .astype(str)
            .str.strip()
            .str.lower() != 'total'
        ].copy()

    cols = resolve_columns(
        df,
        PREF_REQUIRED_COLUMNS,
        'Prefeitura'
    )

    cpf_cnpj_col = find_column_by_aliases(
        df.columns,
        [
            'Tomador (CNPJ / CPF / NIF)',
            'CPF/CNPJ do Tomador',
            'CPF/CNPJ Tomador',
            'CPF CNPJ'
        ]
    )

    situacao_col = find_column_by_aliases(
        df.columns,
        [
            'Situação NFS-e (cStat)',
            'Situacao NFS-e (cStat)',
            'Situação NFS-e',
            'Situacao NFS-e',
            'cStat',
            'Situação da Nota Fiscal',
            'Situacao da Nota Fiscal'
        ]
    )

    data_cancelamento_col = find_column_by_aliases(
        df.columns,
        [
            'Data de Cancelamento (dhCanc)',
            'Data Cancelamento (dhCanc)',
            'dhCanc',
            'Data de Cancelamento',
            'Data Cancelamento'
        ]
    )

    df = df[df[cols['NFE']].notna()].copy()

    df[cols['NFE']] = pd.to_numeric(
        df[cols['NFE']],
        errors='coerce'
    )

    df = df[df[cols['NFE']].notna()].copy()

    if len(df) == 0:
        raise ValueError(
            "Nenhuma NFE válida encontrada no arquivo da Prefeitura"
        )

    df[cols['NFE']] = df[cols['NFE']].astype(int)

    # VALOR
    df[cols['Valor_Pref']] = (
        df[cols['Valor_Pref']]
        .apply(clean_valor)
        .astype(float)
    )

    # VALOR FINAL
    df['Valor_Final_Pref'] = (
        df[cols['Valor_Pref']]
        .copy()
    )

    # CPF/CNPJ
    if cpf_cnpj_col is not None:
        df['CPF_CNPJ'] = df[cpf_cnpj_col].apply(clean_documento)
    else:
        df['CPF_CNPJ'] = ''

    df['Tipo_Pessoa'] = (
        df['CPF_CNPJ']
        .apply(identificar_tipo_documento)
    )

    cpf_mask = df['Tipo_Pessoa'] == 'CPF'
    df.loc[cpf_mask, 'CPF_CNPJ'] = (
        df.loc[cpf_mask, 'CPF_CNPJ']
        .astype(str)
        .str.zfill(11)
    )

    # CANCELADA
    cancel_por_status = pd.Series(False, index=df.index)
    cancel_por_data = pd.Series(False, index=df.index)

    if situacao_col is not None:
        status_num = pd.to_numeric(df[situacao_col], errors='coerce')
        cancel_por_codigo = status_num.eq(2)

        cancel_por_status = (
            df[situacao_col]
            .astype(str)
            .str.strip()
            .str.contains(
                r'(^C$|cancel)',
                case=False,
                na=False,
                regex=True
            )
        ) | cancel_por_codigo

    if data_cancelamento_col is not None:
        cancel_por_data = (
            df[data_cancelamento_col].notna()
            & df[data_cancelamento_col].astype(str).str.strip().ne('')
        )

    df['Nota_Cancelada'] = cancel_por_status | cancel_por_data

    df = df.rename(columns={

        cols['NFE']: 'NFE',
        cols['Nome_Pref']: 'Nome_Pref',
        cols['Valor_Pref']: 'Valor_Pref',

    })

    return df[
        [
            'NFE',
            'Nome_Pref',
            'Valor_Pref',
            'Valor_Final_Pref',
            'CPF_CNPJ',
            'Tipo_Pessoa',
            'Nota_Cancelada'
        ]
    ]

# ==========================
# CONCILIAÇÃO
# ==========================
def conciliar(omie, pref):

    if omie.empty or pref.empty:
        raise ValueError(
            'Um dos arquivos após processamento ficou vazio'
        )

    merged = omie.merge(
        pref,
        on='NFE',
        how='outer',
        indicator=True
    )

    merged['Valor_OMIE'] = (
        merged['Valor_OMIE']
        .fillna(0)
        .astype(float)
    )

    merged['Valor_Final_Pref'] = (
        merged['Valor_Final_Pref']
        .fillna(0)
        .astype(float)
    )

    merged['Dif_Valor'] = (
        merged['Valor_OMIE']
        - merged['Valor_Final_Pref']
    ).round(2)

    def get_status(row):

        if row.get('Nota_Cancelada') == True:
            return 'NOTA CANCELADA'

        if row['_merge'] == 'left_only':
            return 'Ausente na Prefeitura'

        if row['_merge'] == 'right_only':
            return 'Ausente no OMIE'

        if row.get('Tipo_Pessoa') == 'POSSIVELMENTE ESTRANGEIRO':
            return 'POSSIVELMENTE ESTRANGEIRO'

        if row.get('Tipo_Pessoa') == 'ESTRANGEIRO':
            return 'ESTRANGEIRO'

        if abs(row['Dif_Valor']) < 0.01:
            return 'Conciliado'

        return 'Divergência de Valor'

    merged['Status'] = merged.apply(
        get_status,
        axis=1
    )

    merged = (
        merged
        .drop(columns=['_merge'])
        .sort_values('NFE')
        .reset_index(drop=True)
    )

    return merged

# ==========================
# EXCEL
# ==========================
def to_excel(df):

    buf = io.BytesIO()

    with pd.ExcelWriter(
        buf,
        engine='openpyxl'
    ) as writer:

        df.to_excel(
            writer,
            index=False,
            sheet_name='Conciliação'
        )

        df[
            df['Status'] != 'Conciliado'
        ].to_excel(
            writer,
            index=False,
            sheet_name='Divergências'
        )

        df[
            df['Tipo_Pessoa'] == 'CNPJ'
        ].to_excel(
            writer,
            index=False,
            sheet_name='CNPJs'
        )

        df[
            df['Tipo_Pessoa'] == 'POSSIVELMENTE ESTRANGEIRO'
        ].to_excel(
            writer,
            index=False,
            sheet_name='Possivelmente Estrangeiro'
        )

        df[
            df['Nota_Cancelada'] == True
        ].to_excel(
            writer,
            index=False,
            sheet_name='Notas Canceladas'
        )

    return buf.getvalue()

# ==========================
# APP
# ==========================
init_session()

st.title('🔍 CONCILIA PREFEITURA')

empresa = st.text_input(
    'Nome da empresa'
)

col1, col2 = st.columns(2)

with col1:
    file_omie = st.file_uploader(
        'Arquivo OMIE',
        type=['xlsx', 'xls']
    )

with col2:
    file_pref = st.file_uploader(
        'Arquivo Prefeitura',
        type=['csv', 'xlsx', 'xls']
    )

if file_omie and file_pref:

    if st.button('🚀 Conciliar Agora'):

        with st.spinner('Processando...'):

            omie = processar_omie(file_omie)
            pref = processar_pref(file_pref)

            resultado = conciliar(omie, pref)

            st.session_state['resultado'] = resultado

if st.session_state['resultado'] is not None:

    resultado = st.session_state['resultado']

    total = len(resultado)

    conciliadas = (
        resultado['Status'] == 'Conciliado'
    ).sum()

    divergencias = (
        resultado['Status'] == 'Divergência de Valor'
    ).sum()

    estrangeiros = (
        resultado['Tipo_Pessoa'] == 'POSSIVELMENTE ESTRANGEIRO'
    ).sum()

    canceladas = (
        resultado['Nota_Cancelada'] == True
    ).sum()

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric('Total NFEs', total)

    with c2:
        st.metric('Conciliadas', conciliadas)

    with c3:
        st.metric('Divergências', divergencias)

    with c4:
        st.metric('Poss. Estrangeiros', estrangeiros)

    labels = [
        'Conciliadas',
        'Divergências',
        'Poss. Estrangeiros',
        'Canceladas'
    ]

    values = [
        conciliadas,
        divergencias,
        estrangeiros,
        canceladas
    ]

    fig = go.Figure(data=[go.Bar(
        x=labels,
        y=values,
        text=values,
        textposition='outside'
    )])

    st.plotly_chart(fig, use_container_width=True)

    st.subheader('🔎 Filtros')

    colf1, colf2, colf3 = st.columns(3)

    with colf1:

        filtro_status = st.selectbox(
            'Status',
            ['Todos'] + list(resultado['Status'].unique())
        )

    with colf2:

        filtro_tipo = st.selectbox(
            'Tipo Documento',
            [
                'Todos',
                'CPF',
                'CNPJ',
                'POSSIVELMENTE ESTRANGEIRO',
                'ESTRANGEIRO'
            ]
        )

    with colf3:

        busca = st.text_input(
            'Buscar NFE / Cliente'
        )

    df_view = resultado.copy()

    if filtro_status != 'Todos':
        df_view = df_view[
            df_view['Status'] == filtro_status
        ]
    if filtro_tipo != 'Todos':

        df_view = df_view[
            df_view['Tipo_Pessoa'] == filtro_tipo
    ]    

    if filtro_tipo != 'Todos':
        df_view = df_view[
            df_view['Tipo_Pessoa'] == filtro_tipo
        ]

    if busca:

        mask = (
            df_view['NFE'].astype(str).str.contains(
                busca,
                case=False,
                na=False
            )
            |
            df_view['Nome_OMIE'].astype(str).str.contains(
                busca,
                case=False,
                na=False
            )
            |
            df_view['Nome_Pref'].astype(str).str.contains(
                busca,
                case=False,
                na=False
            )
        )

        df_view = df_view[mask]

    df_html = df_view.copy()

    df_html['Status'] = df_html['Status'].apply(status_badge)

    st.markdown(
        df_html.to_html(escape=False, index=False),
        unsafe_allow_html=True
    )

    st.download_button(
        label='⬇️ Baixar Excel Completo',
        data=to_excel(resultado),
        file_name='conciliacao_prefeitura.xlsx',
        mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

