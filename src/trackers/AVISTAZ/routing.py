from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import cli_ui

from src.console import logger
from src.meta import Meta

# These are the country groups used by the three tracker rule implementations.
PRIVATEHD_COUNTRIES = frozenset(
    ["AG", "AI", "AU", "BB", "BM", "BS", "BZ", "CA", "CW", "DM", "GB", "GD", "IE", "JM", "KN", "KY", "LC", "MS", "NZ", "PR", "TC", "TT", "US", "VC", "VG", "VI"]
)
AVISTAZ_COUNTRIES = frozenset(
    ["BD", "BN", "BT", "CN", "HK", "ID", "IN", "JP", "KH", "KP", "KR", "LA", "LK", "MM", "MN", "MO", "MY", "NP", "PH", "PK", "SG", "TH", "TL", "TW", "VN"]
)
ASIAN_COUNTRIES = frozenset(
    [
        "AE",
        "AF",
        "AM",
        "AZ",
        "BD",
        "BH",
        "BN",
        "BT",
        "CN",
        "CY",
        "GE",
        "HK",
        "ID",
        "IL",
        "IN",
        "IQ",
        "IR",
        "JO",
        "JP",
        "KG",
        "KH",
        "KP",
        "KR",
        "KW",
        "KZ",
        "LA",
        "LB",
        "LK",
        "MM",
        "MN",
        "MO",
        "MV",
        "MY",
        "NP",
        "OM",
        "PH",
        "PK",
        "PS",
        "QA",
        "SA",
        "SG",
        "SY",
        "TH",
        "TJ",
        "TL",
        "TM",
        "TR",
        "TW",
        "UZ",
        "VN",
        "YE",
    ]
)
CINEMAZ_COUNTRIES = frozenset(
    [
        "AO",
        "BF",
        "BI",
        "BJ",
        "BW",
        "CD",
        "CF",
        "CG",
        "CI",
        "CM",
        "CV",
        "DJ",
        "DZ",
        "EG",
        "EH",
        "ER",
        "ET",
        "GA",
        "GH",
        "GM",
        "GN",
        "GQ",
        "GW",
        "IO",
        "KE",
        "KM",
        "LR",
        "LS",
        "LY",
        "MA",
        "MG",
        "ML",
        "MR",
        "MU",
        "MW",
        "MZ",
        "NA",
        "NE",
        "NG",
        "RE",
        "RW",
        "SC",
        "SD",
        "SH",
        "SL",
        "SN",
        "SO",
        "SS",
        "ST",
        "SZ",
        "TD",
        "TF",
        "TG",
        "TN",
        "TZ",
        "UG",
        "YT",
        "ZA",
        "ZM",
        "ZW",
        "AR",
        "AW",
        "BL",
        "BO",
        "BQ",
        "BR",
        "CL",
        "CO",
        "CR",
        "CU",
        "DO",
        "EC",
        "FK",
        "GF",
        "GP",
        "GS",
        "GT",
        "GY",
        "HN",
        "HT",
        "MF",
        "MQ",
        "MX",
        "NI",
        "PA",
        "PE",
        "PM",
        "PY",
        "SR",
        "SV",
        "SX",
        "UY",
        "VE",
        "AD",
        "AL",
        "AT",
        "AX",
        "BA",
        "BE",
        "BG",
        "BY",
        "CH",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FO",
        "FR",
        "GG",
        "GI",
        "GR",
        "HR",
        "HU",
        "IS",
        "IT",
        "JE",
        "LI",
        "LT",
        "LU",
        "LV",
        "MC",
        "MD",
        "ME",
        "MK",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "RS",
        "RU",
        "SE",
        "SI",
        "SJ",
        "SK",
        "SM",
        "SU",
        "UA",
        "VA",
        "XC",
    ]
)


@dataclass(frozen=True)
class RoutingDecision:
    source: str
    destination: str | None
    reason: str
    automatic: bool


