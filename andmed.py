import streamlit as st
import altair as alt
import pandas as pd
import requests
from pathlib import Path
from datetime import timedelta
from functools import reduce # Vajalik ühisosa leidmiseks

# Streamliti seadistus laiemaks paigutuseks
st.set_page_config(layout="wide")

# Siht-hashid (andmestike identifikaatorid)
TARGET_HASHES = [
    "611a88c64f5ec2571748107970", "6b700e975f12516c1748101604",
    "bd9842e15356c60a1748087367", "d38b289c1c08f17e1748079161",
    "fe8f7cc6a2c4f1861748041494", "f80ff25c276726041747076629",
    "607fa27c9edc7cc71746898056", "ed017456c24319561746872210",
    "4d52b0a19e210c1b1746534452"
]

# Kataloog andmete allalaadimiseks
DOWNLOAD_DIR = Path("data_elekter") # Nimetasin ümber, et vältida konflikti võimalike data kaustadega
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# --- ANDMETE ALLALAADIMINE ---
def download_data_if_needed(hashes, directory):
    st.sidebar.subheader("Andmete allalaadimine")
    progress_bar = st.sidebar.progress(0)
    download_messages = []

    for i, h in enumerate(hashes):
        file_path = directory / f"{h}.csv"
        if not file_path.exists():
            url = f"https://decision.cs.taltech.ee/electricity/data/{h}.csv"
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status() # Kontrollib HTTP vigasid
                file_path.write_bytes(response.content)
                download_messages.append(f"✓ Laaditud: {file_path.name}")
            except requests.exceptions.RequestException as e:
                download_messages.append(f"✗ Viga laadimisel {file_path.name}: {e}")
        else:
            download_messages.append(f"✓ Olemas: {file_path.name}")
        progress_bar.progress((i + 1) / len(hashes))
    
    if any("Laaditud:" in msg for msg in download_messages) or any("Viga" in msg for msg in download_messages):
        with st.sidebar.expander("Allalaadimise logi", expanded=False):
            for msg in download_messages:
                st.caption(msg)
    progress_bar.empty() # Eemaldab progressiriba pärast lõpetamist

download_data_if_needed(TARGET_HASHES, DOWNLOAD_DIR)

# --- ANDMETE LAADIMINE JA EELTÖÖTLUS ---
@st.cache_data # Cache'ib tulemuse, et vältida korduvat laadimist
def load_single_dataset(file_path):
    try:
        df = pd.read_csv(file_path, sep=';', skiprows=4)
        df.columns = ['timestamp_str', 'consumption_str']
        df['timestamp'] = pd.to_datetime(df['timestamp_str'], dayfirst=True, errors='coerce')
        df['consumption'] = df['consumption_str'].astype(str).str.replace(',', '.').astype(float)
        df.dropna(subset=['timestamp', 'consumption'], inplace=True)
        df['date'] = df['timestamp'].dt.date
        df['hour'] = df['timestamp'].dt.hour
        df['day_name'] = df['timestamp'].dt.strftime('%A (%Y-%m-%d)') # Lisame ka aasta ja kuupäeva nimele
        return df[['timestamp', 'date', 'hour', 'day_name', 'consumption']]
    except Exception as e:
        st.error(f"Viga faili {file_path.name} töötlemisel: {e}")
        return pd.DataFrame() # Tagasta tühi DataFrame vea korral

@st.cache_data
def load_all_datasets(hashes, directory):
    all_data = {}
    for h in hashes:
        file_path = directory / f"{h}.csv"
        if file_path.exists():
            df = load_single_dataset(file_path)
            if not df.empty:
                all_data[h] = df
    return all_data

# Lae kõik andmestikud
all_datasets = load_all_datasets(TARGET_HASHES, DOWNLOAD_DIR)

if not all_datasets:
    st.error("Andmestikke ei õnnestunud laadida. Kontrolli faile või proovi uuesti.")
    st.stop() # Peata rakendus, kui andmeid pole

