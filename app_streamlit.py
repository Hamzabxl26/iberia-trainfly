import os
import requests
import pandas as pd
import streamlit as st
from datetime import date, timedelta

# ---------- CONFIG ----------

try:
    SERPAPI_KEY = st.secrets.get("SERPAPI_KEY")
except Exception:
    SERPAPI_KEY = None

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


# ---------- HELPERS ----------

def daterange(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current.isoformat()
        current += timedelta(days=1)


def google_flights_link(origin, destination, outbound_date, return_date=None):
    if return_date:
        query = f"Flights from {origin} to {destination} on {outbound_date} returning {return_date}"
    else:
        query = f"Flights from {origin} to {destination} on {outbound_date}"

    return "https://www.google.com/travel/flights?q=" + query.replace(" ", "%20")


def serpapi_google_flights(origin, destination, outbound_date, return_date=None):
    if not SERPAPI_KEY:
        raise RuntimeError("Falta la SERPAPI_KEY.")

    params = {
        "engine": "google_flights",
        "api_key": SERPAPI_KEY,
        "departure_id": origin,
        "arrival_id": destination,
        "outbound_date": outbound_date,
        "currency": "EUR",
        "hl": "es",
        "gl": "be",
        "adults": "1",
        "show_hidden": "true",
    }

    if return_date:
        params["type"] = "1"
        params["return_date"] = return_date
    else:
        params["type"] = "2"

    response = requests.get(
        "https://serpapi.com/search",
        params=params,
        timeout=90,
    )
    response.raise_for_status()
    return response.json()


def flatten_results(data, origin, destination, outbound_date, return_date, label):
    rows = []

    blocks = []
    blocks.extend(data.get("best_flights", []) or [])
    blocks.extend(data.get("other_flights", []) or [])

    for block in blocks:
        price = block.get("price")
        total_duration = block.get("total_duration")
        flights = block.get("flights", []) or []

        if not flights:
            continue

        first = flights[0]
        last = flights[-1]

        airlines = []
        flight_numbers = []
        itinerary = []

        for flight in flights:
            dep = flight.get("departure_airport", {}) or {}
            arr = flight.get("arrival_airport", {}) or {}

            airline = flight.get("airline", "")
            flight_number = flight.get("flight_number", "")

            if airline:
                airlines.append(airline)
            if flight_number:
                flight_numbers.append(flight_number)

            itinerary.append(
                f"{dep.get('id', '')} {dep.get('time', '')} → "
                f"{arr.get('id', '')} {arr.get('time', '')}"
            )

        rows.append({
            "tipo_busqueda": label,
            "origen": origin,
            "destino": destination,
            "fecha_ida": outbound_date,
            "fecha_vuelta": return_date or "",
            "precio": price,
            "moneda": "EUR",
            "salida": (first.get("departure_airport", {}) or {}).get("time", ""),
            "llegada": (last.get("arrival_airport", {}) or {}).get("time", ""),
            "duracion_min": total_duration,
            "companias": ", ".join(sorted(set(airlines))),
            "vuelos": ", ".join(flight_numbers),
            "itinerario": " | ".join(itinerary),
            "enlace_google_flights": google_flights_link(
                origin, destination, outbound_date, return_date
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


def best_row(rows):
    valid = [
        row for row in rows
        if isinstance(row.get("precio"), (int, float))
    ]
    if not valid:
        return None
    return min(valid, key=lambda r: r["precio"])


def search_best_roundtrip_range(origin, destination, outbound_start, outbound_end, return_start, return_end, label):
    all_rows = []
    best = None
    errors = []

    outbound_dates = list(daterange(outbound_start, outbound_end))
    return_dates = list(daterange(return_start, return_end))

    for outbound_date in outbound_dates:
        for return_date in return_dates:
            try:
                data = serpapi_google_flights(
                    origin=origin,
                    destination=destination,
                    outbound_date=outbound_date,
                    return_date=return_date,
                )

                rows = flatten_results(
                    data=data,
                    origin=origin,
                    destination=destination,
                    outbound_date=outbound_date,
                    return_date=return_date,
                    label=label,
                )

                all_rows.extend(rows)

                candidate = best_row(rows)
                if candidate and (best is None or candidate["precio"] < best["precio"]):
                    best = candidate

            except Exception as exc:
                errors.append(f"{outbound_date}/{return_date}: {exc}")

    return best, all_rows, errors


# ---------- UI ----------

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
    "Compara vuelos BRU ↔ MAD con billetes Train&Fly BRU ↔ estaciones españolas vía Madrid."
)

st.subheader("Fechas")

col1, col2 = st.columns(2)

with col1:
    outbound_start = st.date_input("Ida desde", value=date(2026, 7, 16))
    outbound_end = st.date_input("Ida hasta", value=date(2026, 7, 20))

with col2:
    return_start = st.date_input("Vuelta desde", value=date(2026, 7, 22))
    return_end = st.date_input("Vuelta hasta", value=date(2026, 7, 25))

if outbound_end < outbound_start:
    st.error("La fecha final de ida debe ser posterior o igual a la fecha inicial.")
    st.stop()

if return_end < return_start:
    st.error("La fecha final de vuelta debe ser posterior o igual a la fecha inicial.")
    st.stop()

st.subheader("Estaciones")

station_labels = [
    f"{station['code']} — {station['city']}"
    for station in STATIONS
]

selected_labels = st.multiselect(
    "Estaciones a analizar",
    station_labels,
    default=station_labels[:3],
)

selected_stations = []
for label in selected_labels:
    code = label.split(" — ", 1)[0]
    selected_stations.append(
        next(station for station in STATIONS if station["code"] == code)
    )

st.warning(
    "Google Flights puede no reconocer todos los códigos ferroviarios. "
    "Si una estación no devuelve resultados, puede venir de Google, no necesariamente de Iberia."
)

total_combinations = (
    (outbound_end - outbound_start).days + 1
) * (
    (return_end - return_start).days + 1
)

st.info(
    f"Cada ruta probará {total_combinations} combinaciones de fechas. "
    "Más estaciones = más consultas SerpApi. La humanidad inventó las cuotas API para que nadie fuera feliz."
)

if st.button("Buscar mejores precios", type="primary"):
    summary_rows = []
    all_rows = []
    errors_rows = []

    progress = st.progress(0)
    total_jobs = 1 + len(selected_stations)
    current_job = 0

    # Référence BRU ↔ MAD
    current_job += 1
    progress.progress(current_job / total_jobs)

    with st.status("Buscando referencia BRU ↔ MAD..."):
        ref_best, ref_all, ref_errors = search_best_roundtrip_range(
            origin="BRU",
            destination="MAD",
            outbound_start=outbound_start,
            outbound_end=outbound_end,
            return_start=return_start,
            return_end=return_end,
            label="REFERENCIA BRU-MAD",
        )

        all_rows.extend(ref_all)

        if ref_errors:
            errors_rows.append({
                "ruta": "BRU-MAD",
                "errores": " | ".join(ref_errors[:5]),
            })

    ref_price = ref_best["precio"] if ref_best else None

    for station in selected_stations:
        current_job += 1
        progress.progress(current_job / total_jobs)

        code = station["code"]
        city = station["city"]

        with st.status(f"Buscando BRU ↔ {city} ({code})..."):
            combo_best, combo_all, combo_errors = search_best_roundtrip_range(
                origin="BRU",
                destination=code,
                outbound_start=outbound_start,
                outbound_end=outbound_end,
                return_start=return_start,
                return_end=return_end,
                label=f"TRAINFLY BRU-{code}",
            )

            all_rows.extend(combo_all)

            if combo_errors:
                errors_rows.append({
                    "ruta": f"BRU-{code}",
                    "errores": " | ".join(combo_errors[:5]),
                })

        combo_price = combo_best["precio"] if combo_best else None

        difference = None
        status = "Sin datos"

        if ref_price is not None and combo_price is not None:
            difference = ref_price - combo_price
            status = (
                "Train&Fly más barato"
                if difference > 0
                else "No es más barato"
            )

        summary_rows.append({
            "estacion": city,
            "codigo": code,
            "precio_referencia_BRU_MAD": ref_price,
            "fecha_ida_ref": ref_best.get("fecha_ida") if ref_best else "",
            "fecha_vuelta_ref": ref_best.get("fecha_vuelta") if ref_best else "",
            "precio_trainfly_minimo": combo_price,
            "fecha_ida_trainfly": combo_best.get("fecha_ida") if combo_best else "",
            "fecha_vuelta_trainfly": combo_best.get("fecha_vuelta") if combo_best else "",
            "diferencia": difference,
            "estado": status,
            "enlace_google_flights": combo_best.get("enlace_google_flights") if combo_best else google_flights_link("BRU", code, outbound_start.isoformat(), return_start.isoformat()),
        })

    df_summary = pd.DataFrame(summary_rows)
    df_all = pd.DataFrame(all_rows)
    df_errors = pd.DataFrame(errors_rows)

    st.subheader("Resumen comparativo")
    st.dataframe(df_summary, use_container_width=True)

    st.download_button(
        "Descargar resumen CSV",
        df_summary.to_csv(index=False).encode("utf-8-sig"),
        file_name="resumen_trainfly.csv",
        mime="text/csv",
    )

    st.subheader("Todos los vuelos y horarios encontrados")
    st.dataframe(df_all, use_container_width=True)

    st.download_button(
        "Descargar todos los vuelos CSV",
        df_all.to_csv(index=False).encode("utf-8-sig"),
        file_name="todos_los_vuelos_trainfly.csv",
        mime="text/csv",
    )

    if not df_errors.empty:
        st.subheader("Errores / rutas sin respuesta")
        st.dataframe(df_errors, use_container_width=True)
