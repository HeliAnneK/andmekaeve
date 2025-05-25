import streamlit as st
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import requests
from pathlib import Path
from datetime import timedelta
from functools import reduce

st.set_page_config(layout="wide")

# Hashid ja allalaadimise kataloog
target_hashes = [
    "611a88c64f5ec2571748107970", "6b700e975f12516c1748101604",
    "bd9842e15356c60a1748087367", "d38b289c1c08f17e1748079161",
    "fe8f7cc6a2c4f1861748041494", "f80ff25c276726041747076629",
    "607fa27c9edc7cc71746898056", "ed017456c24319561746872210",
    "4d52b0a19e210c1b1746534452"
]
download_dir = Path("data")
download_dir.mkdir(parents=True, exist_ok=True)

# Andmete allalaadimine
def download_data():
    for h in target_hashes:
        file_path = download_dir / f"{h}.csv"
        if not file_path.exists():
            url = f"https://decision.cs.taltech.ee/electricity/data/{h}.csv"
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    file_path.write_bytes(response.content)
            except Exception:
                pass

download_data()

# 100 päeva leidmine
def find_100_day_window(dates):
    dates = sorted(list(set(dates)))
    for i in range(len(dates) - 99):
        window = dates[i:i+100]
        expected = [window[0] + timedelta(days=j) for j in range(100)]
        if window == expected:
            return window
    return None

@st.cache_data
def load_profiles_for_100_days():
    h = target_hashes[0]
    df = pd.read_csv(download_dir / f"{h}.csv", sep=';', skiprows=4)
    df.columns = ['Periood', 'consumption']
    df['Periood'] = pd.to_datetime(df['Periood'], dayfirst=True, errors='coerce')
    df['consumption'] = df['consumption'].astype(str).str.replace(',', '.').astype(float)
    df.dropna(subset=['Periood'], inplace=True)
    df['date'] = df['Periood'].dt.date
    df['hour'] = df['Periood'].dt.hour
    pivot = df.pivot_table(index='date', columns='hour', values='consumption')
    pivot = pivot.dropna()
    valid_window = find_100_day_window(pivot.index)
    return pivot.loc[valid_window] if valid_window else None

@st.cache_data
def find_common_day():
    all_dates = []
    for h in target_hashes[:10]:
        df = pd.read_csv(download_dir / f"{h}.csv", sep=';', skiprows=4)
        df.columns = ['Periood', 'consumption']
        df['Periood'] = pd.to_datetime(df['Periood'], dayfirst=True, errors='coerce')
        df.dropna(subset=['Periood'], inplace=True)
        df['date'] = df['Periood'].dt.date
        all_dates.append(set(df['date']))
    common_dates = sorted(reduce(lambda a, b: a & b, all_dates))
    return common_dates[0] if common_dates else None

@st.cache_data
def load_day_data(common_day):
    data = {}
    for h in target_hashes[:10]:
        df = pd.read_csv(download_dir / f"{h}.csv", sep=';', skiprows=4)
        df.columns = ['Periood', 'consumption']
        df['Periood'] = pd.to_datetime(df['Periood'], dayfirst=True, errors='coerce')
        df.dropna(subset=['Periood'], inplace=True)
        df['consumption'] = df['consumption'].astype(str).str.replace(',', '.').astype(float)
        df['date'] = df['Periood'].dt.date
        df['hour'] = df['Periood'].dt.hour
        df_day = df[df['date'] == common_day]
        data[h[-4:]] = df_day
    return data

@st.cache_data
def prepare_violin_data():
    common_day = find_common_day()
    if not common_day:
        return None, None
    data = load_day_data(common_day)
    rows = []
    for label, df in data.items():
        for _, row in df.iterrows():
            rows.append({
                "Mõõtepunkt": label,
                "Tund": row['hour'],
                "kWh": row['consumption']
            })
    return pd.DataFrame(rows), common_day

# Streamlit UI
st.title("Elektritarbimise alternatiivsed visualiseeringud")

# Joonis 100 päeva päevaprofiilidest
st.subheader("100 järjestikuse päeva päevaprofiilid")
profiles = load_profiles_for_100_days()
if profiles is not None:
    fig1, ax1 = plt.subplots(figsize=(12, 6))
    for date, row in profiles.iterrows():
        ax1.plot(range(24), row.values, alpha=0.2)
    ax1.set_title("100 päeva tarbimisprofiilid")
    ax1.set_xlabel("Tund")
    ax1.set_ylabel("kWh")
    ax1.grid(True)
    st.pyplot(fig1)
else:
    st.error("Ei õnnestunud 100 päeva profiile laadida.")

# Violin plot ühise päeva kohta
st.subheader("Violin plot – ühise päeva tunnijaotused")
violin_df, c_day = prepare_violin_data()
if violin_df is not None:
    fig2, ax2 = plt.subplots(figsize=(14, 6))
    sns.violinplot(data=violin_df, x="Tund", y="kWh", hue="Mõõtepunkt", split=False, inner="quartile", palette="tab10", ax=ax2)
    ax2.set_title(f"Tarbimise jaotused kuupäeval {c_day}")
    ax2.set_xlabel("Tund")
    ax2.set_ylabel("kWh")
    st.pyplot(fig2)
else:
    st.error("Ei õnnestunud violin plot’i andmeid luua.")