# --- ABIFUNKTSIOONID ---
def find_100_day_consecutive_window(dates_in_df):
    """Leiab esimese 100 järjestikuse päeva akna DataFrame'i kuupäevadest."""
    unique_sorted_dates = sorted(list(set(dates_in_df)))
    if len(unique_sorted_dates) < 100:
        return None

    for i in range(len(unique_sorted_dates) - 99):
        window_start_date = unique_sorted_dates[i]
        # Kontrolli, kas järgnevad 99 päeva on olemas ja järjestikused
        is_consecutive = True
        for j in range(1, 100):
            expected_next_date = window_start_date + timedelta(days=j)
            if (i + j >= len(unique_sorted_dates)) or (unique_sorted_dates[i+j] != expected_next_date):
                is_consecutive = False
                break
        if is_consecutive:
            return [window_start_date + timedelta(days=k) for k in range(100)]
    return None

# --- STREAMLIT UI ---
st.title("🔌 Elektritarbimise mustrite visualiseerimine")
st.markdown("See rakendus visualiseerib elektritarbimise andmeid kahel viisil.")

# === ÜLESANNE 1: 100 PÄEVA HEATMAP ===
st.header("Ülesanne 1: Ühe andmestiku 100 päeva tarbimise heatmap")

selected_hash_for_heatmap = st.selectbox(
    "Vali andmestik heatmapi kuvamiseks:",
    options=list(all_datasets.keys()),
    format_func=lambda h: f"Andmestik {h[-6:]}" # Näita kasutajale lühemat ID-d
)

if selected_hash_for_heatmap and selected_hash_for_heatmap in all_datasets:
    df_single = all_datasets[selected_hash_for_heatmap]

    # Kontrolli, kas igas tunnis on andmeid (pivot table jaoks)
    # Pivot table nõuab, et iga kuupäeva ja tunni kombinatsioon oleks unikaalne
    # Kui on duplikaate (nt sama tund mitu korda), võtame keskmise
    df_single_pivoted = df_single.groupby(['date', 'hour'])['consumption'].mean().reset_index()

    # Pivot table loomine heatmapi jaoks
    pivot_df = df_single_pivoted.pivot_table(
        index='date',
        columns='hour',
        values='consumption'
    )
    
    # Eemalda päevad, kus pole kõiki 24 tunni andmeid
    pivot_df_cleaned = pivot_df.dropna() 

    if not pivot_df_cleaned.empty:
        # Leia 100 järjestikust päeva
        window_100_days = find_100_day_consecutive_window(pivot_df_cleaned.index)

        if window_100_days:
            df_100_days_for_heatmap = pivot_df_cleaned.loc[window_100_days].reset_index().melt(
                id_vars='date', var_name='hour', value_name='consumption'
            )
            # Muudame kuupäeva stringiks, et Altair seda õigesti järjestaks Y-teljel
            df_100_days_for_heatmap['date_str'] = df_100_days_for_heatmap['date'].astype(str)

            heatmap_chart = alt.Chart(df_100_days_for_heatmap).mark_rect().encode(
                alt.X('hour:O', title='Kellaaeg (0-23)'), # :O - Ordinal
                alt.Y('date_str:O', title='Kuupäev', sort=alt.SortField(field="date", order="ascending")), # Sorteeri kuupäeva järgi
                alt.Color('consumption:Q', title='Tarbimine (kWh)', scale=alt.Scale(scheme='viridis')), # :Q - Quantitative
                tooltip=[
                    alt.Tooltip('date_str', title='Kuupäev'),
                    alt.Tooltip('hour:O', title='Tund'),
                    alt.Tooltip('consumption:Q', title='Tarbimine', format=".2f")
                ]
            ).properties(
                title=f"Elektritarbimine 100 päeva jooksul (Andmestik {selected_hash_for_heatmap[-6:]})",
                width=700, # Võid laiust ja kõrgust kohandada
                height=400
            )
            st.altair_chart(heatmap_chart, use_container_width=True)
        else:
            st.warning(f"Andmestikus {selected_hash_for_heatmap[-6:]} ei leitud 100 järjestikust päeva, kus oleksid olemas kõik 24 tunni andmed.")
    else:
        st.warning(f"Andmestikus {selected_hash_for_heatmap[-6:]} ei ole piisavalt andmeid (pärast puuduvate väärtuste eemaldamist) heatmapi kuvamiseks.")
