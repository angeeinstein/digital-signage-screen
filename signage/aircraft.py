"""Static aircraft/airline reference data.

Icon names refer to files in ``static/icons/adsb_icons/<name>.svg``. The
generic icons (a1, a2, a3, a5, a6, b4, c0, cessna) were picked by eye in v1:
a1 = turboprop, a2 = business jet, a3 = regional jet, a5 = narrowbody,
a6 = widebody, b4 = military, c0 = helicopter, a0 = unknown.
"""

from __future__ import annotations

_SPECIFIC: dict[str, list[str]] = {
    "a320": ["A318", "A319", "A320", "A321", "A19N", "A20N", "A21N"],
    "a330": ["A330", "A332", "A333", "A338", "A339"],
    "a340": ["A340", "A342", "A343", "A345", "A346"],
    "a380": ["A380", "A388"],
    "b737": ["B731", "B732", "B733", "B734", "B735", "B736", "B737", "B738", "B739",
             "B37M", "B38M", "B39M", "B3XM"],
    "b747": ["B741", "B742", "B743", "B744", "B747", "B748", "B74R", "B74S"],
    "b767": ["B762", "B763", "B764", "B767"],
    "b777": ["B772", "B773", "B777", "B77L", "B77W", "B778", "B779"],
    "b787": ["B787", "B788", "B789", "B78X"],
    "learjet": ["LJ24", "LJ25", "LJ31", "LJ35", "LJ40", "LJ45", "LJ55", "LJ60", "LJ75"],
    "glf5": ["GLF4", "GLF5", "GLF6", "GLEX", "GL5T", "GL7T", "G150", "G200", "G250", "G280",
             "G450", "G500", "G550", "G650"],
    "fa7x": ["FA7X", "FA8X", "FA10", "FA20", "FA50", "FA6X"],
    "crjx": ["CRJ1", "CRJ2", "CRJ7", "CRJ9", "CRJX"],
    "erj": ["E135", "E145", "E170", "E175", "E75L", "E75S"],
    "e195": ["E190", "E195", "E19X", "E290", "E295"],
    "dh8a": ["DH8A", "DH8B", "DH8C", "DH8D", "DHC6", "DHC7", "DHC8"],
    "md11": ["MD11", "DC10"],
    "f100": ["F100", "F70"],
    "c130": ["C130", "C30J"],
    "cessna": ["C152", "C162", "C172", "C182", "C206", "C208", "C210"],
}

_GENERIC: dict[str, list[str]] = {
    "c0": ["H25B", "H25C", "H60", "EC35", "EC45", "AS50", "AS55", "AS65", "B06", "B407", "B412",
           "B429", "B505", "R22", "R44", "R66", "S76", "EC30", "EC55", "EC75", "H135", "H145",
           "H160", "H175", "AW09", "AW39", "AW69", "AW89", "AW19", "A109", "A139", "A169", "A189",
           "MD50", "MD60", "MD90", "NH90", "UH1", "S70"],
    "a6": ["A350", "A359", "A35K", "A3ST", "B752", "B753", "IL96", "L101", "A124", "A225", "AN124", "AN225"],
    "a1": ["AT43", "AT44", "AT45", "AT46", "AT72", "AT73", "AT75", "AT76", "E120", "SF34", "SH33",
           "SH36", "IL18", "AN12", "AN24", "AN26", "P3", "BE20", "BE30", "B350", "PC12", "TBM7",
           "TBM8", "TBM9", "PC6T", "D228", "J328", "SW4"],
    "a2": ["C25A", "C25B", "C25C", "C25M", "C500", "C510", "C525", "C550", "C551", "C560", "C56X",
           "C650", "C680", "C68A", "C700", "C750", "CL30", "CL35", "CL60", "E35L", "E50P", "E55P",
           "E545", "E550", "F2TH", "F900", "H25A", "PC24", "PRM1", "BE40", "BE9L", "HDJT", "SF50"],
    "cessna": ["P28A", "P28B", "P28R", "P28T", "PA28", "PA31", "PA34", "PA44", "PA46", "SR20",
               "SR22", "BE58", "BE36", "BE95", "C340", "C402", "C414", "C421", "P68", "DA20",
               "DA40", "DA42", "DA50", "DA62", "PA18", "PA22", "ULAC", "C150", "C177", "C77R",
               "M20P", "M20T", "AA5", "TB20", "TB10", "DR40", "G115"],
    "a3": ["RJ70", "RJ85", "RJ1H", "BCS1", "BCS3", "SU95", "AJ27", "A148"],
}

