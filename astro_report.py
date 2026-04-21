#!/usr/bin/env python3
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import swisseph as swe


WORKDIR = Path(__file__).resolve().parent
NATAL_FILE = WORKDIR / "carta_natal.md"
DEFAULT_COORDS = {
    "general san martin, buenos aires, argentina": (-34.576, -58.535),
    "capital federal, buenos aires, argentina": (-34.604, -58.382),
}
ZODIAC_SIGNS = [
    "Aries", "Tauro", "Geminis", "Cancer", "Leo", "Virgo",
    "Libra", "Escorpio", "Sagitario", "Capricornio", "Acuario", "Piscis",
]
PLANETS = [
    ("Sol", swe.SUN),
    ("Luna", swe.MOON),
    ("Mercurio", swe.MERCURY),
    ("Venus", swe.VENUS),
    ("Marte", swe.MARS),
    ("Jupiter", swe.JUPITER),
    ("Saturno", swe.SATURN),
    ("Urano", swe.URANUS),
    ("Neptuno", swe.NEPTUNE),
    ("Pluton", swe.PLUTO),
    ("Nodo Norte", swe.TRUE_NODE),
    ("Quiron", swe.CHIRON),
]
INGRESS_PLANETS = [p for p in PLANETS if p[0] not in ("Luna", "Nodo Norte", "Quiron")]
ASPECTS = [
    ("conjuncion", 0, 3.0),
    ("sextil", 60, 2.5),
    ("cuadratura", 90, 3.0),
    ("trigono", 120, 3.0),
    ("quincuncio", 150, 2.0),
    ("oposicion", 180, 3.0),
]
DIGNITIES_TABLE = {
    0:  {"domicilio": "Marte",    "exaltacion": "Sol",      "detrimento": "Venus",    "caida": "Saturno"},
    1:  {"domicilio": "Venus",    "exaltacion": "Luna",     "detrimento": "Marte",    "caida": None},
    2:  {"domicilio": "Mercurio", "exaltacion": None,       "detrimento": "Jupiter",  "caida": None},
    3:  {"domicilio": "Luna",     "exaltacion": "Jupiter",  "detrimento": "Saturno",  "caida": "Marte"},
    4:  {"domicilio": "Sol",      "exaltacion": None,       "detrimento": "Saturno",  "caida": None},
    5:  {"domicilio": "Mercurio", "exaltacion": "Mercurio", "detrimento": "Jupiter",  "caida": "Venus"},
    6:  {"domicilio": "Venus",    "exaltacion": "Saturno",  "detrimento": "Marte",    "caida": "Sol"},
    7:  {"domicilio": "Marte",    "exaltacion": None,       "detrimento": "Venus",    "caida": "Luna"},
    8:  {"domicilio": "Jupiter",  "exaltacion": None,       "detrimento": "Mercurio", "caida": None},
    9:  {"domicilio": "Saturno",  "exaltacion": "Marte",    "detrimento": "Luna",     "caida": "Jupiter"},
    10: {"domicilio": "Saturno",  "exaltacion": None,       "detrimento": "Sol",      "caida": None},
    11: {"domicilio": "Jupiter",  "exaltacion": "Venus",    "detrimento": "Mercurio", "caida": "Mercurio"},
}
MOON_PHASES = [
    (0, 45, "Luna nueva"),
    (45, 90, "Luna creciente"),
    (90, 135, "Cuarto creciente"),
    (135, 180, "Gibosa creciente"),
    (180, 225, "Luna llena"),
    (225, 270, "Gibosa menguante"),
    (270, 315, "Cuarto menguante"),
    (315, 360, "Luna menguante"),
]


@dataclass
class NatalData:
    name: str
    birth_date: str
    birth_time: str
    birth_place: str
    timezone_name: str
    latitude: float
    longitude: float


def parse_natal_file(path: Path) -> NatalData:
    text = path.read_text(encoding="utf-8")

    def extract(label: str) -> str:
        match = re.search(rf"- {re.escape(label)}:\s*(.+)", text)
        if not match:
            raise ValueError(f"Falta el campo '{label}' en {path}")
        return match.group(1).strip()

    name = extract("Nombre")
    birth_date = extract("Fecha de nacimiento")
    birth_time = extract("Hora de nacimiento")
    birth_place = extract("Lugar de nacimiento")
    timezone_name = extract("Zona horaria de nacimiento")
    key = birth_place.lower()
    if key not in DEFAULT_COORDS:
        raise ValueError(f"No hay coordenadas para '{birth_place}'")
    latitude, longitude = DEFAULT_COORDS[key]
    return NatalData(name, birth_date, birth_time, birth_place, timezone_name, latitude, longitude)


