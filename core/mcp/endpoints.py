"""MCP endpoint + tool-name constants for the MyRealTrip public server.

Verified 2026-07-01: the endpoint is public (no auth) and answers JSON-RPC over
HTTP POST; ``GET`` returns 405 "POST only". Tool names below are the initial set
named in the plan (section 5.1). The authoritative list is whatever
``tools/list`` returns at runtime — treat these as convenience constants, not a
contract, until the validation step confirms them.
"""
from __future__ import annotations

DEFAULT_ENDPOINT = "https://mcp-servers.myrealtrip.com/mcp"

# MCP protocol revision advertised on initialize. Bump if the server rejects it.
PROTOCOL_VERSION = "2025-06-18"

# --- Tool names (confirmed via tools/list on 2026-07-01) ------------------
# Stays
TOOL_SEARCH_STAYS = "searchStays"
TOOL_GET_STAY_DETAIL = "getStayDetail"

# Flights
TOOL_SEARCH_DOMESTIC_FLIGHTS = "searchDomesticFlights"
TOOL_SEARCH_INTERNATIONAL_FLIGHTS = "searchInternationalFlights"
TOOL_FLIGHTS_FARE_CALENDAR = "flightsFareCalendar"
TOOL_GET_PROMOTION_AIRLINES = "getPromotionAirlines"

# Tours & Activities (TNA)
TOOL_GET_CATEGORY_LIST = "getCategoryList"
TOOL_SEARCH_TNAS = "searchTnas"
TOOL_GET_TNA_DETAIL = "getTnaDetail"
TOOL_GET_TNA_OPTIONS = "getTnaOptions"

# Utility
TOOL_GET_CURRENT_TIME = "getCurrentTime"

# Tools the flat sample sweep can call with self-contained arguments.
# (Detail tools are excluded because they need a gid/url from a prior search.)
SEARCH_TOOLS = {
    "flights": [
        TOOL_SEARCH_INTERNATIONAL_FLIGHTS,
        TOOL_SEARCH_DOMESTIC_FLIGHTS,
        TOOL_FLIGHTS_FARE_CALENDAR,
    ],
    "stays": [TOOL_SEARCH_STAYS],
    "tnas": [TOOL_GET_CATEGORY_LIST, TOOL_SEARCH_TNAS],
}

# Detail tools requiring identifiers harvested from a prior search result.
# ``needs`` documents which fields must be chained in from the search response.
CHAINED_TOOLS = {
    TOOL_GET_STAY_DETAIL: {"domain": "stays", "needs": ["gid", "checkIn", "checkOut"]},
    TOOL_GET_TNA_DETAIL: {"domain": "tnas", "needs": ["gid", "url"]},
    TOOL_GET_TNA_OPTIONS: {"domain": "tnas", "needs": ["gid", "url", "selectedDate"]},
}

# Back-compat alias for the flat sweep in core.cli.
DOMAIN_TOOLS = SEARCH_TOOLS
