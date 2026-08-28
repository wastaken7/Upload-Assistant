from collections.abc import Mapping
from urllib.parse import urlsplit


def _source_value(line: str) -> str | None:
    if "==" in line:
        label, value = line.split("==", 1)
    elif ":" in line:
        label, value = line.split(":", 1)
    else:
        return None

    label_words = "".join(char if char.isalpha() else " " for char in label).split()
    if [word.casefold() for word in label_words] != ["source"]:
        return None

    return value.strip()


def _normalize_service_name(value: str) -> str:
    value = value.strip()
    if "://" in value or ("." in value and " " not in value):
        parsed = urlsplit(value if "://" in value else f"//{value}")
        if parsed.hostname:
            value = parsed.hostname.removeprefix("www.").split(".", 1)[0]

    value = value.casefold().replace("+", "plus")
    return "".join(char for char in value if char.isalnum())


def _resolve_service(value: str, services: Mapping[str, str]) -> tuple[str, str] | None:
    normalized_value = _normalize_service_name(value)
    if not normalized_value:
        return None

    aliases = [(_normalize_service_name(name), code) for name, code in services.items()]

    for alias, code in aliases:
        if alias == normalized_value:
            return code, max((name for name, candidate_code in services.items() if candidate_code == code), key=len, default=code)

    fuzzy_codes = {
        code
        for alias, code in aliases
        if min(len(alias), len(normalized_value)) >= 4 and (alias.startswith(normalized_value) or normalized_value.startswith(alias))
    }
    if len(fuzzy_codes) == 1:
        code = fuzzy_codes.pop()
        return code, max((name for name, candidate_code in services.items() if candidate_code == code), key=len, default=code)

    return None


def parse_nfo_streaming_service(nfo_content: str, services: Mapping[str, str]) -> tuple[str, str, str] | None:
    """Return the NFO source value, service code, and service name when recognized."""
    for line in nfo_content.splitlines():
        source = _source_value(line)
        if source is None:
            continue
        service = _resolve_service(source, services)
        if service:
            code, name = service
            return source, code, name
    return None
