"""Qt translator backed by the bundled HydroSizer pt-BR message catalog."""

from qgis.PyQt.QtCore import QTranslator

from .text import translate_ui_text


class HydroSizerPortugueseTranslator(QTranslator):
    """Translate HydroSizer source messages without external Qt build tools."""

    def translate(
        self,
        context: str,
        source_text: str,
        disambiguation: str = None,
        n: int = -1,
    ) -> str:
        del context, disambiguation, n
        return translate_ui_text(source_text)
