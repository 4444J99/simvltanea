"""Fixture generation commands. Import each command when its dependencies are needed.

Commands remain independently runnable with ``python -m``. Keeping this package
initializer lightweight lets non-image generators run without Pillow installed.
"""
__all__ = ["make_artifact_001", "make_audio_fixture", "make_runtime_fixture"]
