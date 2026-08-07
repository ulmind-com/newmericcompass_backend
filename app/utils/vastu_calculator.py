"""Compass math for the Newmeric Compass 32-pada (N5) system.

Thin wrappers over :mod:`app.domain.padas` kept here for backwards-compatible
imports elsewhere in the codebase.
"""

from app.domain.padas import pada_for_degree


def get_pada(degree: float) -> dict:
    """Return the pada dict for a compass bearing (degrees clockwise from North)."""
    return pada_for_degree(degree)


def get_direction16(degree: float) -> str:
    """Return the 16-wind direction code (e.g. ``"NW"``) for a bearing."""
    return pada_for_degree(degree)["direction16"]


def get_pada_code(degree: float) -> str:
    """Return the pada code (e.g. ``"N5"``) for a bearing."""
    return pada_for_degree(degree)["code"]
