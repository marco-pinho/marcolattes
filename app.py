import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import os
import re
from io import BytesIO
import plotly.express as px

# --- Configuração da Página ---
st.set_page_config(
    page_title="Análise de Produção Lattes",
    page_icon="📚",
    layout="wide"
)

# --- Funções de Carregamento e Processamento de Dados ---

@st.cache_data
def load_qualis_data(main_qualis_file):
    """Carrega os dados de Qualis a partir do arquivo upado."""
    try:
        qualis_final = pd.read_excel(main_qualis_file)
        
        qualis_final["qualis"] = qualis_final["qualis"].fillna("C")
        qualis_final = qualis_final.drop_duplicates(subset="ISSN").drop(columns=['nome'], errors='ignore')
        
        return qualis_final
    except Exception as e:
        st.error(f"Erro ao ler o arquivo Qualis: {e}. Verifique se o arquivo é Excel válido.")
        return pd.DataFrame()

def process_html_files(folder):
    """Processa todos os arquivos HTML em uma pasta para extrair dados de artigos."""
    base_path = os.path.join(os.getcwd(), folder)
    if not os.path.isdir(base_path):
        return pd.DataFrame()

    html_files = [os.path.join(base_path, f) for f in os.listdir(base_path) if f.endswith(".html")]

    all_articles = []

    for file_path in html_files:
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                html_content = f.read()

            soup = BeautifulSoup(html_content, 'lxml')
            nome_arquivo = os.path.splitext(os.path.basename(file_path))[0]

            articles = soup.select("#artigos-completos .artigo-completo")

            for article in articles:
                cvuri = article.select_one("span.citacoes, span.citado")
                if not cvuri: continue
                cvuri_text = cvuri.get('cvuri', '')

                issn_match = re.search(r"(?<=issn=)([A-Za-z0-9]{4})([A-Za-z0-9]{4})", cvuri_text)
                issn = f"{issn_match.group(1)}-{issn_match.group(2)}" if issn_match else None

                doi_match = re.search(r"(?<=doi=)[^&]+", cvuri_text)
                doi = doi_match.group(0) if doi_match else "N/A"

                titulo_match = re.search(r"(?<=titulo=)[^&]+", cvuri_text)
                titulo = titulo_match.group(0) if titulo_match else "Título não encontrado"

                revista_match = re.search(r"(?<=nomePeriodico=)[^&]+", cvuri_text)
                revista = revista_match.group(0) if revista_match else "Revista não encontrada"

                ano_node = article.select_one("span.informacao-artigo[data-tipo-ordenacao='ano']")
                ano = ano_node.get_text(strip=True) if ano_node else None

                all_articles.append({
                    "Nome": nome_arquivo, "ISSN": issn, "DOI": doi, "Titulo": titulo,
                    "Revista": revista, "Ano": ano, "WOS": 0, "Scopus": 0 # Placeholder
                })
        except Exception as e:
            # Silenciar erros dentro do cache
            pass

    df = pd.DataFrame(all_articles)
    df["Ano"] = pd.to_numeric(df["Ano"], errors='coerce')
    return df

@st.cache_data
def calculate_points(_df, qualis_df):
    """Junta o DataFrame de artigos com o de Qualis e calcula os pontos."""
    df_merged = _df.merge(qualis_df, on="ISSN", how="left")
    df_merged["qualis"] = df_merged["qualis"].fillna("C").replace("-", "C")
    pontos_map = {"A1": 100, "A2": 80, "A3": 60, "A4": 40, "B1": 30, "B2": 20, "B3": 10, "B4": 5, "C": 0}
    df_merged["pontos"] = df_merged["qualis"].map(pontos_map).fillna(0)
    return df_merged