class AvistaZNetworkRouter:
    """Resolve unambiguous AvistaZ/CinemaZ/PrivateHD content routing."""

    network_trackers = frozenset({"AVISTAZ", "CINEMAZ", "PRIVATEHD"})

    def __init__(self, config: dict[str, Any], tracker_class_map: dict[str, Any]):
        self.config = config
        self.tracker_class_map = tracker_class_map

    @staticmethod
    def _countries(meta: Meta) -> set[str]:
        raw_countries = meta.origin_country if isinstance(meta.origin_country, list) else []
        return {str(country).upper() for country in raw_countries if country}

    @staticmethod
    def _is_older_than_50_years(meta: Meta) -> bool:
        try:
            return datetime.now(UTC).year - int(meta.year) >= 50
        except TypeError, ValueError:
            return False

    @staticmethod
    def _is_sd(meta: Meta) -> bool:
        if bool(meta.sd):
            return True
        resolution_match = re.search(r"(\d{3,4})", str(meta.resolution or ""))
        return bool(resolution_match and int(resolution_match.group(1)) < 720)

    def decide(self, source: str, meta: Meta) -> RoutingDecision | None:
        source = source.upper()
        countries = self._countries(meta)
        destinations: list[tuple[str, str]] = []

        if source == "PRIVATEHD":
            if self._is_older_than_50_years(meta):
                destinations.append(("CINEMAZ", "content is 50+ years old"))
            if countries & ASIAN_COUNTRIES:
                destinations.append(("AVISTAZ", "Asian production"))
            elif countries & CINEMAZ_COUNTRIES:
                destinations.append(("CINEMAZ", "production belongs to CinemaZ's region"))

        elif source == "CINEMAZ":
            if countries & AVISTAZ_COUNTRIES:
                destinations.append(("AVISTAZ", "Asian production"))
            elif countries & PRIVATEHD_COUNTRIES and not self._is_older_than_50_years(meta) and not self._is_sd(meta):
                # Mainstream status cannot be inferred safely, so this remains a suggestion.
                return RoutingDecision(source, "PRIVATEHD", "recent HD content from a major English-speaking country may belong on PrivateHD", automatic=False)

        elif source == "AVISTAZ":
            if countries & PRIVATEHD_COUNTRIES:
                destinations.append(("PRIVATEHD", "production belongs to a major English-speaking country"))
            elif countries & (CINEMAZ_COUNTRIES | (ASIAN_COUNTRIES - AVISTAZ_COUNTRIES)):
                destinations.append(("CINEMAZ", "production belongs to CinemaZ's region"))

        if not destinations:
            return None
        target_names = {target for target, _reason in destinations}
        if len(target_names) != 1:
            reasons = "; ".join(reason for _target, reason in destinations)
            return RoutingDecision(source, None, f"conflicting routing rules: {reasons}", automatic=False)
        destination, reason = destinations[0]
        return RoutingDecision(source, destination, reason, automatic=True)

    async def apply(self, meta: Meta) -> None:
        trackers = [str(tracker).upper() for tracker in meta.trackers]
        for source in tuple(trackers):
            if source not in self.network_trackers:
                continue
            decision = self.decide(source, meta)
            if decision is None:
                continue

            source_status = meta.tracker_status.setdefault(source, {})
            source_status["routing_reason"] = decision.reason
            if not decision.automatic or not decision.destination:
                source_status["routing_suggested_to"] = decision.destination
                logger.info(f"{source}: [yellow]Routing requires review: {decision.reason}[/yellow]")
                continue

            destination = decision.destination
            if meta.unattended:
                enabled = bool(self.config.get("DEFAULT", {}).get("avistaz_network_auto_redirect", False))
                if not enabled:
                    source_status["routing_suggested_to"] = destination
                    logger.info(
                        f"{source}: [yellow]Suggested redirect to {destination}: {decision.reason}. Set avistaz_network_auto_redirect=true to enable this in unattended mode.[/yellow]"
                    )
                    continue
            else:
                prompt = f"{source}: {decision.reason}. Redirect this upload to {destination}?"
                if not cli_ui.ask_yes_no(prompt, default=True):
                    source_status["routing_suggested_to"] = destination
                    continue

            destination_class = self.tracker_class_map.get(destination)
            if destination_class is None:
                source_status["routing_error"] = f"Destination {destination} is not available."
                continue
            try:
                destination_tracker = destination_class(config=self.config)
                if not await destination_tracker.validate_credentials(meta):
                    source_status["routing_error"] = f"Destination {destination} has no valid cookie session."
                    logger.info(f"{source}: [yellow]Not redirecting to {destination}: cookie validation failed.[/yellow]")
                    continue
            except Exception as exc:
                source_status["routing_error"] = f"Could not validate {destination} credentials: {exc}"
                logger.info(f"{source}: [yellow]Not redirecting to {destination}: credential validation failed.[/yellow]")
                continue

            trackers = [tracker for tracker in trackers if tracker != source]
            if destination not in trackers:
                trackers.append(destination)
            source_status.update({"upload": False, "skipped": True, "redirected_to": destination, "status_message": f"Redirected to {destination}: {decision.reason}"})
            destination_status = meta.tracker_status.setdefault(destination, {})
            destination_status.setdefault("redirected_from", []).append(source)
            logger.info(f"{source}: [green]Redirected to {destination}: {decision.reason}.[/green]")

        meta.trackers = trackers