def to_ut_components(date_str: str, time_str: str, timezone_name: str):
    local_dt = datetime.fromisoformat(f"{date_str}T{time_str}:00").replace(tzinfo=ZoneInfo(timezone_name))
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt, utc_dt.year, utc_dt.month, utc_dt.day, utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600


def format_longitude(value: float) -> str:
    sign_index = int(value // 30) % 12
    sign = ZODIAC_SIGNS[sign_index]
    deg_in_sign = value % 30
    degrees = int(deg_in_sign)
    minutes = int(round((deg_in_sign - degrees) * 60))
    if minutes == 60:
        degrees += 1
        minutes = 0
    if degrees == 30:
        degrees = 0
        sign = ZODIAC_SIGNS[(sign_index + 1) % 12]
    return f"{degrees:02d}°{minutes:02d}' {sign}"


def house_of(longitude: float, cusps) -> int:
    for idx in range(1, 13):
        start = cusps[idx]
        end = cusps[1] if idx == 12 else cusps[idx + 1]
        span = (end - start) % 360
        dist = (longitude - start) % 360
        if dist < span:
            return idx
    return 12


def calc_planet_positions(jd_ut: float):
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED
    positions = {}
    for name, planet_id in PLANETS:
        try:
            values, _ = swe.calc_ut(jd_ut, planet_id, flags)
            positions[name] = {
                "lon": values[0],
                "lat": values[1],
                "speed": values[3],
                "retrogrado": values[3] < 0,
            }
        except Exception:
            pass
    return positions


def get_dignity(planet_name: str, longitude: float) -> str:
    sign_idx = int(longitude // 30) % 12
    d = DIGNITIES_TABLE[sign_idx]
    tags = []
    if d["domicilio"] == planet_name:
        tags.append("domicilio")
    if d["exaltacion"] == planet_name:
        tags.append("exaltacion")
    if d["detrimento"] == planet_name:
        tags.append("detrimento")
    if d["caida"] == planet_name:
        tags.append("caida")
    return "/".join(tags) if tags else "peregrino"


def calc_natal_chart(natal: NatalData):
    utc_dt, year, month, day, hour = to_ut_components(natal.birth_date, natal.birth_time, natal.timezone_name)
    jd_ut = swe.julday(year, month, day, hour)
    cusps, ascmc = swe.houses_ex(jd_ut, natal.latitude, natal.longitude, b'P')
    cusps_list = [0.0] + list(cusps)
    natal_positions = calc_planet_positions(jd_ut)
    for name, data in natal_positions.items():
        data["house"] = house_of(data["lon"], cusps_list)
        data["dignidad"] = get_dignity(name, data["lon"])
    angles = {"Ascendente": ascmc[0], "Medio Cielo": ascmc[1]}
    return {
        "utc_dt": utc_dt,
        "jd_ut": jd_ut,
        "cusps": cusps_list,
        "positions": natal_positions,
        "angles": angles,
        "ascmc": ascmc,
    }


def calc_current_chart(now_local: datetime):
    utc_dt = now_local.astimezone(timezone.utc)
    hour = utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600
    jd_ut = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour)
    positions = calc_planet_positions(jd_ut)
    return {"utc_dt": utc_dt, "jd_ut": jd_ut, "positions": positions}


def julian_day_from_datetime(dt: datetime) -> float:
    utc_dt = dt.astimezone(timezone.utc)
    hour = utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600
    return swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour)


def planetary_longitude(dt: datetime, planet_id: int) -> float:
    values, _ = swe.calc_ut(julian_day_from_datetime(dt), planet_id, swe.FLG_SWIEPH | swe.FLG_SPEED)
    return values[0]


