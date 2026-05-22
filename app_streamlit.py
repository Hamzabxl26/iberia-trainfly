import os
import requests
import pandas as pd
import streamlit as st
from datetime import date

SERPAPI_KEY = os.getenv("SERPAPI_KEY")

# Charge .env sans dépendance externe
if not SERPAPI_KEY and os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("SERPAPI_KEY="):
                SERPAPI_KEY = line.strip().split("=", 1)[1]

STATIONS = [
    {"city": "Málaga María Zambrano", "code": "YJM"},
    {"city": "Sevilla Santa Justa", "code": "XQA"},
    {"city": "Valencia", "code": "YJV"},
    {"city": "Alicante", "code": "YJE"},
    {"city": "Zaragoza", "code": "XZZ"},
    {"city": "Córdoba", "code": "XOJ"},
    {"city": "Valladolid", "code": "XJN"},
    {"city": "Pamplona", "code": "EEP"},
    {"city": "León", "code": "EEU"},
    {"city": "Palencia", "code": "PCI"},
    {"city": "Ourense", "code": "OUQ"},
    {"city": "Granada", "code": "YJG"},
    {"city": "Murcia", "code": "XUT"},
    {"city": "Vigo", "code": "YJR"},
    {"city": "Santiago de Compostela", "code": "YJT"},
    {"city": "A Coruña", "code": "YJC"},
    {"city": "Gijón", "code": "QIJ"},
    {"city": "Oviedo", "code": "OVI"},
    {"city": "Salamanca", "code": "SLM"},
    {"city": "Albacete", "code": "EEM"},
]

def google_flights_link(origin, destination, travel_date):
    return (
        "https://www.google.com/travel/flights"
        f"?q=Flights%20from%20{origin}%20to%20{destination}%20on%20{travel_date}"
    )

def serpapi_google_flights(origin, destination, travel_date):
    if not SERPAPI_KEY:
        raise RuntimeError("SERPAPI_KEY manquante dans .env")

    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_KEY,
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": travel_date,
        "type": "2",
        "currency": "EUR",
        "hl": "fr",
        "gl": "be",
        "adults": "1",
        "show_hidden": "true",
    }

    r = requests.get("https://serpapi.com/search", params=params, timeout=90)
    r.raise_for_status()
    return r.json()

def flatten_results(data, origin, destination, travel_date, label):
    rows = []

    flights_blocks = []
    flights_blocks.extend(data.get("best_flights", []) or [])
    flights_blocks.extend(data.get("other_flights", []) or [])

    for block in flights_blocks:
        price = block.get("price")
        total_duration = block.get("total_duration")
        booking_token = block.get("booking_token")
        departure_token = block.get("departure_token")

        flights = block.get("flights", []) or []
        if not flights:
            continue

        first = flights[0]
        last = flights[-1]

        route_parts = []
        airlines = []
        flight_numbers = []

        for f in flights:
            dep = f.get("departure_airport", {}) or {}
            arr = f.get("arrival_airport", {}) or {}
            dep_code = dep.get("id", "")
            arr_code = arr.get("id", "")
            dep_time = dep.get("time", "")
            arr_time = arr.get("time", "")
            airline = f.get("airline", "")
            flight_number = f.get("flight_number", "")

            if airline:
                airlines.append(airline)
            if flight_number:
                flight_numbers.append(flight_number)

            route_parts.append(f"{dep_code} {dep_time} → {arr_code} {arr_time}")

        booking_url = google_flights_link(origin, destination, travel_date)

        rows.append({
            "type_recherche": label,
            "date": travel_date,
            "origine": origin,
            "destination": destination,
            "prix": price,
            "devise": "EUR",
            "depart": (first.get("departure_airport", {}) or {}).get("time", ""),
            "arrivee": (last.get("arrival_airport", {}) or {}).get("time", ""),
            "duree_min": total_duration,
            "compagnies": ", ".join(sorted(set(airlines))),
            "vols": ", ".join(flight_numbers),
            "itineraire": " | ".join(route_parts),
            "booking_token": booking_token or "",
            "departure_token": departure_token or "",
            "lien_google_flights": booking_url,
        })

    return rows

def lowest_price(rows):
    prices = [r["prix"] for r in rows if isinstance(r.get("prix"), (int, float))]
    return min(prices) if prices else None

st.set_page_config(page_title="Iberia Train&Fly Google Flights", layout="wide")

st.title("Iberia Train&Fly Screener — Google Flights / SerpApi")

if not SERPAPI_KEY:
    st.error("SERPAPI_KEY manquante. Mets-la dans le fichier .env")
    st.stop()

st.caption("Source prix : SerpApi Google Flights. Pas d'ouverture automatique Iberia.")

col1, col2, col3 = st.columns(3)

with col1:
    travel_date = st.date_input("Date", value=date.today()).isoformat()

with col2:
    direction = st.selectbox(
        "Sens",
        ["BRU → Espagne via MAD", "Espagne → BRU via MAD", "Les deux"],
        index=2,
    )

with col3:
    max_stations = st.number_input("Nombre max de gares à scanner", min_value=1, max_value=len(STATIONS), value=3)

