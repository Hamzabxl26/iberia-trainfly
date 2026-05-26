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

    response = requests.get("https://serpapi.com/search", params=params, timeout=90)
    response.raise_for_status()
    return response.json()


def extract_blocks(data):
    blocks = []
    blocks.extend(data.get("best_flights", []) or [])
    blocks.extend(data.get("other_flights", []) or [])
    return blocks


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
    duration_sum = 0
    has_duration = False

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
        if isinstance(duration, int):
            duration_sum += duration
            has_duration = True

        itinerary.append(
            f"{dep.get('id', '')} {dep.get('time', '')} → "
            f"{arr.get('id', '')} {arr.get('time', '')}"
            + (f" ({duration} min)" if duration else "")
        )

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

    for block in extract_blocks(data):
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
            "precio": block.get("price"),
            "moneda": "EUR",
            "duracion_total_min": block.get("total_duration"),

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

            "departure_token": block.get("departure_token", "") or "",
            "booking_token": block.get("booking_token", "") or "",
            "return_booking_token": "",
            "enlace_google_flights": google_flights_link(origin, destination, outbound_date, return_date),
        })

    return rows


def flatten_return_results(data):
    rows = []

    for block in extract_blocks(data):
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
    valid = [r for r in rows if isinstance(r.get("precio"), (int, float))]
    if not valid:
        return None
    return min(valid, key=lambda r: r["precio"])


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


def search_best_range(origin, destination, outbound_start, outbound_end, return_start=None, return_end=None, trip_type="Solo ida", label=""):
    all_rows = []
    best = None
    errors = []

    outbound_dates = list(daterange(outbound_start, outbound_end))
    return_dates = [None] if trip_type == "Solo ida" else list(daterange(return_start, return_end))

    for outbound_date in outbound_dates:
        for return_date in return_dates:
            try:
                data = serpapi_google_flights(origin, destination, outbound_date, return_date)

                rows = flatten_outbound_results(
                    data=data,
                    origin=origin,
                    destination=destination,
                    outbound_date=outbound_date,
                    return_date=return_date,
                    label=label or f"{origin}-{destination}",
                    trip_type=trip_type,
                )

                rows = enrich_rows_with_return_details(rows)
                all_rows.extend(rows)

                candidate = best_row(rows)
                if candidate and (best is None or candidate["precio"] < best["precio"]):
                    best = candidate

            except Exception as exc:
                errors.append(f"{origin}-{destination} {outbound_date}/{return_date or ''}: {exc}")

    return best, all_rows, errors


def row_to_option_row(option_type, station_city, station_code, outbound_best, return_best=None):
    outbound_price = outbound_best.get("precio") if outbound_best else None
    return_price = return_best.get("precio") if return_best else None

    if return_best:
        if isinstance(outbound_price, (int, float)) and isinstance(return_price, (int, float)):
            total_price = outbound_price + return_price
        else:
            total_price = None
    else:
        total_price = outbound_price

    return {
        "tipo_opcion": option_type,
        "estacion": station_city,
        "codigo": station_code,

        "precio_total": total_price,
        "precio_ida": outbound_price,
        "precio_vuelta": return_price,

        "ida_origen": outbound_best.get("origen") if outbound_best else "",
        "ida_destino": outbound_best.get("destino") if outbound_best else "",
        "ida_fecha": outbound_best.get("fecha_ida") if outbound_best else "",
        "ida_salida": outbound_best.get("ida_salida") if outbound_best else "",
        "ida_llegada": outbound_best.get("ida_llegada") if outbound_best else "",
        "ida_companias": outbound_best.get("ida_companias") if outbound_best else "",
        "ida_vuelos": outbound_best.get("ida_vuelos") if outbound_best else "",
        "ida_itinerario": outbound_best.get("ida_itinerario") if outbound_best else "",

        "vuelta_origen": return_best.get("origen") if return_best else outbound_best.get("origen", "") if outbound_best else "",
        "vuelta_destino": return_best.get("destino") if return_best else outbound_best.get("destino", "") if outbound_best else "",
        "vuelta_fecha": return_best.get("fecha_ida") if return_best else outbound_best.get("fecha_vuelta", "") if outbound_best else "",
        "vuelta_salida": return_best.get("ida_salida") if return_best else outbound_best.get("vuelta_salida", "") if outbound_best else "",
        "vuelta_llegada": return_best.get("ida_llegada") if return_best else outbound_best.get("vuelta_llegada", "") if outbound_best else "",
        "vuelta_companias": return_best.get("ida_companias") if return_best else outbound_best.get("vuelta_companias", "") if outbound_best else "",
        "vuelta_vuelos": return_best.get("ida_vuelos") if return_best else outbound_best.get("vuelta_vuelos", "") if outbound_best else "",
        "vuelta_itinerario": return_best.get("ida_itinerario") if return_best else outbound_best.get("vuelta_itinerario", "") if outbound_best else "",

        "enlace_ida": outbound_best.get("enlace_google_flights") if outbound_best else "",
        "enlace_vuelta": return_best.get("enlace_google_flights") if return_best else "",
        "booking_token_ida": outbound_best.get("booking_token") if outbound_best else "",
        "booking_token_vuelta": return_best.get("booking_token") if return_best else outbound_best.get("return_booking_token", "") if outbound_best else "",
        "departure_token_ida": outbound_best.get("departure_token") if outbound_best else "",
    }


