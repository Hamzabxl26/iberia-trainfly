import os
import requests
import pandas as pd
import streamlit as st
from datetime import date

# Leer clave desde Streamlit Cloud Secrets o desde .env local
SERPAPI_KEY = None

try:
    SERPAPI_KEY = st.secrets.get("SERPAPI_KEY")
except Exception:
    pass

if not SERPAPI_KEY:
    SERPAPI_KEY = os.getenv("SERPAPI_KEY")

if not SERPAPI_KEY and os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("SERPAPI_KEY="):
                SERPAPI_KEY = line.strip().split("=", 1)[1].strip().strip('"')


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
        raise RuntimeError("Falta la SERPAPI_KEY.")

    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_KEY,
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": travel_date,
        "type": "2",
        "currency": "EUR",
        "hl": "es",
        "gl": "be",
        "adults": "1",
        "show_hidden": "true",
    }

    response = requests.get(
        "https://serpapi.com/search",
        params=params,
        timeout=90,
    )
    response.raise_for_status()
    return response.json()


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

        for flight in flights:
            dep = flight.get("departure_airport", {}) or {}
            arr = flight.get("arrival_airport", {}) or {}

            dep_code = dep.get("id", "")
            arr_code = arr.get("id", "")
            dep_time = dep.get("time", "")
            arr_time = arr.get("time", "")

            airline = flight.get("airline", "")
            flight_number = flight.get("flight_number", "")

            if airline:
                airlines.append(airline)
            if flight_number:
                flight_numbers.append(flight_number)

            route_parts.append(
                f"{dep_code} {dep_time} → {arr_code} {arr_time}"
            )

        rows.append({
            "tipo_busqueda": label,
            "fecha": travel_date,
            "origen": origin,
            "destino": destination,
            "precio": price,
            "moneda": "EUR",
            "salida": (first.get("departure_airport", {}) or {}).get("time", ""),
            "llegada": (last.get("arrival_airport", {}) or {}).get("time", ""),
            "duracion_min": total_duration,
            "companias": ", ".join(sorted(set(airlines))),
            "vuelos": ", ".join(flight_numbers),
            "itinerario": " | ".join(route_parts),
            "booking_token": booking_token or "",
            "departure_token": departure_token or "",
            "enlace_google_flights": google_flights_link(
                origin, destination, travel_date
            ),
        })

    return rows


def lowest_price(rows):
    prices = [
        row["precio"]
        for row in rows
        if isinstance(row.get("precio"), (int, float))
    ]
    return min(prices) if prices else None


st.set_page_config(
    page_title="Comparador Iberia Train&Fly",
    layout="wide",
)

st.title("Comparador Iberia Train&Fly — Google Flights / SerpApi")

if not SERPAPI_KEY:
    st.error(
        "Falta la SERPAPI_KEY. Añádela en Streamlit Cloud: "
        "Manage app → Settings → Secrets."
    )
    st.stop()

st.caption(
    "Fuente de precios: SerpApi Google Flights. "
    "La aplicación compara vuelos directos con trayectos Train&Fly vía Madrid."
)

col1, col2, col3 = st.columns(3)

with col1:
    travel_date = st.date_input(
        "Fecha",
        value=date.today(),
    ).isoformat()

with col2:
    direction = st.selectbox(
        "Sentido",
        [
            "BRU → España vía MAD",
            "España → BRU vía MAD",
            "Ambos sentidos",
        ],
        index=2,
    )

with col3:
    max_stations = st.number_input(
        "Número máximo de estaciones",
        min_value=1,
        max_value=len(STATIONS),
        value=3,
    )

station_labels = [
    f"{station['code']} — {station['city']}"
    for station in STATIONS
]

selected_labels = st.multiselect(
    "Estaciones a analizar",
    station_labels,
    default=station_labels[: int(max_stations)],
)

selected_stations = []
for label in selected_labels:
    code = label.split(" — ", 1)[0]
    selected_stations.append(
        next(station for station in STATIONS if station["code"] == code)
    )

st.warning(
    "Google Flights puede no reconocer todos los códigos ferroviarios. "
    "Si una estación no devuelve resultados, no significa necesariamente que el trayecto no exista."
)

