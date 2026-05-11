# 🔍 Conciliação OMIE × Prefeitura

Aplicação web para conciliação automática de nota fiscal de serviço eletrônica (NFS-e) entre dados do OMIE e extratos da Prefeitura.

## ✨ Funcionalidades

- ✅ **Reconhecimento inteligente de colunas** - Aceita variações de cabeçalho (acentos, espaços, maiúsculas)
- ✅ **Validação automática** - Detecta NFEs duplicadas, valores inválidos e dados faltantes
- ✅ **Classificação de divergências**:
  - Conciliado
  - Divergência de Valor
  - Ausente na Prefeitura
  - Ausente no OMIE
- ✅ **Filtros e buscas** - Filtre por status ou procure por NFE/cliente
- ✅ **Exportação de relatórios** - Baixe resultado completo ou apenas erros em Excel

## 📋 Requisitos

- Python 3.8+
- Arquivos de entrada:
  - **OMIE**: Arquivo Excel (.xlsx ou .xls)
  - **Prefeitura**: Arquivo CSV

### Colunas esperadas

**OMIE (Excel):**
- Número da NFS-e / Numero NFS-e / NFS-e
- Cliente (Nome Fantasia) / Cliente / Nome Fantasia / Razão Social
- Valor Líquido / Valor Liquido / Valor / Valor Total

**Prefeitura (CSV):**
- Nº NFS-e / N° NFS-e / Numero NFS-e / Número NFS-e / NFS-e
- Razão Social do Tomador / Razao Social do Tomador / Tomador / Razão Social
- Valor dos Serviços / Valor dos Servicos / Valor Serviço / Valor Servico

## 🚀 Instalação Local

```bash
# Clone ou baixe o repositório
cd "Concilia Prefeitura"

# Crie um ambiente virtual
python -m venv .venv

# Ative o ambiente (Windows)
.venv\Scripts\activate

# Instale dependências
pip install -r requirements.txt

# Execute a aplicação
streamlit run app.py
```

## 🌐 Deploy no Streamlit Cloud

1. Faça upload para GitHub
2. Acesse [share.streamlit.io](https://share.streamlit.io)
3. Clique em "New app"
4. Selecione o repositório e arquivo `app.py`
5. Clique em "Deploy"

## 📊 Como usar

1. Acesse a aplicação
2. Faça o upload do **Excel do OMIE**
3. Faça o upload do **CSV da Prefeitura**
4. Clique em **🚀 Conciliar Agora**
5. Visualize o resultado com filtros e buscas
6. Exporte o relatório em Excel

## 🔧 Troubleshooting

### "Coluna não encontrada"
- Verifique o nome exato das colunas no arquivo
- A app aceita variações, mas deve ter as colunas obrigatórias

### "Nenhuma NFE válida"
- Certifique-se de que a coluna de NFE contém números válidos
- Remova linhas em branco do arquivo antes de fazer upload

### "Erro ao ler CSV"
- Tente salvar como UTF-8
- Verifique o separador (vírgula, ponto-e-vírgula, tab)

## 📝 Versão

v1.0.0 (Produção)

## 👤 Autor

Vinícius Sena

## 📄 Licença

Uso interno - XP RA PARTICIPAÇÕES S.A (FERTGROUP)