_ICON_BY_TYPE: dict[str, str] = {}
for _icon, _types in {**_GENERIC, **_SPECIFIC}.items():
    for _t in _types:
        _ICON_BY_TYPE[_t] = _icon
# Specific icons win over generic ones
for _icon, _types in _SPECIFIC.items():
    for _t in _types:
        _ICON_BY_TYPE[_t] = _icon

# ADS-B emitter category fallback (DO-260B), used when the type is unknown.
_ICON_BY_EMITTER = {
    "A1": "cessna",  # light
    "A2": "a2",      # small
    "A3": "a5",      # large
    "A4": "a5",      # high vortex large (B757)
    "A5": "a6",      # heavy
    "A6": "b4",      # high performance
    "A7": "c0",      # rotorcraft
    "B1": "cessna",  # glider
    "B4": "cessna",  # ultralight
    "B6": "a0",      # UAV
}

HELICOPTER_ICON = "c0"


def aircraft_icon(type_code: str | None, emitter_category: str | None = None) -> str:
    """Icon name for an ICAO type designator, with sensible fallbacks."""
    t = (type_code or "").upper().strip()
    if t in _ICON_BY_TYPE:
        return _ICON_BY_TYPE[t]
    if emitter_category and emitter_category.upper() in _ICON_BY_EMITTER:
        return _ICON_BY_EMITTER[emitter_category.upper()]
    if not t:
        return "a0"
    if t.startswith(("MIG", "SU2", "SU3", "F1", "F2", "F3", "EUFI", "TOR", "RFAL", "JAS3")):
        return "b4"
    if t.startswith(("A", "B7", "E1", "E2", "MD8", "MD9", "DC9", "C919")):
        return "a5"
    return "a0"


# ICAO airline designator -> short display name (fallback when no route DB hit)
AIRLINES: dict[str, str] = {
    "AAL": "American", "ACA": "Air Canada", "AEE": "Aegean", "AFR": "Air France", "AUA": "Austrian",
    "AZA": "ITA Airways", "BAW": "British Airways", "BEL": "Brussels", "BTI": "airBaltic",
    "CFG": "Condor", "CPA": "Cathay", "CTN": "Croatia", "DAL": "Delta", "DLH": "Lufthansa",
    "EDW": "Edelweiss", "EIN": "Aer Lingus", "EJU": "easyJet Europe", "ETD": "Etihad",
    "ETH": "Ethiopian", "EWG": "Eurowings", "EXS": "Jet2", "EZS": "easyJet Switzerland",
    "EZY": "easyJet", "FDB": "flydubai", "FIN": "Finnair", "IBE": "Iberia", "ICE": "Icelandair",
    "JAF": "TUI fly Belgium", "KLM": "KLM", "LOT": "LOT", "MSR": "EgyptAir", "NOZ": "Norwegian",
    "NSZ": "Norwegian", "PGT": "Pegasus", "QTR": "Qatar", "RYR": "Ryanair", "RUK": "Ryanair UK",
    "SAS": "SAS", "SIA": "Singapore", "SVA": "Saudia", "SWR": "Swiss", "SXS": "SunExpress",
    "TAP": "TAP", "TAY": "ASL Belgium", "THY": "Turkish", "TOM": "TUI", "TRA": "Transavia",
    "TUI": "TUIfly", "TVS": "Smartwings", "UAE": "Emirates", "UAL": "United", "VLG": "Vueling",
    "WMT": "Wizz Air Malta", "WZZ": "Wizz Air", "WUK": "Wizz Air UK", "LDM": "Lauda",
    "AHO": "Air Hamburg", "OAW": "Helvetic", "BCS": "European Air Transport", "ASL": "Air Serbia",
    "MLD": "Air Moldova", "ROT": "TAROM", "LZB": "Bulgaria Air", "OHY": "Onur Air",
    "ELY": "El Al", "IRA": "Iran Air", "KAC": "Kuwait", "GFA": "Gulf Air", "OMA": "Oman Air",
}


def airline_from_callsign(callsign: str) -> tuple[str, str]:
    """Return (ICAO airline code, name) guessed from a callsign like ``DLH4AB``."""
    cs = (callsign or "").strip().upper()
    if len(cs) >= 4 and cs[:3].isalpha() and cs[3].isdigit():
        code = cs[:3]
        return code, AIRLINES.get(code, "")
    return "", ""


def is_christophorus(callsign: str) -> bool:
    """Austrian ÖAMTC rescue helicopters use callsigns like ``C12`` / ``C16``."""
    cs = (callsign or "").strip().upper()
    return len(cs) >= 2 and cs[0] == "C" and cs[1:].isdigit()
