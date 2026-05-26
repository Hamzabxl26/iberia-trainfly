import os
from datetime import date, timedelta
from urllib.parse import quote_plus

import pandas as pd
import requests
import streamlit as st


# ============================================================
# CONFIG
# ============================================================

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


# ============================================================
# HELPERS
# ============================================================

def daterange(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current.isoformat()
        current += timedelta(days=1)


def google_flights_link(origin, destination, outbound_date, return_date=None):
    if return_date:
        query = (
            f"Flights from {origin} to {destination} "
            f"on {outbound_date} returning {return_date}"
        )
    else:
        query = f"Flights from {origin} to {destination} on {outbound_date}"

    return "https://www.google.com/travel/flights?q=" + quote_plus(query)


def serpapi_google_flights(origin, destination, outbound_date, return_date=None, departure_token=None):
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

    if departure_token:
        params["departure_token"] = departure_token

    response = requests.get(
        "https://serpapi.com/search",
        params=params,
        timeout=90,
    )
    response.raise_for_status()
    return response.json()


def summarize_segments(flights):
    if not flights:
        return {
            "salida": "",
            "llegada": "",
            "duracion_min": "",
            "companias": "",
            "vuelos": "",
            "itinerario": "",
        }

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
        duration = flight.get("duration", "")

        if airline:
            airlines.append(airline)
        if flight_number:
            flight_numbers.append(flight_number)

        itinerary.append(
            f"{dep.get('id', '')} {dep.get('time', '')} → "
            f"{arr.get('id', '')} {arr.get('time', '')}"
            + (f" ({duration} min)" if duration else "")
        )

    duration_sum = 0
    has_duration = False
    for flight in flights:
        duration = flight.get("duration")
        if isinstance(duration, int):
            duration_sum += duration
            has_duration = True

    return {
        "salida": (first.get("departure_airport", {}) or {}).get("time", ""),
        "llegada": (last.get("arrival_airport", {}) or {}).get("time", ""),
        "duracion_min": duration_sum if has_duration else "",
        "companias": ", ".join(sorted(set(airlines))),
        "vuelos": ", ".join(flight_numbers),
        "itinerario": " | ".join(itinerary),
    }


def flatten_outbound_results(data, origin, destination, outbound_date, return_date, label, trip_type):
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

        ida = summarize_segments(flights)

        rows.append({
            "tipo_busqueda": label,
            "tipo_viaje": trip_type,
            "origen": origin,
            "destino": destination,
            "fecha_ida": outbound_date,
            "fecha_vuelta": return_date or "",
            "precio": price,
            "moneda": "EUR",
            "duracion_total_min": total_duration,

            "ida_salida": ida["salida"],
            "ida_llegada": ida["llegada"],
            "ida_duracion_min": ida["duracion_min"],
            "ida_companias": ida["companias"],
            "ida_vuelos": ida["vuelos"],
            "ida_itinerario": ida["itinerario"],

            "vuelta_salida": "",
            "vuelta_llegada": "",
            "vuelta_duracion_min": "",
            "vuelta_companias": "",
            "vuelta_vuelos": "",
            "vuelta_itinerario": "",

            "booking_token": block.get("booking_token", "") or "",
            "departure_token": block.get("departure_token", "") or "",
            "return_booking_token": "",
            "enlace_google_flights": google_flights_link(
                origin, destination, outbound_date, return_date
            ),
        })

    return rows


def flatten_return_results(data):
    rows = []

    blocks = []
    blocks.extend(data.get("best_flights", []) or [])
    blocks.extend(data.get("other_flights", []) or [])

    for block in blocks:
        flights = block.get("flights", []) or []
        if not flights:
            continue

        vuelta = summarize_segments(flights)

        rows.append({
            "precio": block.get("price"),
            "duracion_total_min": block.get("total_duration"),
            "vuelta_salida": vuelta["salida"],
            "vuelta_llegada": vuelta["llegada"],
            "vuelta_duracion_min": vuelta["duracion_min"],
            "vuelta_companias": vuelta["companias"],
            "vuelta_vuelos": vuelta["vuelos"],
            "vuelta_itinerario": vuelta["itinerario"],
            "booking_token": block.get("booking_token", "") or "",
        })

    return rows


def best_row(rows):
    valid = [
        row for row in rows
        if isinstance(row.get("precio"), (int, float))
    ]

    if not valid:
        return None

    return min(valid, key=lambda row: row["precio"])


def enrich_rows_with_return_details(rows):
    enriched = []

    for row in rows:
        if row.get("tipo_viaje") != "Ida y vuelta":
            enriched.append(row)
            continue

        departure_token = row.get("departure_token")
        return_date = row.get("fecha_vuelta")

        if not departure_token or not return_date:
            enriched.append(row)
            continue

        try:
            data = serpapi_google_flights(
                origin=row["origen"],
                destination=row["destino"],
                outbound_date=row["fecha_ida"],
                return_date=return_date,
                departure_token=departure_token,
            )

            return_rows = flatten_return_results(data)
            best_return = best_row(return_rows)

            if best_return:
                row["vuelta_salida"] = best_return.get("vuelta_salida", "")
                row["vuelta_llegada"] = best_return.get("vuelta_llegada", "")
                row["vuelta_duracion_min"] = best_return.get("vuelta_duracion_min", "")
                row["vuelta_companias"] = best_return.get("vuelta_companias", "")
                row["vuelta_vuelos"] = best_return.get("vuelta_vuelos", "")
                row["vuelta_itinerario"] = best_return.get("vuelta_itinerario", "")
                row["return_booking_token"] = best_return.get("booking_token", "")

                if isinstance(best_return.get("precio"), (int, float)):
                    row["precio"] = best_return["precio"]

        except Exception as exc:
            row["vuelta_itinerario"] = f"Error vuelta: {exc}"

        enriched.append(row)

    return enriched


def search_best_range(
    origin,
    destination,
    outbound_start,
    outbound_end,
    return_start,
    return_end,
    label,
    trip_type,
):
    all_rows = []
    best = None
    errors = []

    outbound_dates = list(daterange(outbound_start, outbound_end))

    if trip_type == "Solo ida":
        return_dates = [None]
    else:
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

                rows = flatten_outbound_results(
                    data=data,
                    origin=origin,
                    destination=destination,
                    outbound_date=outbound_date,
                    return_date=return_date,
                    label=label,
                    trip_type=trip_type,
                )

                rows = enrich_rows_with_return_details(rows)

                all_rows.extend(rows)

                candidate = best_row(rows)
                if candidate and (
                    best is None or candidate["precio"] < best["precio"]
                ):
                    best = candidate

            except Exception as exc:
                errors.append(f"{outbound_date}/{return_date or ''}: {exc}")

    return best, all_rows, errors


def make_routes(direction_label, station_code):
    if direction_label == "BRU → España":
        return {
            "ref_origin": "BRU",
            "ref_destination": "MAD",
            "combo_origin": "BRU",
            "combo_destination": station_code,
            "direction_short": "BRU → España",
        }

    return {
        "ref_origin": "MAD",
        "ref_destination": "BRU",
        "combo_origin": station_code,
        "combo_destination": "BRU",
        "direction_short": "España → BRU",
    }


# ============================================================
# UI
# ============================================================

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
    "Compara vuelos directos con billetes Train&Fly vía Madrid, "
    "con búsqueda por rangos de fechas."
)

