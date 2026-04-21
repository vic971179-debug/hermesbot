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
}
ZODIAC_SIGNS = [
    "Aries",
    "Tauro",
    "Geminis",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Escorpio",
    "Sagitario",
    "Capricornio",
    "Acuario",
    "Piscis",
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
]
INGRESS_PLANETS = [planet for planet in PLANETS if planet[0] != "Luna"]
ASPECTS = [
    ("conjuncion", 0, 3.0),
    ("sextil", 60, 2.5),
    ("cuadratura", 90, 3.0),
    ("trigono", 120, 3.0),
    ("quincuncio", 150, 2.0),
    ("oposicion", 180, 3.0),
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
        pattern = rf"- {re.escape(label)}:\s*(.+)"
        match = re.search(pattern, text)
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
        raise ValueError(f"No hay coordenadas cargadas para '{birth_place}'")
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
        values, _ = swe.calc_ut(jd_ut, planet_id, flags)
        positions[name] = {"lon": values[0], "speed": values[3]}
    return positions


def calc_natal_chart(natal: NatalData):
    utc_dt, year, month, day, hour = to_ut_components(natal.birth_date, natal.birth_time, natal.timezone_name)
    jd_ut = swe.julday(year, month, day, hour)
    cusps, ascmc = swe.houses_ex(jd_ut, natal.latitude, natal.longitude, b'P')
    cusps = [0.0] + list(cusps)
    natal_positions = calc_planet_positions(jd_ut)
    for name, data in natal_positions.items():
        data["house"] = house_of(data["lon"], cusps)
    angles = {"Ascendente": ascmc[0], "Medio Cielo": ascmc[1]}
    return {
        "utc_dt": utc_dt,
        "jd_ut": jd_ut,
        "cusps": cusps,
        "positions": natal_positions,
        "angles": angles,
    }


def calc_current_chart(now_local: datetime):
    utc_dt = now_local.astimezone(timezone.utc)
    hour = utc_dt.hour + utc_dt.minute / 60 + utc_dt.second / 3600
    jd_ut = swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, hour)
    return {"utc_dt": utc_dt, "jd_ut": jd_ut, "positions": calc_planet_positions(jd_ut)}


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


def refine_crossing(start_dt: datetime, end_dt: datetime, value_fn, target: float, iterations: int = 30) -> datetime:
    left = start_dt
    right = end_dt
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


def find_lunation_events(now_local: datetime, timezone_name: str, days_ahead: int = 3):
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
    return sorted(unique.values(), key=lambda item: item[0])


def find_ingress_events(now_local: datetime, days_ahead: int = 3):
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
    return sorted(events, key=lambda item: item[0])


def find_upcoming_events(now_local: datetime, timezone_name: str, days_ahead: int = 3):
    lunations = find_lunation_events(now_local, timezone_name, days_ahead=days_ahead)
    ingresses = find_ingress_events(now_local, days_ahead=days_ahead)
    return sorted(lunations + ingresses, key=lambda item: item[0])


def detect_transits(current_positions, natal_positions, natal_angles):
    transits = []
    targets = {**{k: v["lon"] for k, v in natal_positions.items()}, **natal_angles}
    for t_name, t_data in current_positions.items():
        for n_name, n_lon in targets.items():
            distance = angular_distance(t_data["lon"], n_lon)
            for aspect_name, exact, max_orb in ASPECTS:
                orb = abs(distance - exact)
                if orb <= max_orb:
                    transits.append(
                        {
                            "transit": t_name,
                            "target": n_name,
                            "aspect": aspect_name,
                            "orb": orb,
                            "distance": distance,
                        }
                    )
                    break
    transits.sort(key=lambda item: (item["orb"], item["transit"], item["target"]))
    return transits


def render_report(natal: NatalData, natal_chart, current_chart, transits, upcoming_events) -> str:
    now_local = current_chart["utc_dt"].astimezone(ZoneInfo(natal.timezone_name))
    lines = []
    lines.append("# Carta natal y transitos")
    lines.append("")
    lines.append("## Datos natales")
    lines.append(f"- Nombre: {natal.name}")
    lines.append(f"- Nacimiento local: {natal.birth_date} {natal.birth_time} ({natal.timezone_name})")
    lines.append(f"- Lugar: {natal.birth_place}")
    lines.append(f"- Coordenadas usadas: {natal.latitude:.3f}, {natal.longitude:.3f}")
    lines.append("")
    lines.append("## Carta natal")
    for name, data in natal_chart["positions"].items():
        lines.append(f"- {name}: {format_longitude(data['lon'])} | Casa {data['house']}")
    lines.append(f"- Ascendente: {format_longitude(natal_chart['angles']['Ascendente'])}")
    lines.append(f"- Medio Cielo: {format_longitude(natal_chart['angles']['Medio Cielo'])}")
    lines.append("")
    lines.append("## Momento presente")
    lines.append(f"- Fecha y hora local: {now_local.strftime('%Y-%m-%d %H:%M:%S')} ({natal.timezone_name})")
    for name, data in current_chart["positions"].items():
        lines.append(f"- {name}: {format_longitude(data['lon'])}")
    lines.append("")
    lines.append("## Transitos mas cercanos")
    if not transits:
        lines.append("- No se encontraron aspectos mayores dentro del orbe configurado.")
    else:
        for item in transits[:20]:
            lines.append(
                f"- {item['transit']} {item['aspect']} {item['target']} | orbe {item['orb']:.2f}°"
            )
    lines.append("")
    lines.append("## Eventos proximos (3 dias)")
    if not upcoming_events:
        lines.append("- No hay lunas nuevas, lunas llenas ni cambios de signo dentro de los proximos 3 dias.")
    else:
        for event_dt, label in upcoming_events:
            delta = event_dt - now_local
            total_hours = max(0, int(round(delta.total_seconds() / 3600)))
            lines.append(
                f"- {label} | {event_dt.strftime('%Y-%m-%d %H:%M')} ({natal.timezone_name}) | faltan aprox. {total_hours} h"
            )
    return "\n".join(lines) + "\n"


def main():
    natal = parse_natal_file(NATAL_FILE)
    natal_chart = calc_natal_chart(natal)
    now_local = datetime.now(ZoneInfo(natal.timezone_name))
    current_chart = calc_current_chart(now_local)
    transits = detect_transits(current_chart["positions"], natal_chart["positions"], natal_chart["angles"])
    upcoming_events = find_upcoming_events(now_local, natal.timezone_name, days_ahead=3)
    report = render_report(natal, natal_chart, current_chart, transits, upcoming_events)
    sys.stdout.write(report)


if __name__ == "__main__":
    main()