# ============================================================
# STREAMLIT UI
# ============================================================

st.set_page_config(page_title="Comparador Iberia Train&Fly", layout="wide")
st.title("Comparador Iberia Train&Fly — Google Flights / SerpApi")

if not SERPAPI_KEY:
    st.error("Falta la SERPAPI_KEY. Añádela en Streamlit Cloud: Manage app → Settings → Secrets.")
    st.stop()

st.caption("Busca combinaciones baratas entre Bélgica y España usando vuelos simples, ida/vuelta y Train&Fly.")

mode = st.selectbox(
    "Modo de búsqueda",
    [
        "Solo ida",
        "Ida y vuelta simétrico",
        "Train&Fly ida + vuelo simple vuelta",
        "Train&Fly ida + vuelta a otra estación",
        "Comparar todas las opciones",
    ],
    index=4,
)

direction = st.selectbox(
    "Sentido principal",
    [
        "España → BRU",
        "BRU → España",
    ],
    index=0,
)

st.subheader("Fechas")

col1, col2 = st.columns(2)
with col1:
    outbound_start = st.date_input("Ida desde", value=date(2026, 6, 30))
    outbound_end = st.date_input("Ida hasta", value=date(2026, 6, 30))

with col2:
    return_start = st.date_input("Vuelta desde", value=date(2026, 7, 2))
    return_end = st.date_input("Vuelta hasta", value=date(2026, 7, 2))

if outbound_end < outbound_start:
    st.error("La fecha final de ida debe ser posterior o igual a la inicial.")
    st.stop()

if return_end < return_start:
    st.error("La fecha final de vuelta debe ser posterior o igual a la inicial.")
    st.stop()

st.subheader("Estaciones")

station_labels = [f"{s['code']} — {s['city']}" for s in STATIONS]

selected_outbound_labels = st.multiselect(
    "Estaciones de ida",
    station_labels,
    default=[station_labels[1]],  # XQA Sevilla
)

selected_return_labels = st.multiselect(
    "Estaciones alternativas de vuelta",
    station_labels,
    default=[station_labels[3]],  # YJE Alicante
)

selected_outbound = [
    next(s for s in STATIONS if s["code"] == label.split(" — ", 1)[0])
    for label in selected_outbound_labels
]

selected_return = [
    next(s for s in STATIONS if s["code"] == label.split(" — ", 1)[0])
    for label in selected_return_labels
]

outbound_count = (outbound_end - outbound_start).days + 1
return_count = (return_end - return_start).days + 1

st.info(
    f"Plage aller : {outbound_count} jour(s). Plage retour : {return_count} jour(s). "
    "Attention aux quotas SerpApi, parce que les API aussi aiment facturer la curiosité humaine."
)