trip_type = st.selectbox(
    "Tipo de viaje",
    ["Solo ida", "Ida y vuelta"],
    index=1,
)

direction_label = st.selectbox(
    "Sentido del viaje",
    [
        "BRU → España",
        "España → BRU",
    ],
    index=0,
)

st.subheader("Fechas")

col1, col2 = st.columns(2)

with col1:
    outbound_start = st.date_input("Ida desde", value=date(2026, 7, 16))
    outbound_end = st.date_input("Ida hasta", value=date(2026, 7, 20))

with col2:
    if trip_type == "Ida y vuelta":
        return_start = st.date_input("Vuelta desde", value=date(2026, 7, 22))
        return_end = st.date_input("Vuelta hasta", value=date(2026, 7, 25))
    else:
        return_start = None
        return_end = None
        st.info("Viaje de solo ida: no se usa fecha de vuelta.")

if outbound_end < outbound_start:
    st.error("La fecha final de ida debe ser posterior o igual a la fecha inicial.")
    st.stop()

if trip_type == "Ida y vuelta" and return_end < return_start:
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

outbound_count = (outbound_end - outbound_start).days + 1

if trip_type == "Ida y vuelta":
    return_count = (return_end - return_start).days + 1
else:
    return_count = 1

total_combinations = outbound_count * return_count

st.info(
    f"Cada ruta probará {total_combinations} combinaciones de fechas. "
    "Más estaciones = más consultas SerpApi."
)

