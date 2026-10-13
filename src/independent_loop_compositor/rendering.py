"""Render independent-loop states using the existing FFmpeg implementation."""
from simvltanea.rendering import Panel, Placement, Segment, Settings, probe_audio_channels
from simvltanea.rendering import render_triptych as _implementation

render = _implementation.render

__all__ = ["Panel", "Placement", "Segment", "Settings", "probe_audio_channels", "render"]
