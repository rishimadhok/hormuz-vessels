"""Opus 4.8 vision verification of CFAR candidates.

Each candidate chip is sent to Claude (`claude-opus-4-8`) and classified
vessel / island / rig / noise with a confidence and short rationale, using
structured outputs so the verdict is machine-readable. This is what makes the
final counts model-verified rather than threshold-only.

Phase 1 runs synchronously (few chips). The Message Batches API (50% cost) is
the Phase-2 swap for the full date range — see NOTES.md.
"""

from __future__ import annotations

import os
from typing import Literal

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

from .blobs import Candidate
from .chips import chip_base64
from .config import Settings
from .fetch import Window

load_dotenv()  # pick up ANTHROPIC_API_KEY from a .env if present

VesselLabel = Literal["vessel", "island", "rig", "noise"]

_SYSTEM = (
    "You are a SAR (synthetic aperture radar) imagery analyst verifying ship "
    "detections in the Strait of Hormuz. Each image is a single Sentinel-1 VH "
    "chip (~10 m/pixel) centred on a bright radar return flagged by a CFAR "
    "detector. Bright compact blobs on dark water are vessels. Reject false "
    "positives: static land/island returns, fixed oil/gas platforms (rigs), and "
    "speckle/wake/azimuth-ambiguity noise. Be skeptical — only call it a vessel "
    "when the return looks like a discrete ship-sized target on open water."
)

_PROMPT = (
    "Classify the central radar return in this chip as exactly one of: "
    "vessel, island, rig, noise. Consider the surroundings (open water vs land)."
)


class Verdict(BaseModel):
    label: VesselLabel
    confidence: float
    reasoning: str


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Export it (or put it in a .env file) "
            "before running the vision verification step."
        )
    return anthropic.Anthropic()


def verify_candidate(
    client: anthropic.Anthropic,
    window: Window,
    cand: Candidate,
    chip_amplitude,
    settings: Settings,
) -> Verdict:
    """Classify one candidate chip with Opus 4.8 vision (structured output)."""
    b64 = chip_base64(chip_amplitude)
    resp = client.messages.parse(
        model=settings.model,
        max_tokens=1024,
        system=_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
        output_format=Verdict,
    )
    verdict = resp.parsed_output
    if verdict is None:  # refusal or parse failure -> treat as noise, don't crash
        return Verdict(label="noise", confidence=0.0, reasoning="no structured output")
    return verdict