if st.button("Buscar precios en Google Flights", type="primary"):
    all_rows = []
    summary_rows = []

    total_jobs = len(selected_stations)
    if direction == "Ambos sentidos":
        total_jobs *= 2

    job = 0
    progress = st.progress(0)

    ref_out_rows = []
    ref_in_rows = []

    if direction in ["BRU → España vía MAD", "Ambos sentidos"]:
        with st.status("Buscando referencia BRU → MAD..."):
            data_ref_out = serpapi_google_flights("BRU", "MAD", travel_date)
            ref_out_rows = flatten_results(
                data_ref_out,
                "BRU",
                "MAD",
                travel_date,
                "REFERENCIA BRU-MAD",
            )
            all_rows.extend(ref_out_rows)

    if direction in ["España → BRU vía MAD", "Ambos sentidos"]:
        with st.status("Buscando referencia MAD → BRU..."):
            data_ref_in = serpapi_google_flights("MAD", "BRU", travel_date)
            ref_in_rows = flatten_results(
                data_ref_in,
                "MAD",
                "BRU",
                travel_date,
                "REFERENCIA MAD-BRU",
            )
            all_rows.extend(ref_in_rows)

    ref_out_price = lowest_price(ref_out_rows)
    ref_in_price = lowest_price(ref_in_rows)

    for station in selected_stations:
        code = station["code"]
        city = station["city"]

        if direction in ["BRU → España vía MAD", "Ambos sentidos"]:
            job += 1
            progress.progress(job / total_jobs)

            with st.status(f"Buscando BRU → {city} ({code})..."):
                try:
                    data = serpapi_google_flights("BRU", code, travel_date)
                    rows = flatten_results(
                        data,
                        "BRU",
                        code,
                        travel_date,
                        f"BRU-{code}",
                    )
                    all_rows.extend(rows)

                    combo_price = lowest_price(rows)
                    difference = None

                    if combo_price is not None and ref_out_price is not None:
                        difference = ref_out_price - combo_price

                    summary_rows.append({
                        "sentido": "BRU → España",
                        "estacion": city,
                        "codigo": code,
                        "precio_referencia_BRU_MAD": ref_out_price,
                        "precio_trainfly_minimo": combo_price,
                        "diferencia": difference,
                        "estado": (
                            "Train&Fly más barato"
                            if difference is not None and difference > 0
                            else "No es más barato / desconocido"
                        ),
                        "enlace": google_flights_link("BRU", code, travel_date),
                    })

                except Exception as exc:
                    summary_rows.append({
                        "sentido": "BRU → España",
                        "estacion": city,
                        "codigo": code,
                        "precio_referencia_BRU_MAD": ref_out_price,
                        "precio_trainfly_minimo": None,
                        "diferencia": None,
                        "estado": f"Error: {exc}",
                        "enlace": google_flights_link("BRU", code, travel_date),
                    })

        if direction in ["España → BRU vía MAD", "Ambos sentidos"]:
            job += 1
            progress.progress(job / total_jobs)

            with st.status(f"Buscando {city} ({code}) → BRU..."):
                try:
                    data = serpapi_google_flights(code, "BRU", travel_date)
                    rows = flatten_results(
                        data,
                        code,
                        "BRU",
                        travel_date,
                        f"{code}-BRU",
                    )
                    all_rows.extend(rows)

                    combo_price = lowest_price(rows)
                    difference = None

                    if combo_price is not None and ref_in_price is not None:
                        difference = ref_in_price - combo_price

                    summary_rows.append({
                        "sentido": "España → BRU",
                        "estacion": city,
                        "codigo": code,
                        "precio_referencia_MAD_BRU": ref_in_price,
                        "precio_trainfly_minimo": combo_price,
                        "diferencia": difference,
                        "estado": (
                            "Train&Fly más barato"
                            if difference is not None and difference > 0
                            else "No es más barato / desconocido"
                        ),
                        "enlace": google_flights_link(code, "BRU", travel_date),
                    })

                except Exception as exc:
                    summary_rows.append({
                        "sentido": "España → BRU",
                        "estacion": city,
                        "codigo": code,
                        "precio_referencia_MAD_BRU": ref_in_price,
                        "precio_trainfly_minimo": None,
                        "diferencia": None,
                        "estado": f"Error: {exc}",
                        "enlace": google_flights_link(code, "BRU", travel_date),
                    })

    df_summary = pd.DataFrame(summary_rows)
    df_all = pd.DataFrame(all_rows)

    st.subheader("Resumen comparativo")
    st.dataframe(df_summary, use_container_width=True)

    st.download_button(
        "Descargar resumen CSV",
        df_summary.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"resumen_trainfly_{travel_date}.csv",
        mime="text/csv",
    )

    st.subheader("Todos los vuelos y horarios encontrados")
    st.dataframe(df_all, use_container_width=True)

    st.download_button(
        "Descargar todos los vuelos CSV",
        df_all.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"todos_los_vuelos_trainfly_{travel_date}.csv",
        mime="text/csv",
    )
