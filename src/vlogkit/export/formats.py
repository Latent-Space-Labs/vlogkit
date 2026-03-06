"""Export OTIO timeline to various NLE formats."""

from __future__ import annotations

from pathlib import Path

import opentimelineio as otio

FORMAT_EXTENSIONS = {
    "fcpxml": ".fcpxml",
    "edl": ".edl",
    "premiere": ".xml",
    "otio": ".otio",
}

FORMAT_ADAPTERS = {
    "fcpxml": "fcp_xml",
    "edl": "cmx_3600",
    "premiere": "fcp_xml",  # Premiere reads FCPXML
    "otio": "otio_json",
}


def export_timeline(
    timeline: otio.schema.Timeline,
    output_path: Path,
    fmt: str = "fcpxml",
) -> Path:
    ext = FORMAT_EXTENSIONS.get(fmt, ".fcpxml")
    adapter = FORMAT_ADAPTERS.get(fmt, "fcp_xml")

    if not output_path.suffix:
        output_path = output_path.with_suffix(ext)

    otio.adapters.write_to_file(timeline, str(output_path), adapter_name=adapter)
    return output_path