else:
    st.info("Palun vali andmestik.")


# === ÜLESANNE 2: PALJUDE ANDMESTIKE ÜHE PÄEVA VÕRDLUS ===
st.header("Ülesanne 2: Erinevate andmestike tarbimise võrdlus ühel päeval")

# Leia ühised kuupäevad kõikide (või valitud) andmestike vahel
# Kasutame ainult neid andmestikke, mis on edukalt laetud
available_datasets_for_common_day = {
    h: df for h, df in all_datasets.items() if not df.empty
}

if len(available_datasets_for_common_day) < 2:
    st.warning("Võrdluseks on vaja vähemalt kahte laetud andmestikku.")
else:
    list_of_date_sets = [set(df['date']) for df in available_datasets_for_common_day.values()]
    
    if not list_of_date_sets:
        common_dates = []
    else:
        common_dates = sorted(list(reduce(lambda a, b: a & b, list_of_date_sets)), reverse=True) # Sorteeri uuemad enne

    if not common_dates:
        st.warning("Valitud andmestikel ei leitud ühtegi ühist kuupäeva.")
    else:
        col1, col2 = st.columns([1,2]) # Paigutuse jaoks

        with col1:
            selected_common_day = st.selectbox(
                "Vali ühine kuupäev võrdluseks:",
                options=common_dates,
                format_func=lambda d: d.strftime('%Y-%m-%d (%A)') # Näita kuupäeva ja nädalapäeva
            )
            
            available_hashes_for_multiselect = list(available_datasets_for_common_day.keys())
            selected_hashes_for_comparison = st.multiselect(
                "Vali andmestikud võrdluseks (vähemalt 2):",
                options=available_hashes_for_multiselect,
                default=available_hashes_for_multiselect[:min(len(available_hashes_for_multiselect), 5)], # Vaikimisi esimesed 5
                format_func=lambda h: f"Andmestik {h[-6:]}"
            )

        if selected_common_day and selected_hashes_for_comparison and len(selected_hashes_for_comparison) >= 1:
            comparison_data_list = []
            for h in selected_hashes_for_comparison:
                if h in available_datasets_for_common_day:
                    df_temp = available_datasets_for_common_day[h]
                    df_day = df_temp[df_temp['date'] == selected_common_day].copy() # Kasuta .copy() et vältida SettingWithCopyWarning
                    if not df_day.empty:
                        df_day['dataset_id'] = f"ID {h[-6:]}" # Lisa andmestiku ID
                        comparison_data_list.append(df_day)
            
            if comparison_data_list:
                df_comparison_combined = pd.concat(comparison_data_list)

                line_chart = alt.Chart(df_comparison_combined).mark_line(interpolate='monotone').encode(
                    alt.X('hour:O', title='Kellaaeg (0-23)'),
                    alt.Y('consumption:Q', title='Tarbimine (kWh)', scale=alt.Scale(zero=False)), # zero=False on tihti parem tarbimise puhul
                    alt.Color('dataset_id:N', title='Andmestik'), # :N - Nominal
                    tooltip=[
                        alt.Tooltip('dataset_id', title='Andmestik'),
                        alt.Tooltip('hour:O', title='Tund'),
                        alt.Tooltip('consumption:Q', title='Tarbimine', format=".2f")
                    ]
                ).properties(
                    title=f"Tarbimine kuupäeval {selected_common_day.strftime('%Y-%m-%d (%A)')}",
                    width=600,
                    height=400
                ).interactive() # Muudab graafiku interaktiivseks (zoom, pan)
                
                with col2:
                    st.altair_chart(line_chart, use_container_width=True)
            else:
                with col2:
                    st.info("Valitud andmestikel ja kuupäeval ei leitud andmeid kuvamiseks.")
        else:
            with col2:
                st.info("Palun vali kuupäev ja vähemalt üks andmestik võrdluseks.")

st.sidebar.markdown("---")
st.sidebar.info("Rakendus loodud elektritarbimise andmete analüüsiks ja visualiseerimiseks.")
st.sidebar.markdown("Algandmed: [TalTech Decision Making](https://decision.cs.taltech.ee/electricity/)")
