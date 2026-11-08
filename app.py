
import streamlit as st
import pandas as pd
from pathlib import Path
import io

# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Recherche Concours",
    page_icon="🔎",
    layout="wide"
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

st.title("🔎 Recherche des candidats aux concours")
st.caption("Base de données des concours de 2015 à 2026")


# ============================================================
# CHARGEMENT DES FICHIERS
# ============================================================

@st.cache_data
def get_available_years():
    if not DATA_DIR.exists():
        return []

    years = []

    for file in DATA_DIR.glob("*.parquet"):
        try:
            years.append(int(file.stem))
        except ValueError:
            pass

    return sorted(years)


@st.cache_data
def load_data(year):
    file_path = DATA_DIR / f"{year}.parquet"

    if not file_path.exists():
        return pd.DataFrame()

    return pd.read_parquet(file_path)


years = get_available_years()

if not years:
    st.error(
        "Aucun fichier Parquet trouvé dans le dossier : "
        f"{DATA_DIR}"
    )
    st.stop()


# ============================================================
# SÉLECTION DE L'ANNÉE
# ============================================================

st.sidebar.header("Configuration")

year = st.sidebar.selectbox(
    "Année du concours",
    years,
    index=len(years) - 1
)

df = load_data(year)

if df.empty:
    st.warning("Aucune donnée disponible pour cette année.")
    st.stop()


# ============================================================
# INFORMATIONS GÉNÉRALES
# ============================================================

col1, col2, col3 = st.columns(3)

col1.metric("Année", year)
col2.metric("Nombre de candidats", f"{len(df):,}")
col3.metric("Nombre de colonnes", len(df.columns))

st.divider()


# ============================================================
# AFFICHAGE DES COLONNES
# ============================================================

with st.expander("📋 Voir les colonnes et leurs informations"):

    columns_info = pd.DataFrame({
        "N°": range(1, len(df.columns) + 1),
        "Nom de la colonne": [repr(c) for c in df.columns],
        "Type": [str(df[c].dtype) for c in df.columns],
        "Valeurs non nulles": [df[c].notna().sum() for c in df.columns],
        "Valeurs distinctes": [df[c].nunique(dropna=True) for c in df.columns]
    })

    st.dataframe(
        columns_info,
        width="stretch",
        hide_index=True
    )


# ============================================================
# RECHERCHE GLOBALE
# ============================================================

st.subheader("🔍 Recherche globale")

global_search = st.text_input(
    "Rechercher dans toutes les colonnes",
    placeholder="Nom, numéro de dossier, NNI, région, centre...",
    key="global_search"
)

filtered_df = df.copy()

if global_search.strip():

    search_value = global_search.strip().casefold()

    mask = pd.Series(False, index=filtered_df.index)

    for column in filtered_df.columns:

        column_values = (
            filtered_df[column]
            .astype("string")
            .str.casefold()
        )

        mask |= column_values.str.contains(
            search_value,
            na=False,
            regex=False
        )

    filtered_df = filtered_df[mask]


# ============================================================
# FILTRES AVANCÉS
# ============================================================

st.sidebar.divider()
st.sidebar.header("Filtres avancés")

selected_columns = st.sidebar.multiselect(
    "Choisir les colonnes à filtrer",
    options=list(df.columns),
    help=(
        "Sélectionne les colonnes sur lesquelles tu souhaites "
        "appliquer des filtres."
    )
)


# ============================================================
# APPLICATION DES FILTRES DYNAMIQUES
# ============================================================