def angular_distance(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def signed_angle_diff(value: float, target: float) -> float:
    return ((value - target + 180) % 360) - 180


def refine_crossing(start_dt, end_dt, value_fn, target, iterations=30):
    left, right = start_dt, end_dt
    left_diff = signed_angle_diff(value_fn(left), target)
    for _ in range(iterations):
        mid = left + (right - left) / 2
        mid_diff = signed_angle_diff(value_fn(mid), target)
        if left_diff == 0 or left_diff * mid_diff <= 0:
            right = mid
        else:
            left = mid
            left_diff = mid_diff
    return left + (right - left) / 2


def moon_phase_angle(dt: datetime) -> float:
    jd_ut = julian_day_from_datetime(dt)
    sun = swe.calc_ut(jd_ut, swe.SUN, swe.FLG_SWIEPH)[0][0]
    moon = swe.calc_ut(jd_ut, swe.MOON, swe.FLG_SWIEPH)[0][0]
    return (moon - sun) % 360


def get_moon_phase_name(angle: float) -> str:
    for start, end, name in MOON_PHASES:
        if start <= angle < end:
            return name
    return "Luna menguante"


def find_lunation_events(now_local, timezone_name, days_ahead=3):
    events = []
    end_local = now_local + timedelta(days=days_ahead)
    current = now_local
    step = timedelta(hours=6)
    previous_phase = moon_phase_angle(current)
    targets = [("Luna nueva", 0.0), ("Luna llena", 180.0)]
    while current < end_local:
        next_dt = min(current + step, end_local)
        next_phase = moon_phase_angle(next_dt)
        for label, target in targets:
            prev_diff = signed_angle_diff(previous_phase, target)
            next_diff = signed_angle_diff(next_phase, target)
            crossed = prev_diff == 0 or prev_diff * next_diff < 0
            if target == 0.0 and abs(next_phase - previous_phase) > 180:
                crossed = True
            if crossed:
                event_dt = refine_crossing(current, next_dt, moon_phase_angle, target)
                if now_local <= event_dt <= end_local:
                    moon_lon = planetary_longitude(event_dt, swe.MOON)
                    sign = ZODIAC_SIGNS[int(moon_lon // 30) % 12]
                    events.append((event_dt, f"{label} en {sign}"))
        current = next_dt
        previous_phase = next_phase
    unique = {}
    for dt, label in events:
        unique[(label, dt.strftime("%Y-%m-%d %H:%M"))] = (dt, label)
    return sorted(unique.values(), key=lambda x: x[0])


def find_ingress_events(now_local, days_ahead=3):
    events = []
    end_local = now_local + timedelta(days=days_ahead)
    step = timedelta(hours=6)
    for planet_name, planet_id in INGRESS_PLANETS:
        current = now_local
        prev_lon = planetary_longitude(current, planet_id)
        prev_sign = int(prev_lon // 30) % 12
        while current < end_local:
            next_dt = min(current + step, end_local)
            next_lon = planetary_longitude(next_dt, planet_id)
            next_sign = int(next_lon // 30) % 12
            if next_sign != prev_sign:
                target = (next_sign * 30.0) % 360
                event_dt = refine_crossing(current, next_dt, lambda dt: planetary_longitude(dt, planet_id), target)
                if now_local <= event_dt <= end_local:
                    events.append((event_dt, f"{planet_name} entra en {ZODIAC_SIGNS[next_sign]}"))
                break
            current = next_dt
            prev_sign = next_sign
    return sorted(events, key=lambda x: x[0])


def find_upcoming_events(now_local, timezone_name, days_ahead=3):
    lunations = find_lunation_events(now_local, timezone_name, days_ahead=days_ahead)
    ingresses = find_ingress_events(now_local, days_ahead=days_ahead)
    return sorted(lunations + ingresses, key=lambda x: x[0])


def detect_transits(current_positions, natal_positions, natal_angles):
    transits = []
    targets = {**{k: v["lon"] for k, v in natal_positions.items()}, **natal_angles}
    for t_name, t_data in current_positions.items():
        for n_name, n_lon in targets.items():
            distance = angular_distance(t_data["lon"], n_lon)
            for aspect_name, exact, max_orb in ASPECTS:
                orb = abs(distance - exact)
                if orb <= max_orb:
                    speed = abs(t_data["speed"])
                    hours_exact = round((orb / speed) * 24, 1) if speed > 0.001 else None
                    aplicando = (distance - exact) * (1 if t_data["speed"] > 0 else -1) < 0
                    transits.append({
                        "transit": t_name,
                        "target": n_name,
                        "aspect": aspect_name,
                        "orb": orb,
                        "retrogrado": t_data["retrogrado"],
                        "aplicando": aplicando,
                        "horas_exacto": hours_exact,
                    })
                    break
    transits.sort(key=lambda x: (x["orb"], x["transit"], x["target"]))
    return transits


def detect_natal_aspects(natal_positions):
    aspects = []
    planets = list(natal_positions.items())
    for i, (name_a, data_a) in enumerate(planets):
        for name_b, data_b in planets[i + 1:]:
            distance = angular_distance(data_a["lon"], data_b["lon"])
            for aspect_name, exact, max_orb in ASPECTS:
                orb = abs(distance - exact)
                if orb <= max_orb:
                    aspects.append({
                        "planeta_a": name_a,
                        "planeta_b": name_b,
                        "aspect": aspect_name,
                        "orb": orb,
                    })
                    break
    aspects.sort(key=lambda x: x["orb"])
    return aspects


def detect_transit_to_transit(current_positions):
    aspects = []
    planets = list(current_positions.items())
    for i, (name_a, data_a) in enumerate(planets):
        for name_b, data_b in planets[i + 1:]:
            distance = angular_distance(data_a["lon"], data_b["lon"])
            for aspect_name, exact, max_orb in ASPECTS:
                orb = abs(distance - exact)
                if orb <= max_orb:
                    aspects.append({
                        "planeta_a": name_a,
                        "planeta_b": name_b,
                        "aspect": aspect_name,
                        "orb": orb,
                    })
                    break
    aspects.sort(key=lambda x: x["orb"])
    return aspects


def render_report(natal: NatalData, natal_chart, current_chart, transits, natal_aspects, transit_aspects, upcoming_events) -> str:
    now_local = current_chart["utc_dt"].astimezone(ZoneInfo(natal.timezone_name))
    phase_angle = moon_phase_angle(now_local)
    phase_name = get_moon_phase_name(phase_angle)
    phase_pct = round(phase_angle / 360 * 100, 1)
    L = []

    L.append(f"HERMES | {now_local.strftime('%Y-%m-%d %H:%M')} | {natal.name}")
    L.append(f"Luna: {phase_name} {phase_pct}% | {format_longitude(current_chart['positions']['Luna']['lon'])}")
    L.append("")

    L.append("=CARTA NATAL=")
    asc = format_longitude(natal_chart['angles']['Ascendente'])
    mc = format_longitude(natal_chart['angles']['Medio Cielo'])
    L.append(f"ASC {asc} | MC {mc}")
    for name, data in natal_chart["positions"].items():
        r = "Rx" if data["retrogrado"] else "  "
        L.append(f"{name:<12} {format_longitude(data['lon'])} {r} C{data['house']:02d} {data['dignidad']}")

    L.append("")
    L.append("=CASAS=")
    row = []
    for i in range(1, 13):
        row.append(f"C{i:02d}:{format_longitude(natal_chart['cusps'][i])}")
        if len(row) == 2:
            L.append("  ".join(row))
            row = []

    L.append("")
    L.append("=ASPECTOS NATALES=")
    for a in natal_aspects[:8]:
        L.append(f"{a['planeta_a']} {a['aspect']} {a['planeta_b']} {a['orb']:.1f}°")

    L.append("")
    L.append("=TRANSITO AHORA=")
    for name, data in current_chart["positions"].items():
        r = "Rx" if data["retrogrado"] else "  "
        L.append(f"{name:<12} {format_longitude(data['lon'])} {r} {data['speed']:+.3f}°/d")

    if transit_aspects:
        L.append("")
        L.append("=ENTRE TRANSITOS=")
        for a in transit_aspects[:5]:
            L.append(f"{a['planeta_a']} {a['aspect']} {a['planeta_b']} {a['orb']:.1f}°")

    L.append("")
    L.append("=TRANSITOS A NATAL=")
    for item in transits[:15]:
        r = "Rx" if item["retrogrado"] else ""
        ap = "apl" if item["aplicando"] else "sep"
        t = f"~{item['horas_exacto']:.0f}h" if item["horas_exacto"] is not None else ""
        L.append(f"{item['transit']}{r} {item['aspect']} {item['target']} {item['orb']:.1f}° {ap} {t}")

    if upcoming_events:
        L.append("")
        L.append("=PROXIMOS 3 DIAS=")
        for event_dt, label in upcoming_events:
            delta = event_dt - now_local
            hrs = max(0, int(round(delta.total_seconds() / 3600)))
            L.append(f"{label} | {event_dt.strftime('%m-%d %H:%M')} | ~{hrs}h")

    return "\n".join(L) + "\n"


def main():
    natal_file = Path(sys.argv[1]) if len(sys.argv) > 1 else NATAL_FILE
    natal = parse_natal_file(natal_file)
    natal_chart = calc_natal_chart(natal)
    now_local = datetime.now(ZoneInfo(natal.timezone_name))
    current_chart = calc_current_chart(now_local)
    transits = detect_transits(current_chart["positions"], natal_chart["positions"], natal_chart["angles"])
    natal_aspects = detect_natal_aspects(natal_chart["positions"])
    transit_aspects = detect_transit_to_transit(current_chart["positions"])
    upcoming_events = find_upcoming_events(now_local, natal.timezone_name, days_ahead=3)
    report = render_report(natal, natal_chart, current_chart, transits, natal_aspects, transit_aspects, upcoming_events)
    sys.stdout.write(report)


if __name__ == "__main__":
    main()