if st.button("Buscar mejores opciones", type="primary"):
    option_rows = []
    all_rows = []
    error_rows = []

    progress = st.progress(0)
    total_jobs = max(len(selected_outbound) * 6, 1)
    current_job = 0

    for station in selected_outbound:
        code = station["code"]
        city = station["city"]

        if direction == "España → BRU":
            trainfly_out_origin = code
            trainfly_out_dest = "BRU"
            simple_out_origin = "MAD"
            simple_out_dest = "BRU"
            simple_return_origin = "BRU"
            simple_return_dest = "MAD"
            symmetric_return_origin = "BRU"
            symmetric_return_dest = code
        else:
            trainfly_out_origin = "BRU"
            trainfly_out_dest = code
            simple_out_origin = "BRU"
            simple_out_dest = "MAD"
            simple_return_origin = "MAD"
            simple_return_dest = "BRU"
            symmetric_return_origin = code
            symmetric_return_dest = "BRU"

        # 1. Référence vol aller-retour simple même origine/destination
        if mode in ["Ida y vuelta simétrico", "Comparar todas las opciones"]:
            current_job += 1
            progress.progress(min(current_job / total_jobs, 1.0))
            with st.status(f"Buscando vuelo ida/vuelta simple {simple_out_origin} ↔ {simple_out_dest}..."):
                ref_rt_best, ref_rt_all, ref_rt_errors = search_best_range(
                    simple_out_origin,
                    simple_out_dest,
                    outbound_start,
                    outbound_end,
                    return_start,
                    return_end,
                    trip_type="Ida y vuelta",
                    label=f"FLIGHT_RT {simple_out_origin}-{simple_out_dest}",
                )
                all_rows.extend(ref_rt_all)
                if ref_rt_errors:
                    error_rows.append({"ruta": f"{simple_out_origin}-{simple_out_dest}", "errores": " | ".join(ref_rt_errors[:5])})

                option_rows.append(
                    row_to_option_row(
                        "FLIGHT_RT",
                        city,
                        code,
                        ref_rt_best,
                        None,
                    )
                )

        # 2. Train&Fly aller-retour symétrique
        if mode in ["Ida y vuelta simétrico", "Comparar todas las opciones"]:
            current_job += 1
            progress.progress(min(current_job / total_jobs, 1.0))
            with st.status(f"Buscando Train&Fly ida/vuelta {trainfly_out_origin} ↔ {trainfly_out_dest}..."):
                tf_rt_best, tf_rt_all, tf_rt_errors = search_best_range(
                    trainfly_out_origin,
                    trainfly_out_dest,
                    outbound_start,
                    outbound_end,
                    return_start,
                    return_end,
                    trip_type="Ida y vuelta",
                    label=f"TRAINFLY_RT {trainfly_out_origin}-{trainfly_out_dest}",
                )
                all_rows.extend(tf_rt_all)
                if tf_rt_errors:
                    error_rows.append({"ruta": f"{trainfly_out_origin}-{trainfly_out_dest}", "errores": " | ".join(tf_rt_errors[:5])})

                option_rows.append(
                    row_to_option_row(
                        "TRAINFLY_RT",
                        city,
                        code,
                        tf_rt_best,
                        None,
                    )
                )

        # 3. Solo ida Train&Fly
        if mode in ["Solo ida", "Comparar todas las opciones"]:
            current_job += 1
            progress.progress(min(current_job / total_jobs, 1.0))
            with st.status(f"Buscando Train&Fly solo ida {trainfly_out_origin} → {trainfly_out_dest}..."):
                tf_ow_best, tf_ow_all, tf_ow_errors = search_best_range(
                    trainfly_out_origin,
                    trainfly_out_dest,
                    outbound_start,
                    outbound_end,
                    trip_type="Solo ida",
                    label=f"TRAINFLY_ONEWAY {trainfly_out_origin}-{trainfly_out_dest}",
                )
                all_rows.extend(tf_ow_all)
                if tf_ow_errors:
                    error_rows.append({"ruta": f"{trainfly_out_origin}-{trainfly_out_dest}", "errores": " | ".join(tf_ow_errors[:5])})

                option_rows.append(
                    row_to_option_row(
                        "TRAINFLY_ONEWAY",
                        city,
                        code,
                        tf_ow_best,
                        None,
                    )
                )

        # 4. Train&Fly ida + vol simple vuelta
        if mode in ["Train&Fly ida + vuelo simple vuelta", "Comparar todas las opciones"]:
            current_job += 1
            progress.progress(min(current_job / total_jobs, 1.0))
            with st.status(f"Buscando Train&Fly ida + vuelo simple vuelta para {city}..."):
                tf_out_best, tf_out_all, tf_out_errors = search_best_range(
                    trainfly_out_origin,
                    trainfly_out_dest,
                    outbound_start,
                    outbound_end,
                    trip_type="Solo ida",
                    label=f"TRAINFLY_OUT {trainfly_out_origin}-{trainfly_out_dest}",
                )
                ret_flight_best, ret_flight_all, ret_flight_errors = search_best_range(
                    simple_return_origin,
                    simple_return_dest,
                    return_start,
                    return_end,
                    trip_type="Solo ida",
                    label=f"RETURN_FLIGHT {simple_return_origin}-{simple_return_dest}",
                )

                all_rows.extend(tf_out_all)
                all_rows.extend(ret_flight_all)

                if tf_out_errors:
                    error_rows.append({"ruta": f"{trainfly_out_origin}-{trainfly_out_dest}", "errores": " | ".join(tf_out_errors[:5])})
                if ret_flight_errors:
                    error_rows.append({"ruta": f"{simple_return_origin}-{simple_return_dest}", "errores": " | ".join(ret_flight_errors[:5])})

                option_rows.append(
                    row_to_option_row(
                        "TRAINFLY_OUT + FLIGHT_RETURN",
                        city,
                        code,
                        tf_out_best,
                        ret_flight_best,
                    )
                )

        # 5. Train&Fly ida + retour autre gare
        if mode in ["Train&Fly ida + vuelta a otra estación", "Comparar todas las opciones"]:
            for return_station in selected_return:
                return_code = return_station["code"]
                return_city = return_station["city"]

                if direction == "España → BRU":
                    ret_origin = "BRU"
                    ret_dest = return_code
                else:
                    ret_origin = return_code
                    ret_dest = "BRU"

                current_job += 1
                progress.progress(min(current_job / total_jobs, 1.0))
                with st.status(f"Buscando Train&Fly ida + vuelta estación {return_city}..."):
                    tf_out_best, tf_out_all, tf_out_errors = search_best_range(
                        trainfly_out_origin,
                        trainfly_out_dest,
                        outbound_start,
                        outbound_end,
                        trip_type="Solo ida",
                        label=f"TRAINFLY_OUT {trainfly_out_origin}-{trainfly_out_dest}",
                    )
                    tf_ret_best, tf_ret_all, tf_ret_errors = search_best_range(
                        ret_origin,
                        ret_dest,
                        return_start,
                        return_end,
                        trip_type="Solo ida",
                        label=f"TRAINFLY_RETURN_ALT {ret_origin}-{ret_dest}",
                    )

                    all_rows.extend(tf_out_all)
                    all_rows.extend(tf_ret_all)

                    if tf_out_errors:
                        error_rows.append({"ruta": f"{trainfly_out_origin}-{trainfly_out_dest}", "errores": " | ".join(tf_out_errors[:5])})
                    if tf_ret_errors:
                        error_rows.append({"ruta": f"{ret_origin}-{ret_dest}", "errores": " | ".join(tf_ret_errors[:5])})

                    row = row_to_option_row(
                        "TRAINFLY_OUT + TRAINFLY_RETURN_ALT",
                        f"{city} / vuelta {return_city}",
                        f"{code}/{return_code}",
                        tf_out_best,
                        tf_ret_best,
                    )
                    option_rows.append(row)

    df_options = pd.DataFrame(option_rows)
    df_all = pd.DataFrame(all_rows)
    df_errors = pd.DataFrame(error_rows)

    if not df_options.empty and "precio_total" in df_options.columns:
        df_options = df_options.sort_values(by="precio_total", na_position="last")

    st.subheader("🏆 Mejores opciones comparadas")
    st.dataframe(df_options, use_container_width=True)

    st.download_button(
        "Descargar opciones comparadas CSV",
        df_options.to_csv(index=False).encode("utf-8-sig"),
        file_name="opciones_comparadas_trainfly.csv",
        mime="text/csv",
    )

    st.subheader("Todos los resultados brutos")
    st.dataframe(df_all, use_container_width=True)

    st.download_button(
        "Descargar todos los resultados CSV",
        df_all.to_csv(index=False).encode("utf-8-sig"),
        file_name="todos_los_resultados_trainfly.csv",
        mime="text/csv",
    )

    if not df_errors.empty:
        st.subheader("Errores")
        st.dataframe(df_errors, use_container_width=True)
