"""Qt translator backed by the bundled HydroSizer pt-BR message catalog."""

from typing import Optional

from qgis.PyQt.QtCore import QTranslator

from .text import registered_ui_translation


_HYDROSIZER_CONTEXTS = frozenset(
    {
        "HydroSizerPlugin",
        "HydroSizerDialog",
        "CatalogProductDialog",
    }
)


class HydroSizerPortugueseTranslator(QTranslator):
    """Translate HydroSizer source messages without external Qt build tools."""

    def translate(
        self,
        context: str,
        source_text: str,
        disambiguation: str = None,
        n: int = -1,
    ) -> Optional[str]:
        del disambiguation, n
        if context not in _HYDROSIZER_CONTEXTS:
            return None
        return registered_ui_translation(source_text)
