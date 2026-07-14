"""QGIS entry point for the HydroSizer plugin."""

__version__ = "1.0.1"


def classFactory(iface):  # noqa: N802 - required by the QGIS plugin API
    """Create the plugin instance requested by QGIS."""
    from .plugin import HydroSizerPlugin

    return HydroSizerPlugin(iface)
