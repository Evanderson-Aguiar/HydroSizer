"""Product editor for the HydroSizer-owned catalog."""

from typing import Any, Dict, Mapping, Optional

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class CatalogProductDialog(QDialog):
    """Collect product attributes while leaving validation to the domain layer."""

    def __init__(
        self,
        product: Optional[Mapping[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("HydroSizer catalog product"))
        self.resize(620, 580)
        self._lines: Dict[str, QLineEdit] = {}

        note = QLabel(
            self.tr(
                "Required fields are marked with *. Decimal comma or decimal point "
                "is accepted. Blank optional hydraulic values generate warnings. "
                "Project-specific material choices are configured outside the "
                "universal catalog."
            )
        )
        note.setWordWrap(True)

        content = QWidget()
        form = QFormLayout(content)
        for field, label in (
            ("material_code", self.tr("Material code *")),
            ("material_name_pt", self.tr("Material name (pt-BR) *")),
            ("material_name_en", self.tr("Material name (English) *")),
            ("product_code", self.tr("Product code *")),
            ("manufacturer", self.tr("Manufacturer")),
            ("standard", self.tr("Standard")),
            ("series", self.tr("Series / SDR / class")),
            ("nominal_diameter", self.tr("Nominal diameter *")),
        ):
            form.addRow(label + ":", self._line(field))

        self._nominal_unit = self._unit_combo(("mm", "m", "in"), allow_blank=False)
        form.addRow(self.tr("Nominal diameter unit *:"), self._nominal_unit)
        form.addRow(
            self.tr("Internal diameter *:"), self._line("internal_diameter")
        )
        self._internal_unit = self._unit_combo(("mm", "m", "in"), allow_blank=False)
        form.addRow(self.tr("Internal diameter unit *:"), self._internal_unit)

        for field, label in (
            ("pressure_class", self.tr("Pressure class")),
            ("max_allowable_pressure", self.tr("Maximum allowable pressure")),
        ):
            form.addRow(label + ":", self._line(field))
        self._pressure_unit = self._unit_combo(("mca", "kPa", "bar", "psi"))
        form.addRow(self.tr("Pressure unit:"), self._pressure_unit)

        form.addRow(
            self.tr("Hazen–Williams C:"), self._line("hazen_williams_c")
        )
        form.addRow(
            self.tr("Absolute roughness:"), self._line("absolute_roughness")
        )
        self._roughness_unit = self._unit_combo(("mm", "m", "in"))
        form.addRow(self.tr("Roughness unit:"), self._roughness_unit)
        form.addRow(
            self.tr("Cost per length:"), self._line("cost_per_length")
        )
        self._cost_unit = self._unit_combo(("per m", "per ft"))
        form.addRow(self.tr("Cost length unit:"), self._cost_unit)

        for field, label in (
            ("currency", self.tr("Currency code")),
            ("qgisred_material_value", self.tr("QGISRed material value")),
        ):
            form.addRow(label + ":", self._line(field))
        self._active = QCheckBox(self.tr("Product available for selection"))
        self._active.setChecked(True)
        form.addRow(self.tr("Active:"), self._active)
        self._notes = QPlainTextEdit()
        self._notes.setMaximumHeight(100)
        form.addRow(self.tr("Notes:"), self._notes)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)

        if product is not None:
            self.set_product(product)

    def values(self) -> Dict[str, Any]:
        """Return raw values for centralized normalization and validation."""
        values = {field: widget.text() for field, widget in self._lines.items()}
        values.update(
            {
                "nominal_diameter_unit": self._nominal_unit.currentData(),
                "internal_diameter_unit": self._internal_unit.currentData(),
                "pressure_unit": self._pressure_unit.currentData(),
                "roughness_unit": self._roughness_unit.currentData(),
                "cost_length_unit": self._cost_unit.currentData(),
                "active": self._active.isChecked(),
                "notes": self._notes.toPlainText(),
            }
        )
        return values

    def set_product(self, product: Mapping[str, Any]) -> None:
        for field, widget in self._lines.items():
            value = product.get(field)
            widget.setText("" if value is None else str(value))
        self._select_data(
            self._nominal_unit, product.get("nominal_diameter_unit", "mm")
        )
        self._select_data(
            self._internal_unit, product.get("internal_diameter_unit", "mm")
        )
        self._select_data(self._pressure_unit, product.get("pressure_unit", ""))
        self._select_data(self._roughness_unit, product.get("roughness_unit", ""))
        self._select_data(self._cost_unit, product.get("cost_length_unit", ""))
        self._active.setChecked(bool(product.get("active", True)))
        self._notes.setPlainText(product.get("notes") or "")

    def run(self) -> bool:
        """Execute modally across Qt 5 and Qt 6 bindings."""
        execute = getattr(self, "exec", None)
        result = execute() if callable(execute) else self.exec_()
        dialog_code = getattr(QDialog, "DialogCode", None)
        accepted = dialog_code.Accepted if dialog_code else QDialog.Accepted
        return result == accepted

    def _line(self, field: str) -> QLineEdit:
        widget = QLineEdit()
        self._lines[field] = widget
        return widget

    def _unit_combo(self, values, allow_blank: bool = True) -> QComboBox:
        combo = QComboBox()
        if allow_blank:
            combo.addItem(self.tr("Not defined"), "")
        display_values = {
            "per m": self.tr("per m"),
            "per ft": self.tr("per ft"),
        }
        for value in values:
            combo.addItem(display_values.get(value, value), value)
        return combo

    @staticmethod
    def _select_data(combo: QComboBox, value: Any) -> None:
        index = combo.findData(value or "")
        combo.setCurrentIndex(index if index >= 0 else 0)