for i, column in enumerate(selected_columns):

    original_series = df[column]

    st.sidebar.markdown(f"**{column}**")

    # --------------------------------------------------------
    # COLONNE NUMÉRIQUE
    # --------------------------------------------------------

    if pd.api.types.is_numeric_dtype(original_series):

        numeric_values = pd.to_numeric(
            original_series,
            errors="coerce"
        ).dropna()

        if numeric_values.empty:
            st.sidebar.info("Aucune valeur numérique.")
            continue

        min_value = float(numeric_values.min())
        max_value = float(numeric_values.max())

        if min_value < max_value:

            selected_range = st.sidebar.slider(
                "Intervalle",
                min_value=min_value,
                max_value=max_value,
                value=(min_value, max_value),
                key=f"numeric_{year}_{i}"
            )

            current_values = pd.to_numeric(
                filtered_df[column],
                errors="coerce"
            )

            filtered_df = filtered_df[
                current_values.between(
                    selected_range[0],
                    selected_range[1]
                )
            ]

        else:
            st.sidebar.info(f"Valeur unique : {min_value}")

    # --------------------------------------------------------
    # COLONNE DATE
    # --------------------------------------------------------

    elif pd.api.types.is_datetime64_any_dtype(original_series):

        dates = original_series.dropna()

        if dates.empty:
            st.sidebar.info("Aucune date disponible.")
            continue

        min_date = dates.min().date()
        max_date = dates.max().date()

        date_range = st.sidebar.date_input(
            "Intervalle de dates",
            value=(min_date, max_date),
            key=f"date_{year}_{i}"
        )

        if isinstance(date_range, (tuple, list)) and len(date_range) == 2:

            start_date, end_date = date_range

            current_dates = pd.to_datetime(
                filtered_df[column],
                errors="coerce"
            )

            filtered_df = filtered_df[
                current_dates.dt.date.between(
                    start_date,
                    end_date
                )
            ]

    # --------------------------------------------------------
    # COLONNE TEXTE / CATÉGORIELLE
    # --------------------------------------------------------

    else:

        unique_values = original_series.dropna().unique()

        # Peu de valeurs distinctes : liste de sélection
        if len(unique_values) <= 100:

            options = sorted(
                [str(value) for value in unique_values]
            )

            selected_values = st.sidebar.multiselect(
                "Valeurs",
                options=options,
                key=f"category_{year}_{i}"
            )

            if selected_values:

                filtered_df = filtered_df[
                    filtered_df[column]
                    .astype("string")
                    .isin(selected_values)
                ]

        # Beaucoup de valeurs : recherche par texte
        else:

            text_filter = st.sidebar.text_input(
                "Contient",
                placeholder="Saisir une valeur...",
                key=f"text_{year}_{i}"
            )

            if text_filter.strip():

                filtered_df = filtered_df[
                    filtered_df[column]
                    .astype("string")
                    .str.contains(
                        text_filter.strip(),
                        case=False,
                        na=False,
                        regex=False
                    )
                ]


# ============================================================
# RÉSULTATS
# ============================================================

st.divider()
st.subheader("📊 Résultats")

col1, col2 = st.columns(2)

col1.metric(
    "Candidats correspondant aux critères",
    f"{len(filtered_df):,}"
)

col2.metric(
    "Colonnes affichées",
    len(filtered_df.columns)
)


# ============================================================
# PAGINATION
# ============================================================

page_size = st.selectbox(
    "Nombre de lignes par page",
    [25, 50, 100, 250, 500],
    index=1
)

total_pages = max(
    1,
    (len(filtered_df) + page_size - 1) // page_size
)

page = st.number_input(
    "Page",
    min_value=1,
    max_value=total_pages,
    value=1,
    step=1
)

start = (page - 1) * page_size
end = start + page_size

page_df = filtered_df.iloc[start:end]

st.dataframe(
    page_df,
    width="stretch",
    hide_index=True
)

st.caption(
    f"Page {page} / {total_pages} — "
    f"Lignes {start + 1 if len(filtered_df) else 0} "
    f"à {min(end, len(filtered_df))}"
)


# ============================================================
# EXPORT EXCEL
# ============================================================

st.divider()
st.subheader("📥 Export des résultats")


def dataframe_to_excel(dataframe, year):
    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:

        dataframe.to_excel(
            writer,
            index=False,
            sheet_name=str(year)
        )

    return output.getvalue()



st.download_button(
    label="Télécharger tous les résultats filtrés en Excel",
    data=lambda: dataframe_to_excel(filtered_df, year),
    file_name=f"concours_{year}_resultats.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