if st.button("Buscar mejores precios", type="primary"):
    summary_rows = []
    all_rows = []
    errors_rows = []

    progress = st.progress(0)
    total_jobs = max(len(selected_stations) * 2, 1)
    current_job = 0

    for station in selected_stations:
        code = station["code"]
        city = station["city"]
        routes = make_routes(direction_label, code)

        current_job += 1
        progress.progress(current_job / total_jobs)

        with st.status(
            f"Buscando referencia {routes['ref_origin']} → {routes['ref_destination']}..."
        ):
            ref_best, ref_all, ref_errors = search_best_range(
                origin=routes["ref_origin"],
                destination=routes["ref_destination"],
                outbound_start=outbound_start,
                outbound_end=outbound_end,
                return_start=return_start,
                return_end=return_end,
                label=f"REFERENCIA {routes['ref_origin']}-{routes['ref_destination']}",
                trip_type=trip_type,
            )

            all_rows.extend(ref_all)

            if ref_errors:
                errors_rows.append({
                    "ruta": f"{routes['ref_origin']}-{routes['ref_destination']}",
                    "errores": " | ".join(ref_errors[:5]),
                })

        current_job += 1
        progress.progress(current_job / total_jobs)

        with st.status(
            f"Buscando Train&Fly {routes['combo_origin']} → {routes['combo_destination']}..."
        ):
            combo_best, combo_all, combo_errors = search_best_range(
                origin=routes["combo_origin"],
                destination=routes["combo_destination"],
                outbound_start=outbound_start,
                outbound_end=outbound_end,
                return_start=return_start,
                return_end=return_end,
                label=f"TRAINFLY {routes['combo_origin']}-{routes['combo_destination']}",
                trip_type=trip_type,
            )

            all_rows.extend(combo_all)

            if combo_errors:
                errors_rows.append({
                    "ruta": f"{routes['combo_origin']}-{routes['combo_destination']}",
                    "errores": " | ".join(combo_errors[:5]),
                })

        ref_price = ref_best["precio"] if ref_best else None
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
            "tipo_viaje": trip_type,
            "sentido": routes["direction_short"],
            "estacion": city,
            "codigo": code,
            "ruta_referencia": f"{routes['ref_origin']} → {routes['ref_destination']}",
            "ruta_trainfly": f"{routes['combo_origin']} → {routes['combo_destination']}",

            "precio_referencia": ref_price,
            "fecha_ida_ref": ref_best.get("fecha_ida") if ref_best else "",
            "fecha_vuelta_ref": ref_best.get("fecha_vuelta") if ref_best else "",
            "ida_salida_ref": ref_best.get("ida_salida") if ref_best else "",
            "ida_llegada_ref": ref_best.get("ida_llegada") if ref_best else "",
            "ida_itinerario_ref": ref_best.get("ida_itinerario") if ref_best else "",
            "vuelta_salida_ref": ref_best.get("vuelta_salida") if ref_best else "",
            "vuelta_llegada_ref": ref_best.get("vuelta_llegada") if ref_best else "",
            "vuelta_itinerario_ref": ref_best.get("vuelta_itinerario") if ref_best else "",

            "precio_trainfly_minimo": combo_price,
            "fecha_ida_trainfly": combo_best.get("fecha_ida") if combo_best else "",
            "fecha_vuelta_trainfly": combo_best.get("fecha_vuelta") if combo_best else "",
            "ida_salida_trainfly": combo_best.get("ida_salida") if combo_best else "",
            "ida_llegada_trainfly": combo_best.get("ida_llegada") if combo_best else "",
            "ida_itinerario_trainfly": combo_best.get("ida_itinerario") if combo_best else "",
            "vuelta_salida_trainfly": combo_best.get("vuelta_salida") if combo_best else "",
            "vuelta_llegada_trainfly": combo_best.get("vuelta_llegada") if combo_best else "",
            "vuelta_itinerario_trainfly": combo_best.get("vuelta_itinerario") if combo_best else "",

            "diferencia": difference,
            "estado": status,
            "enlace_google_flights_opcion": (
                combo_best.get("enlace_google_flights")
                if combo_best
                else google_flights_link(
                    routes["combo_origin"],
                    routes["combo_destination"],
                    outbound_start.isoformat(),
                    return_start.isoformat() if return_start else None,
                )
            ),
            "booking_token": combo_best.get("booking_token") if combo_best else "",
            "departure_token": combo_best.get("departure_token") if combo_best else "",
            "return_booking_token": combo_best.get("return_booking_token") if combo_best else "",
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