def to_excel(dfs_dict):
    """Escreve um dicionário de DataFrames para um objeto BytesIO em formato Excel."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in dfs_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()

# --- UI Principal ---

# --- Seletor de Categoria ---
categoria = st.sidebar.radio(
    "📂 Selecione a categoria:",
    options=["Professores Permanentes", "Professores Colaboradores"],
    index=0  # Padrão: Permanentes
)

# Mapear seleção para nome da pasta
pasta_map = {
    "Professores Permanentes": "permanentes",
    "Professores Colaboradores": "colaboradores"
}
folder_path = pasta_map[categoria]

st.title(f"📊 Análise de Produção Científica - {categoria}")

# --- Carregamento e Processamento dos Dados ---
# Carrega os arquivos Qualis diretamente da pasta 'data'
main_qualis_path = os.path.join("data", "qualis_final.xlsx")

if not os.path.exists(main_qualis_path):
    st.error(f"Arquivo Qualis não encontrado na pasta 'data'. Certifique-se que 'qualis_final.xlsx' está no lugar certo.")
    st.stop()

qualis_df = load_qualis_data(main_qualis_path)

with st.spinner(f"Processando currículos de {categoria}..."):
    articles_df = process_html_files(folder=folder_path)

if qualis_df.empty or articles_df.empty:
    st.error("Falha no carregamento dos dados. Verifique os arquivos e o diretório HTML.")
    st.stop()
    
banco_final = calculate_points(articles_df, qualis_df)

# --- Barra Lateral: Filtros ---
st.sidebar.header("Filtros de Análise")
anos_disponiveis = sorted(banco_final["Ano"].dropna().unique().astype(int))
if not anos_disponiveis:
    st.sidebar.warning("Não há anos disponíveis para filtro nos dados processados.")
    st.stop()
    
# O seletor de ano é dinâmico e se ajustará automaticamente aos anos presentes nos dados.
# Isso garante que anos futuros (2026, 2027, etc.) sejam incluídos no filtro.
ano_inicio, ano_fim = st.sidebar.select_slider(
    "Selecione o Período de Análise:",
    options=anos_disponiveis,
    value=(min(anos_disponiveis), max(anos_disponiveis))
)

professores_disponiveis = sorted(banco_final["Nome"].unique())
professores_selecionados = st.sidebar.multiselect(
    "Selecione os Professores:",
    options=professores_disponiveis,
    default=professores_disponiveis
)

# Aplicar filtros
df_filtrado = banco_final[
    (banco_final["Ano"] >= ano_inicio) &
    (banco_final["Ano"] <= ano_fim) &
    (banco_final["Nome"].isin(professores_selecionados))
]

# --- Área de Conteúdo Principal com Abas ---
tab1, tab2, tab3 = st.tabs(["📈 Dashboard Geral", "👩‍🏫 Análise Individual", "📄 Dados Completos"])

with tab1:
    st.header(f"Dashboard Geral - {categoria} ({ano_inicio} - {ano_fim})")
    if df_filtrado.empty:
        st.warning("Nenhum dado encontrado para os filtros selecionados.")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Pontos", f"{df_filtrado['pontos'].sum():,.0f}")
        col2.metric("Total de Artigos", f"{len(df_filtrado):,}")
        col3.metric("Professores na Seleção", f"{len(professores_selecionados):,}")
        st.markdown("---")
        col1_graph, col2_graph = st.columns([1, 2])
        with col1_graph:
            st.subheader("Artigos por Qualis (%)")
            qualis_counts = df_filtrado['qualis'].value_counts(normalize=True).mul(100).sort_index()
            # Garantir a ordem correta do Qualis
            qualis_order = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C"]
            qualis_counts = qualis_counts.reindex(qualis_order, fill_value=0)
            fig_bar_qualis = px.bar(qualis_counts, x=qualis_counts.index, y=qualis_counts.values,
                                    title="Distribuição Percentual por Qualis",
                                    labels={'y': 'Porcentagem (%)', 'x': 'Qualis'},
                                    color_discrete_sequence=px.colors.sequential.RdBu)
            fig_bar_qualis.update_layout(showlegend=False)
            st.plotly_chart(fig_bar_qualis, use_container_width=True)
        with col2_graph:
            st.subheader("Pontuação Total por Professor")
            pontos_por_prof = df_filtrado.groupby('Nome')['pontos'].sum().sort_values(ascending=False)
            fig_bar = px.bar(pontos_por_prof, x=pontos_por_prof.index, y=pontos_por_prof.values, title="Ranking de Pontuação", labels={'y': 'Pontos', 'x': 'Professor'})
            st.plotly_chart(fig_bar, use_container_width=True, key="ranking_chart")

with tab2:
    st.header("Análise Detalhada por Professor")
    if not professores_selecionados:
        st.warning("Selecione pelo menos um professor na barra lateral.")
    else:
        for professor in professores_selecionados:
            with st.expander(f"Análise de {professor}", expanded=False):
                prof_data = df_filtrado[df_filtrado["Nome"] == professor]
                if prof_data.empty:
                    st.write("Nenhuma produção encontrada para este professor no período.")
                    continue
                
                st.subheader("Produção Principal")
                tabela_main = prof_data[['Titulo', 'Ano', 'Revista', 'qualis', 'pontos']].copy()
                st.dataframe(tabela_main)
                
                st.subheader("Resumo por Qualis")
                pesos = pd.DataFrame([{"qualis": "A1", "peso": 100}, {"qualis": "A2", "peso": 80}, {"qualis": "A3", "peso": 60}, {"qualis": "A4", "peso": 40}, {"qualis": "B1", "peso": 30}, {"qualis": "B2", "peso": 20}, {"qualis": "B3", "peso": 10}, {"qualis": "B4", "peso": 5}, {"qualis": "C", "peso": 0}])
                por_qualis = prof_data.groupby('qualis').size().reset_index(name='n')
                resumo_qualis = pesos.merge(por_qualis, on='qualis', how='left').fillna(0)
                resumo_qualis['pontos'] = resumo_qualis['n'] * resumo_qualis['peso']
                st.dataframe(resumo_qualis)

                # Gráfico de barras para o Qualis do professor
                st.subheader("Distribuição Percentual por Qualis")
                qualis_counts_prof = prof_data['qualis'].value_counts(normalize=True).mul(100).sort_index()
                qualis_order = ["A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4", "C"]
                qualis_counts_prof = qualis_counts_prof.reindex(qualis_order, fill_value=0)
                fig_bar_prof = px.bar(qualis_counts_prof, x=qualis_counts_prof.index, y=qualis_counts_prof.values,
                                      labels={'y': 'Porcentagem (%)', 'x': 'Qualis'},
                                      color_discrete_sequence=px.colors.sequential.RdBu)
                fig_bar_prof.update_layout(showlegend=False)
                st.plotly_chart(fig_bar_prof, use_container_width=True, key=f"qualis_chart_{professor}")

                st.subheader("Relação Produção A vs. B")
                n_A = resumo_qualis[resumo_qualis['qualis'].str.startswith('A')]['n'].sum()
                pontos_A = resumo_qualis[resumo_qualis['qualis'].str.startswith('A')]['pontos'].sum()
                n_B = resumo_qualis[resumo_qualis['qualis'].str.startswith('B')]['n'].sum()
                pontos_B = resumo_qualis[resumo_qualis['qualis'].str.startswith('B')]['pontos'].sum()
                total_n_AB = n_A + n_B
                
                relacao_df = pd.DataFrame({
                    "Categoria": ["Total (A+B)", "A", "B"],
                    "Número (n)": [total_n_AB, n_A, n_B],
                    "Porcentagem (%)": [100, int((n_A / total_n_AB * 100)) if total_n_AB > 0 else 0, int((n_B / total_n_AB * 100)) if total_n_AB > 0 else 0],
                    "Pontuação Total": [pontos_A + pontos_B, pontos_A, pontos_B]
                }).set_index('Categoria')
                # Formatando para inteiros
                st.dataframe(relacao_df.astype({'Número (n)': int, 'Pontuação Total': int}).style.format({'Porcentagem (%)': '{:.0f}%'}))
                
                excel_data = to_excel({"Producao_Principal": tabela_main, "Resumo_Qualis": resumo_qualis, "Relacao_A_B": relacao_df.reset_index().astype({'Número (n)': int, 'Pontuação Total': int}).style.format({'Porcentagem (%)': '{:.0f}%'})})
                st.download_button(label=f"📥 Baixar Relatório Excel de {professor}", data=excel_data, file_name=f"{professor}_relatorio_{ano_inicio}_{ano_fim}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"download_button_{professor}")

with tab3:
    st.header("Tabela de Dados Completa")
    if df_filtrado.empty:
        st.warning("Nenhuma dado para exibir com base nos filtros atuais.")
    else:
        # Remover colunas 'Unnamed'
        df_display = df_filtrado.loc[:, ~df_filtrado.columns.str.startswith('Unnamed')]
        df_display = df_display.drop(columns=['WOS', 'Scopus'], errors='ignore')
        st.dataframe(df_display)
        csv_data = df_display.to_csv(index=False).encode('utf-8')
        st.download_button(label="📥 Baixar dados como CSV", data=csv_data, file_name=f"producao_filtrada_{ano_inicio}_{ano_fim}.csv", mime="text/csv")
# --- Rodapé ---
st.sidebar.info("Desenvolvido para análise de dados Lattes.")