station_labels = [f"{s['code']} — {s['city']}" for s in STATIONS]
selected_labels = st.multiselect(
    "Gares à scanner",
    station_labels,
    default=station_labels[:int(max_stations)],
)

selected = []
for label in selected_labels:
    code = label.split(" — ", 1)[0]
    selected.append(next(s for s in STATIONS if s["code"] == code))

st.warning(
    "Important : Google Flights peut ne pas reconnaître tous les codes de gares ferroviaires. "
    "Si une gare renvoie zéro résultat, ce n'est pas forcément ton script : c'est Google."
)

if st.button("Scanner les prix Google Flights", type="primary"):
    all_rows = []
    summary_rows = []

    progress = st.progress(0)
    total_jobs = len(selected)
    if direction == "Les deux":
        total_jobs *= 2

    job = 0

    # Prix de référence
    ref_out_rows = []
    ref_in_rows = []

    if direction in ["BRU → Espagne via MAD", "Les deux"]:
        with st.status("Recherche référence BRU → MAD..."):
            data_ref_out = serpapi_google_flights("BRU", "MAD", travel_date)
            ref_out_rows = flatten_results(data_ref_out, "BRU", "MAD", travel_date, "REF BRU-MAD")
            all_rows.extend(ref_out_rows)

    if direction in ["Espagne → BRU via MAD", "Les deux"]:
        with st.status("Recherche référence MAD → BRU..."):
            data_ref_in = serpapi_google_flights("MAD", "BRU", travel_date)
            ref_in_rows = flatten_results(data_ref_in, "MAD", "BRU", travel_date, "REF MAD-BRU")
            all_rows.extend(ref_in_rows)

    ref_out_price = lowest_price(ref_out_rows)
    ref_in_price = lowest_price(ref_in_rows)

    for station in selected:
        code = station["code"]
        city = station["city"]

        if direction in ["BRU → Espagne via MAD", "Les deux"]:
            job += 1
            progress.progress(job / total_jobs)
            with st.status(f"Recherche BRU → {city} ({code})..."):
                try:
                    data = serpapi_google_flights("BRU", code, travel_date)
                    rows = flatten_results(data, "BRU", code, travel_date, f"BRU-{code}")
                    all_rows.extend(rows)
                    combo_price = lowest_price(rows)
                    saving = None
                    if combo_price is not None and ref_out_price is not None:
                        saving = ref_out_price - combo_price
                    summary_rows.append({
                        "sens": "BRU → Espagne",
                        "gare": city,
                        "code": code,
                        "prix_ref_BRU_MAD": ref_out_price,
                        "prix_trainfly_min": combo_price,
                        "difference": saving,
                        "statut": "Train&Fly moins cher" if saving is not None and saving > 0 else "Pas moins cher / inconnu",
                        "lien": google_flights_link("BRU", code, travel_date),
                    })
                except Exception as e:
                    summary_rows.append({
                        "sens": "BRU → Espagne",
                        "gare": city,
                        "code": code,
                        "prix_ref_BRU_MAD": ref_out_price,
                        "prix_trainfly_min": None,
                        "difference": None,
                        "statut": f"Erreur: {e}",
                        "lien": google_flights_link("BRU", code, travel_date),
                    })

        if direction in ["Espagne → BRU via MAD", "Les deux"]:
            job += 1
            progress.progress(job / total_jobs)
            with st.status(f"Recherche {city} ({code}) → BRU..."):
                try:
                    data = serpapi_google_flights(code, "BRU", travel_date)
                    rows = flatten_results(data, code, "BRU", travel_date, f"{code}-BRU")
                    all_rows.extend(rows)
                    combo_price = lowest_price(rows)
                    saving = None
                    if combo_price is not None and ref_in_price is not None:
                        saving = ref_in_price - combo_price
                    summary_rows.append({
                        "sens": "Espagne → BRU",
                        "gare": city,
                        "code": code,
                        "prix_ref_MAD_BRU": ref_in_price,
                        "prix_trainfly_min": combo_price,
                        "difference": saving,
                        "statut": "Train&Fly moins cher" if saving is not None and saving > 0 else "Pas moins cher / inconnu",
                        "lien": google_flights_link(code, "BRU", travel_date),
                    })
                except Exception as e:
                    summary_rows.append({
                        "sens": "Espagne → BRU",
                        "gare": city,
                        "code": code,
                        "prix_ref_MAD_BRU": ref_in_price,
                        "prix_trainfly_min": None,
                        "difference": None,
                        "statut": f"Erreur: {e}",
                        "lien": google_flights_link(code, "BRU", travel_date),
                    })

    df_summary = pd.DataFrame(summary_rows)
    df_all = pd.DataFrame(all_rows)

    st.subheader("Résumé comparatif")
    st.dataframe(df_summary, use_container_width=True)

    st.download_button(
        "Télécharger résumé CSV",
        df_summary.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"resume_trainfly_{travel_date}.csv",
        mime="text/csv",
    )

    st.subheader("Tous les vols / horaires trouvés")
    st.dataframe(df_all, use_container_width=True)

    st.download_button(
        "Télécharger tous les vols CSV",
        df_all.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"tous_les_vols_trainfly_{travel_date}.csv",
        mime="text/csv",
    )
