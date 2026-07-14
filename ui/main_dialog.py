"""Localized, workflow-oriented HydroSizer interface."""

from typing import Any, Dict, Mapping, Optional, Sequence

from qgis.PyQt.QtCore import QSize, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..integrations.layer_mapping import compatible_fields, mapping_display_name
from ..integrations.endpoint_pressure_mapping import endpoint_fields


class _CollapsibleSection(QWidget):
    """Present one ordered workflow activity without adding nested tabs."""

    def __init__(
        self,
        title: str,
        content: QWidget,
        expanded: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HydroSizerWorkflowSection")
        self._content = content
        self._header = QToolButton()
        self._header.setObjectName("HydroSizerWorkflowSectionHeader")
        self._header.setText(title)
        self._header.setCheckable(True)
        self._header.setChecked(expanded)
        self._header.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._header.setStyleSheet(
            "QToolButton { text-align: left; padding: 7px; font-weight: bold; }"
        )
        self._header.toggled.connect(self._set_expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)
        layout.addWidget(self._header)
        layout.addWidget(self._content)
        self._set_expanded(expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self._header.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._content.setVisible(expanded)


class HydroSizerDialog(QDialog):
    """Display the five-step project workflow using translatable source text."""

    diagnostic_requested = pyqtSignal()
    export_requested = pyqtSignal()
    qgisred_detection_requested = pyqtSignal()
    options_browse_requested = pyqtSignal()
    mapping_refresh_requested = pyqtSignal()
    mapping_save_requested = pyqtSignal()
    mapping_changed = pyqtSignal()
    validation_requested = pyqtSignal()
    pipe_highlight_requested = pyqtSignal()
    result_highlight_requested = pyqtSignal()
    basic_calculation_requested = pyqtSignal()
    catalog_refresh_requested = pyqtSignal()
    catalog_add_requested = pyqtSignal()
    catalog_edit_requested = pyqtSignal()
    catalog_duplicate_requested = pyqtSignal()
    catalog_toggle_active_requested = pyqtSignal()
    catalog_delete_requested = pyqtSignal()
    catalog_import_requested = pyqtSignal()
    catalog_export_requested = pyqtSignal()
    catalog_validate_requested = pyqtSignal()
    hazen_williams_requested = pyqtSignal()
    darcy_weisbach_requested = pyqtSignal()
    sizing_criteria_changed = pyqtSignal()
    endpoint_refresh_requested = pyqtSignal()
    endpoint_evaluate_requested = pyqtSignal()
    endpoint_highlight_pipe_requested = pyqtSignal()
    endpoint_highlight_nodes_requested = pyqtSignal()
    batch_sizing_requested = pyqtSignal()
    preview_filter_requested = pyqtSignal()
    preview_include_requested = pyqtSignal(bool)
    preview_map_selection_requested = pyqtSignal()
    preview_export_requested = pyqtSignal()
    apply_configuration_changed = pyqtSignal()
    apply_audit_browse_requested = pyqtSignal()
    apply_plan_requested = pyqtSignal()
    apply_execute_requested = pyqtSignal()
    report_export_requested = pyqtSignal()

    def __init__(self, version: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("HydroSizerDialog")
        self.setWindowTitle(self.tr("HydroSizer — Hydraulic Pipe Sizing"))
        self.resize(960, 580)
        self.setMinimumSize(760, 500)

        title = QLabel("HydroSizer")
        title.setObjectName("HydroSizerTitle")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")

        description = QLabel(
            self.tr(
                "Follow the five project steps from data connection to final "
                "documentation. Open Advanced tools only for diagnostics or "
                "single-pipe checks."
            )
        )
        description.setWordWrap(True)
        version_label = QLabel(
            self.tr("Version: {version}").format(version=version)
        )

        self._mapping_inventory = []
        self._mapping_suggestions: Dict[str, str] = {}

        self._workflow_step_names = (
            self.tr("Project"),
            self.tr("Criteria"),
            self.tr("Sizing"),
            self.tr("Apply"),
            self.tr("Documents"),
        )
        self._workflow_step_descriptions = (
            self.tr(
                "Detect the hydraulic scenario, map project data, and validate "
                "the records used by HydroSizer."
            ),
            self.tr(
                "Review the product catalog, hydraulic limits, selection rules, "
                "and endpoint-pressure settings."
            ),
            self.tr(
                "Run pipe sizing in memory, inspect every result, and choose the "
                "rows that belong to the design."
            ),
            self.tr(
                "Optionally prepare and confirm audited changes to existing pipe "
                "attributes."
            ),
            self.tr(
                "Identify the project and export the reviewed calculation memory "
                "and detailed spreadsheet."
            ),
        )

        project_page = self._build_workflow_page(
            (
                (
                    self.tr("1. Detect Hydraulic Scenario"),
                    self._build_qgisred_page(),
                    True,
                ),
                (
                    self.tr("2. Map Layers and Fields"),
                    self._build_mapping_page(),
                    False,
                ),
                (
                    self.tr("3. Validate Input Data"),
                    self._build_validation_page(),
                    False,
                ),
            )
        )
        criteria_page = self._build_workflow_page(
            (
                (
                    self.tr("1. Product Catalog"),
                    self._build_catalog_page(),
                    True,
                ),
                (
                    self.tr("2. Hydraulic and Selection Criteria"),
                    self._build_combined_sizing_page(),
                    False,
                ),
                (
                    self.tr("3. Automatic Pressure Check"),
                    self._build_endpoint_pressure_page(),
                    False,
                ),
            )
        )
        sizing_page = self._build_workflow_page(
            (
                (
                    self.tr("1. Run Sizing"),
                    self._build_batch_sizing_page(),
                    True,
                ),
                (
                    self.tr("2. Review and Include Results"),
                    self._build_preview_page(),
                    False,
                ),
            )
        )
        apply_page = self._build_workflow_page(
            (
                (
                    self.tr("Review and Apply Changes"),
                    self._build_safe_apply_page(),
                    True,
                ),
            )
        )
        documents_page = self._build_workflow_page(
            (
                (
                    self.tr("Project Calculation Memory"),
                    self._build_reports_page(),
                    True,
                ),
            )
        )

        self._workflow_tabs = QTabWidget()
        self._workflow_tabs.setObjectName("HydroSizerWorkflowTabs")
        self._workflow_tabs.setDocumentMode(True)
        self._workflow_tabs.setIconSize(QSize(22, 22))
        self._workflow_tabs.setElideMode(Qt.ElideRight)
        self._workflow_tabs.setUsesScrollButtons(False)
        self._workflow_tabs.tabBar().setExpanding(True)
        tab_specs = (
            (project_page, QStyle.SP_DirOpenIcon),
            (criteria_page, QStyle.SP_FileDialogDetailedView),
            (sizing_page, QStyle.SP_ArrowForward),
            (apply_page, QStyle.SP_DialogApplyButton),
            (documents_page, QStyle.SP_FileIcon),
        )
        for index, (page, icon_type) in enumerate(tab_specs):
            self._workflow_tabs.addTab(
                page,
                self.style().standardIcon(icon_type),
                self.tr("{number}. {name}").format(
                    number=index + 1,
                    name=self._workflow_step_names[index],
                ),
            )
            self._workflow_tabs.setTabToolTip(
                index, self._workflow_step_descriptions[index]
            )

        self._advanced_dialog = self._build_advanced_dialog()
        self._workflow_context = QLabel()
        self._workflow_context.setObjectName("HydroSizerWorkflowContext")
        self._workflow_context.setWordWrap(True)
        self._workflow_context.setStyleSheet(
            "QLabel { background: palette(alternate-base); border: 1px solid "
            "palette(mid); border-radius: 3px; padding: 7px; }"
        )

        self._previous_button = QPushButton(self.tr("Previous"))
        self._previous_button.setObjectName("HydroSizerPreviousStepButton")
        self._previous_button.clicked.connect(self._go_to_previous_step)
        self._next_button = QPushButton()
        self._next_button.setObjectName("HydroSizerNextStepButton")
        self._next_button.clicked.connect(self._go_to_next_step)
        advanced_button = QPushButton(self.tr("Advanced Tools…"))
        advanced_button.setObjectName("HydroSizerAdvancedToolsButton")
        advanced_button.clicked.connect(self._show_advanced_tools)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.addButton(advanced_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(
            self._previous_button, QDialogButtonBox.ButtonRole.ActionRole
        )
        buttons.addButton(self._next_button, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)

        self._workflow_tabs.currentChanged.connect(
            self._update_workflow_navigation
        )

        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(version_label)
        layout.addLayout(heading)
        layout.addWidget(description)
        layout.addWidget(self._workflow_context)
        layout.addWidget(self._workflow_tabs, 1)
        layout.addWidget(buttons)
        self._workflow_tabs.setCurrentIndex(0)
        self._update_workflow_navigation(0)

    def _build_workflow_page(
        self,
        sections: Sequence[tuple[str, QWidget, bool]],
    ) -> QWidget:
        """Build one scrollable main step from ordered collapsible activities."""
        content = QWidget()
        content.setObjectName("HydroSizerWorkflowPageContent")
        content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(3, 3, 3, 3)
        content_layout.setSpacing(5)
        for title, widget, expanded in sections:
            widget.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            section = _CollapsibleSection(title, widget, expanded, content)
            section.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            content_layout.addWidget(section)
        content_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setObjectName("HydroSizerWorkflowScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(content)

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        return page

    def _build_advanced_dialog(self) -> QDialog:
        """Keep diagnostic and single-pipe calculators outside the main flow."""
        dialog = QDialog(self)
        dialog.setObjectName("HydroSizerAdvancedToolsDialog")
        dialog.setWindowTitle(self.tr("HydroSizer — Advanced Tools"))
        dialog.resize(900, 560)
        dialog.setMinimumSize(720, 480)

        hint = QLabel(
            self.tr(
                "These optional tools support diagnostics and individual checks. "
                "They are not required for the normal project workflow."
            )
        )
        hint.setWordWrap(True)
        tabs = QTabWidget()
        tabs.setObjectName("HydroSizerAdvancedToolsTabs")
        tabs.setDocumentMode(True)
        tabs.setElideMode(Qt.ElideRight)
        tabs.setUsesScrollButtons(False)
        tabs.tabBar().setExpanding(True)
        tabs.addTab(self._build_environment_page(), self.tr("Environment Diagnostic"))
        tabs.addTab(self._build_basic_calculation_page(), self.tr("Unit Calculator"))
        tabs.addTab(self._build_hazen_williams_page(), self.tr("Hazen–Williams Check"))
        tabs.addTab(self._build_darcy_weisbach_page(), self.tr("Darcy–Weisbach Check"))
        tabs.addTab(
            self._build_endpoint_pressure_check_page(),
            self.tr("Pipe Pressure Check"),
        )

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.hide)
        layout = QVBoxLayout(dialog)
        layout.addWidget(hint)
        layout.addWidget(tabs, 1)
        layout.addWidget(buttons)
        return dialog

    def _update_workflow_navigation(self, index: int) -> None:
        """Update orientation and navigation controls for the active main step."""
        if not 0 <= index < len(self._workflow_step_names):
            return
        self._workflow_context.setText(
            self.tr("Step {current} of {total}: {name}\n{description}").format(
                current=index + 1,
                total=len(self._workflow_step_names),
                name=self._workflow_step_names[index],
                description=self._workflow_step_descriptions[index],
            )
        )
        self._previous_button.setEnabled(index > 0)
        has_next = index + 1 < self._workflow_tabs.count()
        self._next_button.setEnabled(has_next)
        if has_next:
            self._next_button.setText(
                self.tr("Next: {step}").format(
                    step=self._workflow_step_names[index + 1]
                )
            )
        else:
            self._next_button.setText(self.tr("End of Workflow"))

    def _go_to_previous_step(self) -> None:
        self._workflow_tabs.setCurrentIndex(
            max(0, self._workflow_tabs.currentIndex() - 1)
        )

    def _go_to_next_step(self) -> None:
        self._workflow_tabs.setCurrentIndex(
            min(
                self._workflow_tabs.count() - 1,
                self._workflow_tabs.currentIndex() + 1,
            )
        )

    def _show_advanced_tools(self) -> None:
        self._advanced_dialog.show()
        self._advanced_dialog.raise_()
        self._advanced_dialog.activateWindow()

    def _build_environment_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Lists the current project, loaded layers, sanitized sources, "
                "providers, layer types, CRS information, and field definitions."
            )
        )
        hint.setWordWrap(True)

        action_layout = QHBoxLayout()
        diagnostic_button = QPushButton(self.tr("Inspect current project"))
        diagnostic_button.clicked.connect(self.diagnostic_requested.emit)
        self._export_button = QPushButton(self.tr("Export JSON…"))
        self._export_button.setEnabled(False)
        self._export_button.clicked.connect(self.export_requested.emit)
        action_layout.addWidget(diagnostic_button)
        action_layout.addWidget(self._export_button)

        self._diagnostic_status = QLabel(
            self.tr("Environment diagnostic not run.")
        )
        self._diagnostic_status.setWordWrap(True)
        self._diagnostic_output = QPlainTextEdit()
        self._diagnostic_output.setObjectName("EnvironmentDiagnosticOutput")
        self._diagnostic_output.setReadOnly(True)
        self._diagnostic_output.setPlaceholderText(
            self.tr(
                "Click “Inspect current project” to list project and layer metadata."
            )
        )

        layout.addWidget(hint)
        layout.addLayout(action_layout)
        layout.addWidget(self._diagnostic_status)
        layout.addWidget(self._diagnostic_output, 1)
        return page

    def _build_qgisred_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Searches the project and local layer directories for "
                "*_Options.dbf, then opens the selected table through QGIS/OGR "
                "for read-only inspection."
            )
        )
        hint.setWordWrap(True)

        action_layout = QHBoxLayout()
        detect_button = QPushButton(self.tr("Detect from current project"))
        detect_button.clicked.connect(self.qgisred_detection_requested.emit)
        browse_button = QPushButton(self.tr("Choose Options DBF…"))
        browse_button.clicked.connect(self.options_browse_requested.emit)
        action_layout.addWidget(detect_button)
        action_layout.addWidget(browse_button)

        self._qgisred_status = QLabel(self.tr("QGISRed detection not run."))
        self._qgisred_status.setWordWrap(True)
        self._detection_output = QPlainTextEdit()
        self._detection_output.setReadOnly(True)
        self._detection_output.setMaximumHeight(130)
        self._detection_output.setPlaceholderText(
            self.tr("Detection scope and candidate files will appear here.")
        )

        self._options_output = QPlainTextEdit()
        self._options_output.setObjectName("QgisRedOptionsOutput")
        self._options_output.setReadOnly(True)
        self._options_output.setPlaceholderText(
            self.tr("DBF fields, records, and detected settings will appear here.")
        )

        manual_group = QGroupBox(self.tr("Review or correct detected settings"))
        manual_layout = QFormLayout(manual_group)
        self._flow_unit_combo = QComboBox()
        for label, code in (
            (self.tr("Not selected"), ""),
            ("L/s (LPS)", "LPS"),
            ("m³/s (CMS)", "CMS"),
            ("m³/h (CMH)", "CMH"),
            ("US gal/min (GPM)", "GPM"),
            ("ft³/s (CFS)", "CFS"),
        ):
            self._flow_unit_combo.addItem(label, code)
        self._headloss_combo = QComboBox()
        for label, code in (
            (self.tr("Not selected"), ""),
            (self.tr("Hazen–Williams (H-W)"), "H-W"),
            (self.tr("Darcy–Weisbach (D-W)"), "D-W"),
        ):
            self._headloss_combo.addItem(label, code)
        manual_layout.addRow(self.tr("Flow unit:"), self._flow_unit_combo)
        manual_layout.addRow(self.tr("Headloss method:"), self._headloss_combo)
        manual_note = QLabel(
            self.tr(
                "These selections are temporary and are not used for sizing in "
                "this stage. They demonstrate the required manual fallback."
            )
        )
        manual_note.setWordWrap(True)
        manual_layout.addRow(manual_note)

        layout.addWidget(hint)
        layout.addLayout(action_layout)
        layout.addWidget(self._qgisred_status)
        layout.addWidget(self._detection_output)
        layout.addWidget(self._options_output, 1)
        layout.addWidget(manual_group)
        return page

    def _build_mapping_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Select the pipe layer, result layer, matching ID fields, flow "
                "field, and attribute-based pipe length. Only compatible fields "
                "are listed. Features are not read in this stage."
            )
        )
        hint.setWordWrap(True)

        refresh_button = QPushButton(self.tr("Refresh project layers"))
        refresh_button.clicked.connect(self.mapping_refresh_requested.emit)

        mapping_group = QGroupBox(self.tr("Temporary layer and field mapping"))
        form = QFormLayout(mapping_group)
        self._pipe_layer_combo = QComboBox()
        self._pipe_id_combo = QComboBox()
        self._length_combo = QComboBox()
        self._result_layer_combo = QComboBox()
        self._result_id_combo = QComboBox()
        self._flow_combo = QComboBox()
        form.addRow(self.tr("Pipe layer:"), self._pipe_layer_combo)
        form.addRow(self.tr("Pipe ID field:"), self._pipe_id_combo)
        form.addRow(self.tr("Pipe length field:"), self._length_combo)
        form.addRow(self.tr("Result layer/table:"), self._result_layer_combo)
        form.addRow(self.tr("Result ID field:"), self._result_id_combo)
        form.addRow(self.tr("Flow field:"), self._flow_combo)

        self._pipe_layer_combo.currentIndexChanged.connect(
            self._on_pipe_layer_changed
        )
        self._pipe_id_combo.currentIndexChanged.connect(
            self._on_pipe_id_changed
        )
        self._result_layer_combo.currentIndexChanged.connect(
            self._on_result_layer_changed
        )
        for combo in (
            self._pipe_layer_combo,
            self._pipe_id_combo,
            self._length_combo,
            self._result_layer_combo,
            self._result_id_combo,
            self._flow_combo,
        ):
            combo.currentIndexChanged.connect(self._mark_mapping_changed)

        store_button = QPushButton(self.tr("Store temporary mapping"))
        store_button.clicked.connect(self.mapping_save_requested.emit)
        self._mapping_status = QLabel(self.tr("Layer inventory not loaded."))
        self._mapping_status.setWordWrap(True)
        self._mapping_summary = QPlainTextEdit()
        self._mapping_summary.setReadOnly(True)
        self._mapping_summary.setMaximumHeight(150)
        self._mapping_summary.setPlaceholderText(
            self.tr("The in-memory mapping summary will appear here.")
        )
        safety_notice = QLabel(
            self.tr(
                "Length will later be read only from the selected attribute. "
                "Geometry length is not used. No layer is edited in this stage."
            )
        )
        safety_notice.setWordWrap(True)
        safety_notice.setStyleSheet("color: #666666;")

        layout.addWidget(hint)
        layout.addWidget(refresh_button)
        layout.addWidget(mapping_group)
        layout.addWidget(store_button)
        layout.addWidget(self._mapping_status)
        layout.addWidget(self._mapping_summary)
        layout.addWidget(safety_notice)
        layout.addStretch(1)
        return page

    def _build_validation_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Validates all mapped records for null or duplicate IDs, missing "
                "matches, invalid flow, and invalid attribute length. The reader "
                "requests no geometry and never starts editing."
            )
        )
        hint.setWordWrap(True)

        validate_button = QPushButton(self.tr("Validate stored mapping"))
        validate_button.clicked.connect(self.validation_requested.emit)

        highlight_layout = QHBoxLayout()
        self._pipe_highlight_button = QPushButton(
            self.tr("Select/zoom problem pipes")
        )
        self._pipe_highlight_button.setEnabled(False)
        self._pipe_highlight_button.clicked.connect(
            self.pipe_highlight_requested.emit
        )
        self._result_highlight_button = QPushButton(
            self.tr("Select/zoom problem results")
        )
        self._result_highlight_button.setEnabled(False)
        self._result_highlight_button.clicked.connect(
            self.result_highlight_requested.emit
        )
        highlight_layout.addWidget(self._pipe_highlight_button)
        highlight_layout.addWidget(self._result_highlight_button)

        self._validation_status = QLabel(
            self.tr("Store a complete mapping before validation.")
        )
        self._validation_status.setWordWrap(True)
        self._validation_output = QPlainTextEdit()
        self._validation_output.setObjectName("DataValidationOutput")
        self._validation_output.setReadOnly(True)
        self._validation_output.setPlaceholderText(
            self.tr("The read-only validation report will appear here.")
        )
        selection_notice = QLabel(
            self.tr(
                "Highlight buttons change only the current QGIS selection. They "
                "do not change attributes or save edits."
            )
        )
        selection_notice.setWordWrap(True)
        selection_notice.setStyleSheet("color: #666666;")

        layout.addWidget(hint)
        layout.addWidget(validate_button)
        layout.addLayout(highlight_layout)
        layout.addWidget(self._validation_status)
        layout.addWidget(self._validation_output, 1)
        layout.addWidget(selection_notice)
        return page

    def _build_basic_calculation_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Demonstrates central unit conversion, mean velocity, and segment "
                "cost for manually entered values. No project layer is accessed."
            )
        )
        hint.setWordWrap(True)

        input_group = QGroupBox(self.tr("Demonstration inputs"))
        form = QFormLayout(input_group)
        self._demo_flow_value = self._numeric_input(-1.0e9, 1.0e9, 10.0)
        self._demo_flow_unit = QComboBox()
        for label, code in (
            ("L/s (LPS)", "LPS"),
            ("m³/s (CMS)", "CMS"),
            ("m³/h (CMH)", "CMH"),
            ("US gal/min (GPM)", "GPM"),
            ("ft³/s (CFS)", "CFS"),
        ):
            self._demo_flow_unit.addItem(label, code)

        self._demo_diameter_value = self._numeric_input(0.0, 1.0e9, 100.0)
        self._demo_diameter_unit = QComboBox()
        for label, code in (("mm", "mm"), ("m", "m"), ("in", "in")):
            self._demo_diameter_unit.addItem(label, code)

        self._demo_length_value = self._numeric_input(0.0, 1.0e12, 1000.0)
        self._demo_length_unit = QComboBox()
        for label, code in (("m", "m"), ("km", "km"), ("ft", "ft")):
            self._demo_length_unit.addItem(label, code)

        self._demo_cost_value = self._numeric_input(0.0, 1.0e12, 50.0)
        self._demo_cost_unit = QComboBox()
        self._demo_cost_unit.addItem(self.tr("currency per m"), "per m")
        self._demo_cost_unit.addItem(self.tr("currency per ft"), "per ft")

        form.addRow(self.tr("Flow value:"), self._demo_flow_value)
        form.addRow(self.tr("Flow unit:"), self._demo_flow_unit)
        form.addRow(self.tr("Internal diameter:"), self._demo_diameter_value)
        form.addRow(self.tr("Diameter unit:"), self._demo_diameter_unit)
        form.addRow(self.tr("Segment length:"), self._demo_length_value)
        form.addRow(self.tr("Length unit:"), self._demo_length_unit)
        form.addRow(self.tr("Unit cost:"), self._demo_cost_value)
        form.addRow(self.tr("Cost basis:"), self._demo_cost_unit)

        calculate_button = QPushButton(self.tr("Calculate demonstration"))
        calculate_button.clicked.connect(self.basic_calculation_requested.emit)
        self._basic_calculation_status = QLabel(
            self.tr("Demonstration not calculated.")
        )
        self._basic_calculation_status.setWordWrap(True)
        self._basic_calculation_output = QPlainTextEdit()
        self._basic_calculation_output.setReadOnly(True)
        self._basic_calculation_output.setObjectName("BasicCalculationOutput")

        supported_units = QLabel(
            self.tr(
                "Central registry also supports pressure: mca, kPa, bar, psi; "
                "headloss gradient: m/m, m/km, ft/100 ft, ft/1000 ft."
            )
        )
        supported_units.setWordWrap(True)
        supported_units.setStyleSheet("color: #666666;")

        layout.addWidget(hint)
        layout.addWidget(input_group)
        layout.addWidget(calculate_button)
        layout.addWidget(self._basic_calculation_status)
        layout.addWidget(self._basic_calculation_output, 1)
        layout.addWidget(supported_units)
        return page

    def _build_catalog_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "This is a universal HydroSizer product catalog, stored separately "
                "from QGISRed. Active means generally available; restrict materials "
                "for one project in the Criteria step instead of deactivating them."
            )
        )
        hint.setWordWrap(True)

        filter_layout = QHBoxLayout()
        self._catalog_search = QLineEdit()
        self._catalog_search.setPlaceholderText(
            self.tr("Search material, product, name, or manufacturer")
        )
        self._catalog_active_only = QCheckBox(self.tr("Active products only"))
        refresh_button = QPushButton(self.tr("Refresh / search"))
        refresh_button.clicked.connect(self.catalog_refresh_requested.emit)
        self._catalog_search.returnPressed.connect(
            self.catalog_refresh_requested.emit
        )
        filter_layout.addWidget(self._catalog_search, 1)
        filter_layout.addWidget(self._catalog_active_only)
        filter_layout.addWidget(refresh_button)

        self._catalog_table = QTableWidget()
        self._catalog_table.setColumnCount(11)
        self._catalog_table.setHorizontalHeaderLabels(
            [
                self.tr("ID"),
                self.tr("Active"),
                self.tr("Material"),
                self.tr("Name (pt-BR)"),
                self.tr("Product"),
                "DN",
                self.tr("Internal D"),
                self.tr("Pressure"),
                "H-W C",
                self.tr("Roughness"),
                self.tr("Cost"),
            ]
        )
        edit_trigger = getattr(QAbstractItemView, "EditTrigger", None)
        selection_behavior = getattr(QAbstractItemView, "SelectionBehavior", None)
        selection_mode = getattr(QAbstractItemView, "SelectionMode", None)
        self._catalog_table.setEditTriggers(
            edit_trigger.NoEditTriggers
            if edit_trigger
            else QAbstractItemView.NoEditTriggers
        )
        self._catalog_table.setSelectionBehavior(
            selection_behavior.SelectRows
            if selection_behavior
            else QAbstractItemView.SelectRows
        )
        self._catalog_table.setSelectionMode(
            selection_mode.SingleSelection
            if selection_mode
            else QAbstractItemView.SingleSelection
        )
        self._catalog_table.setSortingEnabled(True)
        self._catalog_table.cellDoubleClicked.connect(
            lambda _row, _column: self.catalog_edit_requested.emit()
        )

        primary_actions = QHBoxLayout()
        for label, signal in (
            (self.tr("Add"), self.catalog_add_requested),
            (self.tr("Edit"), self.catalog_edit_requested),
            (self.tr("Duplicate"), self.catalog_duplicate_requested),
            (self.tr("Activate / deactivate"), self.catalog_toggle_active_requested),
        ):
            button = QPushButton(label)
            button.clicked.connect(signal.emit)
            primary_actions.addWidget(button)
        primary_actions.addStretch(1)
        delete_button = QPushButton(self.tr("Delete"))
        delete_button.clicked.connect(self.catalog_delete_requested.emit)
        primary_actions.addWidget(delete_button)

        interchange_actions = QHBoxLayout()
        for label, signal in (
            (self.tr("Import CSV…"), self.catalog_import_requested),
            (self.tr("Export CSV…"), self.catalog_export_requested),
            (self.tr("Validate catalog"), self.catalog_validate_requested),
        ):
            button = QPushButton(label)
            button.clicked.connect(signal.emit)
            interchange_actions.addWidget(button)

        self._catalog_status = QLabel(self.tr("Catalog not initialized."))
        self._catalog_status.setWordWrap(True)
        self._catalog_report = QPlainTextEdit()
        self._catalog_report.setReadOnly(True)
        self._catalog_report.setMaximumHeight(145)
        self._catalog_report.setPlaceholderText(
            self.tr("Catalog validation and operation details will appear here.")
        )

        layout.addWidget(hint)
        layout.addLayout(filter_layout)
        layout.addWidget(self._catalog_table, 1)
        layout.addLayout(primary_actions)
        layout.addLayout(interchange_actions)
        layout.addWidget(self._catalog_status)
        layout.addWidget(self._catalog_report)
        return page

    def _build_hazen_williams_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Evaluates every active, hydraulically complete catalog product "
                "for one manually entered segment. Only maximum unit headloss "
                "determines admissibility; velocity and cost are informative."
            )
        )
        hint.setWordWrap(True)

        input_group = QGroupBox(self.tr("Single-segment inputs"))
        form = QFormLayout(input_group)
        self._hw_flow_value = self._numeric_input(-1.0e9, 1.0e9, 10.0)
        self._hw_flow_unit = QComboBox()
        for label, code in (
            ("L/s (LPS)", "LPS"),
            ("m³/s (CMS)", "CMS"),
            ("m³/h (CMH)", "CMH"),
            ("US gal/min (GPM)", "GPM"),
            ("ft³/s (CFS)", "CFS"),
        ):
            self._hw_flow_unit.addItem(label, code)
        self._hw_length_value = self._numeric_input(0.0, 1.0e12, 1000.0)
        self._hw_length_unit = QComboBox()
        for label, code in (("m", "m"), ("km", "km"), ("ft", "ft")):
            self._hw_length_unit.addItem(label, code)
        self._hw_gradient_value = self._numeric_input(0.0, 1.0e9, 30.0)
        self._hw_gradient_unit = QComboBox()
        for label, code in (
            ("m/km", "m/km"),
            ("m/m", "m/m"),
            ("ft/100 ft", "ft/100 ft"),
            ("ft/1000 ft", "ft/1000 ft"),
        ):
            self._hw_gradient_unit.addItem(label, code)
        form.addRow(self.tr("Flow:"), self._hw_flow_value)
        form.addRow(self.tr("Flow unit:"), self._hw_flow_unit)
        form.addRow(self.tr("Segment length:"), self._hw_length_value)
        form.addRow(self.tr("Length unit:"), self._hw_length_unit)
        form.addRow(self.tr("Maximum unit headloss:"), self._hw_gradient_value)
        form.addRow(self.tr("Gradient unit:"), self._hw_gradient_unit)

        calculate_button = QPushButton(
            self.tr("Evaluate active catalog products")
        )
        calculate_button.clicked.connect(self.hazen_williams_requested.emit)
        self._hw_status = QLabel(
            self.tr("Hazen–Williams demonstration not calculated.")
        )
        self._hw_status.setWordWrap(True)
        self._hw_output = QPlainTextEdit()
        self._hw_output.setObjectName("HazenWilliamsOutput")
        self._hw_output.setReadOnly(True)
        notice = QLabel(
            self.tr(
                "This demonstration does not inspect or edit project layers. "
                "Inactive and incomplete products are not eligible for selection."
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #666666;")

        layout.addWidget(hint)
        layout.addWidget(input_group)
        layout.addWidget(calculate_button)
        layout.addWidget(self._hw_status)
        layout.addWidget(self._hw_output, 1)
        layout.addWidget(notice)
        return page

    def _build_darcy_weisbach_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Evaluates active catalog products using their absolute "
                "roughness. Reynolds number, flow regime, relative roughness, "
                "friction factor, velocity, and losses are reported."
            )
        )
        hint.setWordWrap(True)

        input_group = QGroupBox(self.tr("Single-segment inputs"))
        form = QFormLayout(input_group)
        self._dw_flow_value = self._numeric_input(-1.0e9, 1.0e9, 10.0)
        self._dw_flow_unit = QComboBox()
        for label, code in (
            ("L/s (LPS)", "LPS"),
            ("m³/s (CMS)", "CMS"),
            ("m³/h (CMH)", "CMH"),
            ("US gal/min (GPM)", "GPM"),
            ("ft³/s (CFS)", "CFS"),
        ):
            self._dw_flow_unit.addItem(label, code)
        self._dw_length_value = self._numeric_input(0.0, 1.0e12, 1000.0)
        self._dw_length_unit = QComboBox()
        for label, code in (("m", "m"), ("km", "km"), ("ft", "ft")):
            self._dw_length_unit.addItem(label, code)
        self._dw_gradient_value = self._numeric_input(0.0, 1.0e9, 35.0)
        self._dw_gradient_unit = QComboBox()
        for label, code in (
            ("m/km", "m/km"),
            ("m/m", "m/m"),
            ("ft/100 ft", "ft/100 ft"),
            ("ft/1000 ft", "ft/1000 ft"),
        ):
            self._dw_gradient_unit.addItem(label, code)
        form.addRow(self.tr("Flow:"), self._dw_flow_value)
        form.addRow(self.tr("Flow unit:"), self._dw_flow_unit)
        form.addRow(self.tr("Segment length:"), self._dw_length_value)
        form.addRow(self.tr("Length unit:"), self._dw_length_unit)
        form.addRow(self.tr("Maximum unit headloss:"), self._dw_gradient_value)
        form.addRow(self.tr("Gradient unit:"), self._dw_gradient_unit)

        advanced_group = QGroupBox(self.tr("Advanced fluid property"))
        advanced_form = QFormLayout(advanced_group)
        self._dw_viscosity_value = QDoubleSpinBox()
        self._dw_viscosity_value.setDecimals(12)
        self._dw_viscosity_value.setRange(1.0e-12, 1.0e6)
        self._dw_viscosity_value.setValue(1.004)
        self._dw_viscosity_value.setKeyboardTracking(False)
        self._dw_viscosity_unit = QComboBox()
        self._dw_viscosity_unit.addItem("mm²/s (cSt)", "mm²/s")
        self._dw_viscosity_unit.addItem("cSt", "cSt")
        self._dw_viscosity_unit.addItem("m²/s", "m²/s")
        advanced_form.addRow(
            self.tr("Water kinematic viscosity:"),
            self._dw_viscosity_value,
        )
        advanced_form.addRow(self.tr("Viscosity unit:"), self._dw_viscosity_unit)
        viscosity_note = QLabel(
            self.tr(
                "Default: 1.004 mm²/s = 1.004×10⁻⁶ m²/s, representative "
                "of water near 20 °C. Review it for the design temperature."
            )
        )
        viscosity_note.setWordWrap(True)
        advanced_form.addRow(viscosity_note)

        calculate_button = QPushButton(
            self.tr("Evaluate active catalog products")
        )
        calculate_button.clicked.connect(self.darcy_weisbach_requested.emit)
        self._dw_status = QLabel(
            self.tr("Darcy–Weisbach demonstration not calculated.")
        )
        self._dw_status.setWordWrap(True)
        self._dw_output = QPlainTextEdit()
        self._dw_output.setObjectName("DarcyWeisbachOutput")
        self._dw_output.setReadOnly(True)
        notice = QLabel(
            self.tr(
                "Only maximum unit headloss determines admissibility in Stage 9. "
                "No project layer is inspected or edited."
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #666666;")

        layout.addWidget(hint)
        layout.addWidget(input_group)
        layout.addWidget(advanced_group)
        layout.addWidget(calculate_button)
        layout.addWidget(self._dw_status)
        layout.addWidget(self._dw_output, 1)
        layout.addWidget(notice)
        return page

    def _build_combined_sizing_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Defines project-wide sizing rules. Batch sizing supplies each "
                "pipe's flow, length, and endpoint pressures automatically."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(360)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        scope_group = QGroupBox(self.tr("Products Allowed in This Project"))
        scope_form = QFormLayout(scope_group)
        self._project_material_filter = QComboBox()
        self._project_material_filter.addItem(
            self.tr("All active materials"), ""
        )
        scope_form.addRow(
            self.tr("Material scope"), self._project_material_filter
        )
        scope_note = QLabel(
            self.tr(
                "This temporary filter does not change the universal catalog. "
                "Choose one material when the project must use only that material."
            )
        )
        scope_note.setWordWrap(True)
        scope_form.addRow(scope_note)

        segment_group = QGroupBox(self.tr("Hydraulic Method and Headloss"))
        segment_form = QFormLayout(segment_group)
        self._combined_method = QComboBox()
        self._combined_method.addItem(self.tr("Hazen–Williams"), "H-W")
        self._combined_method.addItem(self.tr("Darcy–Weisbach"), "D-W")
        self._combined_gradient_enabled = QCheckBox(
            self.tr("Use maximum unit headloss as a required criterion")
        )
        self._combined_gradient_enabled.setChecked(True)
        self._combined_gradient_value = self._numeric_input(0.0, 1.0e9, 30.0)
        self._combined_gradient_unit = QComboBox()
        for label, code in (
            ("m/km", "m/km"),
            ("m/m", "m/m"),
            ("ft/100 ft", "ft/100 ft"),
            ("ft/1000 ft", "ft/1000 ft"),
        ):
            self._combined_gradient_unit.addItem(label, code)
        segment_form.addRow(self.tr("Hydraulic method"), self._combined_method)
        segment_form.addRow(self._combined_gradient_enabled)
        segment_form.addRow(
            self.tr("Maximum unit headloss"), self._combined_gradient_value
        )
        segment_form.addRow(
            self.tr("Headloss unit"), self._combined_gradient_unit
        )
        self._combined_gradient_enabled.toggled.connect(
            self._combined_gradient_value.setEnabled
        )
        self._combined_gradient_enabled.toggled.connect(
            self._combined_gradient_unit.setEnabled
        )

        velocity_group = QGroupBox(self.tr("Velocity criteria"))
        velocity_form = QFormLayout(velocity_group)
        self._combined_max_velocity_enabled = QCheckBox(
            self.tr("Maximum velocity is required")
        )
        self._combined_max_velocity_enabled.setChecked(True)
        self._combined_max_velocity = self._numeric_input(0.0, 1.0e6, 2.0)
        self._combined_min_velocity_mode = QComboBox()
        self._combined_min_velocity_mode.addItem(
            self.tr("Disabled"), "disabled"
        )
        self._combined_min_velocity_mode.addItem(
            self.tr("Warning only"), "warning"
        )
        self._combined_min_velocity_mode.addItem(
            self.tr("Required"), "required"
        )
        self._combined_min_velocity_mode.setCurrentIndex(1)
        self._combined_min_velocity = self._numeric_input(0.0, 1.0e6, 0.5)
        velocity_form.addRow(self._combined_max_velocity_enabled)
        velocity_form.addRow(
            self.tr("Maximum velocity (m/s):"), self._combined_max_velocity
        )
        velocity_form.addRow(
            self.tr("Minimum velocity behavior:"),
            self._combined_min_velocity_mode,
        )
        velocity_form.addRow(
            self.tr("Minimum velocity (m/s):"), self._combined_min_velocity
        )
        self._combined_max_velocity_enabled.toggled.connect(
            self._combined_max_velocity.setEnabled
        )
        self._combined_min_velocity_mode.currentIndexChanged.connect(
            lambda _index: self._combined_min_velocity.setEnabled(
                self._combined_min_velocity_mode.currentData() != "disabled"
            )
        )

        diameter_group = QGroupBox(self.tr("Diameter criteria"))
        diameter_form = QFormLayout(diameter_group)
        self._combined_min_nominal_enabled = QCheckBox(
            self.tr("Require a minimum nominal diameter")
        )
        self._combined_min_nominal = self._numeric_input(0.0, 1.0e9, 100.0)
        self._combined_min_nominal_unit = QComboBox()
        for label, code in (("mm", "mm"), ("m", "m"), ("in", "in")):
            self._combined_min_nominal_unit.addItem(label, code)
        self._combined_bresse_enabled = QCheckBox(
            self.tr("Use Bresse as an initial minimum-diameter estimate")
        )
        self._combined_bresse_coefficient = self._numeric_input(
            0.0,
            1.0e6,
            1.2,
        )
        diameter_form.addRow(self._combined_min_nominal_enabled)
        diameter_form.addRow(
            self.tr("Minimum DN value:"), self._combined_min_nominal
        )
        diameter_form.addRow(
            self.tr("Minimum DN unit:"), self._combined_min_nominal_unit
        )
        diameter_form.addRow(self._combined_bresse_enabled)
        diameter_form.addRow(
            self.tr("Bresse coefficient K:"),
            self._combined_bresse_coefficient,
        )
        self._combined_min_nominal.setEnabled(False)
        self._combined_min_nominal_unit.setEnabled(False)
        self._combined_bresse_coefficient.setEnabled(False)
        self._combined_min_nominal_enabled.toggled.connect(
            self._combined_min_nominal.setEnabled
        )
        self._combined_min_nominal_enabled.toggled.connect(
            self._combined_min_nominal_unit.setEnabled
        )
        self._combined_bresse_enabled.toggled.connect(
            self._combined_bresse_coefficient.setEnabled
        )

        pressure_group = QGroupBox(self.tr("Product Pressure Criterion"))
        pressure_layout = QVBoxLayout(pressure_group)
        self._combined_pressure_enabled = QCheckBox(
            self.tr(
                "Require product rating to support the maximum endpoint pressure"
            )
        )
        self._combined_pressure_enabled.setChecked(True)
        pressure_note = QLabel(
            self.tr(
                "For every pipe, HydroSizer automatically uses the larger of the "
                "start and end node pressures, applies the configured margin, and "
                "rejects products with insufficient allowable pressure."
            )
        )
        pressure_note.setWordWrap(True)
        pressure_layout.addWidget(self._combined_pressure_enabled)
        pressure_layout.addWidget(pressure_note)

        viscosity_group = QGroupBox(self.tr("Darcy–Weisbach fluid property"))
        viscosity_form = QFormLayout(viscosity_group)
        self._combined_viscosity_value = QDoubleSpinBox()
        self._combined_viscosity_value.setDecimals(12)
        self._combined_viscosity_value.setRange(1.0e-12, 1.0e6)
        self._combined_viscosity_value.setValue(1.004)
        self._combined_viscosity_unit = QComboBox()
        self._combined_viscosity_unit.addItem("mm²/s (cSt)", "mm²/s")
        self._combined_viscosity_unit.addItem("cSt", "cSt")
        self._combined_viscosity_unit.addItem("m²/s", "m²/s")
        viscosity_form.addRow(
            self.tr("Kinematic viscosity:"), self._combined_viscosity_value
        )
        viscosity_form.addRow(
            self.tr("Viscosity unit:"), self._combined_viscosity_unit
        )
        viscosity_group.setEnabled(False)
        self._combined_method.currentIndexChanged.connect(
            lambda _index: viscosity_group.setEnabled(
                self._combined_method.currentData() == "D-W"
            )
        )

        for group in (
            scope_group,
            segment_group,
            velocity_group,
            diameter_group,
            pressure_group,
            viscosity_group,
        ):
            controls_layout.addWidget(group)
        controls_layout.addStretch(1)
        scroll.setWidget(controls)
        layout.addWidget(scroll)

        criteria_controls = (
            self._project_material_filter,
            self._combined_method,
            self._combined_gradient_enabled,
            self._combined_gradient_value,
            self._combined_gradient_unit,
            self._combined_max_velocity_enabled,
            self._combined_max_velocity,
            self._combined_min_velocity_mode,
            self._combined_min_velocity,
            self._combined_min_nominal_enabled,
            self._combined_min_nominal,
            self._combined_min_nominal_unit,
            self._combined_bresse_enabled,
            self._combined_bresse_coefficient,
            self._combined_pressure_enabled,
            self._combined_viscosity_value,
            self._combined_viscosity_unit,
        )
        for control in criteria_controls:
            if isinstance(control, QComboBox):
                control.currentIndexChanged.connect(
                    lambda _value: self.sizing_criteria_changed.emit()
                )
            elif isinstance(control, QCheckBox):
                control.toggled.connect(
                    lambda _value: self.sizing_criteria_changed.emit()
                )
            else:
                control.valueChanged.connect(
                    lambda _value: self.sizing_criteria_changed.emit()
                )
        notice = QLabel(
            self.tr(
                "Selection first rejects products that fail an enabled criterion. "
                "Among the remaining products it chooses the smallest DN, then "
                "the lowest available cost, highest pressure rating, and stable ID."
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #666666;")
        layout.addWidget(notice)
        return page

    def _build_endpoint_pressure_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Configures the automatic batch pressure check. HydroSizer matches "
                "each pipe endpoint to node results and compares the larger pressure, "
                "including any margin, with each candidate product rating."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(350)
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        mapping_group = QGroupBox(self.tr("Read-only endpoint mapping"))
        mapping_form = QFormLayout(mapping_group)
        self._endpoint_pipe_layer = QComboBox()
        self._endpoint_pipe_id_field = QComboBox()
        self._endpoint_node_layer = QComboBox()
        self._endpoint_node_id_field = QComboBox()
        self._endpoint_pressure_field = QComboBox()
        self._endpoint_pressure_unit = QComboBox()
        self._endpoint_tolerance = self._numeric_input(0.0, 1.0e9, 0.01)
        for label, code in (
            ("mca", "mca"),
            ("kPa", "kPa"),
            ("bar", "bar"),
            ("psi", "psi"),
        ):
            self._endpoint_pressure_unit.addItem(label, code)
        mapping_form.addRow(self.tr("Pipe layer:"), self._endpoint_pipe_layer)
        mapping_form.addRow(
            self.tr("Pipe ID field:"), self._endpoint_pipe_id_field
        )
        mapping_form.addRow(
            self.tr("Node result layer/table:"), self._endpoint_node_layer
        )
        mapping_form.addRow(
            self.tr("Node result ID field:"), self._endpoint_node_id_field
        )
        mapping_form.addRow(
            self.tr("Pressure field:"), self._endpoint_pressure_field
        )
        mapping_form.addRow(
            self.tr("Pressure unit:"), self._endpoint_pressure_unit
        )
        mapping_form.addRow(
            self.tr("Endpoint tolerance (pipe CRS units):"),
            self._endpoint_tolerance,
        )
        self._endpoint_pipe_layer.currentIndexChanged.connect(
            self._on_endpoint_pipe_layer_changed
        )
        self._endpoint_node_layer.currentIndexChanged.connect(
            self._on_endpoint_node_layer_changed
        )

        margin_group = QGroupBox(self.tr("Optional Pressure Margin"))
        margin_form = QFormLayout(margin_group)
        self._endpoint_margin_mode = QComboBox()
        self._endpoint_margin_mode.addItem(self.tr("None"), "none")
        self._endpoint_margin_mode.addItem(
            self.tr("Multiplicative factor"), "factor"
        )
        self._endpoint_margin_mode.addItem(
            self.tr("Additive pressure"), "additive"
        )
        self._endpoint_factor = self._numeric_input(1.0, 100.0, 1.1)
        self._endpoint_additive_value = self._numeric_input(0.0, 1.0e12, 10.0)
        self._endpoint_additive_unit = QComboBox()
        for label, code in (
            ("mca", "mca"),
            ("kPa", "kPa"),
            ("bar", "bar"),
            ("psi", "psi"),
        ):
            self._endpoint_additive_unit.addItem(label, code)
        margin_form.addRow(self.tr("Margin mode"), self._endpoint_margin_mode)
        margin_form.addRow(self.tr("Safety factor"), self._endpoint_factor)
        margin_form.addRow(
            self.tr("Additive margin"), self._endpoint_additive_value
        )
        margin_form.addRow(
            self.tr("Additive margin unit"), self._endpoint_additive_unit
        )
        self._endpoint_margin_mode.currentIndexChanged.connect(
            self._update_endpoint_margin_controls
        )
        self._update_endpoint_margin_controls()
        for combo in (
            self._endpoint_pipe_layer,
            self._endpoint_pipe_id_field,
            self._endpoint_node_layer,
            self._endpoint_node_id_field,
            self._endpoint_pressure_field,
            self._endpoint_pressure_unit,
            self._endpoint_margin_mode,
            self._endpoint_additive_unit,
        ):
            combo.currentIndexChanged.connect(
                lambda _value: self.sizing_criteria_changed.emit()
            )
        for value_input in (
            self._endpoint_tolerance,
            self._endpoint_factor,
            self._endpoint_additive_value,
        ):
            value_input.valueChanged.connect(
                lambda _value: self.sizing_criteria_changed.emit()
            )

        refresh_button = QPushButton(self.tr("Refresh layers and catalog"))
        refresh_button.clicked.connect(self.endpoint_refresh_requested.emit)
        controls_layout.addWidget(refresh_button)
        controls_layout.addWidget(mapping_group)
        controls_layout.addWidget(margin_group)
        controls_layout.addStretch(1)
        scroll.setWidget(controls)
        layout.addWidget(scroll)

        self._endpoint_mapping_status = QLabel(
            self.tr("Endpoint mapping has not been refreshed.")
        )
        self._endpoint_mapping_status.setWordWrap(True)
        notice = QLabel(
            self.tr(
                "No pipe-by-pipe action is required here. When the pressure "
                "criterion is enabled, batch sizing performs this check for every "
                "pipe automatically. This is not a transient analysis."
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #666666;")
        layout.addWidget(self._endpoint_mapping_status)
        layout.addWidget(notice)
        return page

    def _build_endpoint_pressure_check_page(self) -> QWidget:
        """Build the optional single-pipe pressure diagnostic."""
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Optional diagnostic for one pipe and one catalog product. The "
                "normal batch workflow performs the same endpoint-pressure rule "
                "automatically for every pipe."
            )
        )
        hint.setWordWrap(True)

        form = QFormLayout()
        self._endpoint_pipe_id_value = QLineEdit()
        self._endpoint_pipe_id_value.setPlaceholderText(
            self.tr("Exact pipe ID, for example 1 or P-001")
        )
        self._endpoint_product = QComboBox()
        form.addRow(self.tr("Pipe ID to evaluate"), self._endpoint_pipe_id_value)
        form.addRow(self.tr("Catalog product"), self._endpoint_product)

        evaluate_button = QPushButton(self.tr("Verify One Pipe"))
        evaluate_button.clicked.connect(self.endpoint_evaluate_requested.emit)
        highlight_layout = QHBoxLayout()
        self._endpoint_highlight_pipe = QPushButton(
            self.tr("Select / zoom pipe")
        )
        self._endpoint_highlight_pipe.setEnabled(False)
        self._endpoint_highlight_pipe.clicked.connect(
            self.endpoint_highlight_pipe_requested.emit
        )
        self._endpoint_highlight_nodes = QPushButton(
            self.tr("Select / zoom endpoint nodes")
        )
        self._endpoint_highlight_nodes.setEnabled(False)
        self._endpoint_highlight_nodes.clicked.connect(
            self.endpoint_highlight_nodes_requested.emit
        )
        highlight_layout.addWidget(self._endpoint_highlight_pipe)
        highlight_layout.addWidget(self._endpoint_highlight_nodes)
        self._endpoint_status = QLabel(
            self.tr("Individual pressure check not run.")
        )
        self._endpoint_status.setWordWrap(True)
        self._endpoint_output = QPlainTextEdit()
        self._endpoint_output.setObjectName("EndpointPressureOutput")
        self._endpoint_output.setReadOnly(True)

        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(evaluate_button)
        layout.addLayout(highlight_layout)
        layout.addWidget(self._endpoint_status)
        layout.addWidget(self._endpoint_output, 1)
        return page

    def _build_batch_sizing_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Uses the validated project mapping, current hydraulic and "
                "selection criteria, active catalog, and geometric endpoint "
                "mapping. Manual check values are replaced by each pipe's mapped "
                "flow and length."
            )
        )
        hint.setWordWrap(True)

        group = QGroupBox(self.tr("Memory-only run"))
        form = QFormLayout(group)
        self._batch_selection_mode = QComboBox()
        self._batch_selection_mode.addItem(self.tr("All mapped pipes"), "all")
        self._batch_selection_mode.addItem(
            self.tr("Selected pipe features only"),
            "selected",
        )
        self._batch_length_unit = QComboBox()
        for label, code in (("m", "m"), ("km", "km"), ("ft", "ft")):
            self._batch_length_unit.addItem(label, code)
        form.addRow(self.tr("Processing mode:"), self._batch_selection_mode)
        form.addRow(
            self.tr("Mapped length attribute unit:"), self._batch_length_unit
        )
        prerequisites = QLabel(
            self.tr(
                "Prerequisites: complete Project mapping and validation; review "
                "the Criteria activities. If pressure is enabled, also review "
                "endpoint mapping and margin."
            )
        )
        prerequisites.setWordWrap(True)
        form.addRow(prerequisites)

        run_button = QPushButton(self.tr("Run memory-only batch sizing"))
        run_button.clicked.connect(self.batch_sizing_requested.emit)
        self._batch_status = QLabel(self.tr("Batch sizing not run."))
        self._batch_status.setWordWrap(True)
        self._batch_output = QPlainTextEdit()
        self._batch_output.setObjectName("BatchSizingOutput")
        self._batch_output.setReadOnly(True)
        notice = QLabel(
            self.tr(
                "The progress dialog provides Cancel. Results are cleared on "
                "plugin reload. There is no apply action in this stage."
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #666666;")

        layout.addWidget(hint)
        layout.addWidget(group)
        layout.addWidget(run_button)
        layout.addWidget(self._batch_status)
        layout.addWidget(self._batch_output, 1)
        layout.addWidget(notice)
        return page

    def _build_preview_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Reviews the latest Batch sizing snapshot without recalculating. "
                "Only successfully sized rows are eligible for later apply."
            )
        )
        hint.setWordWrap(True)

        filters = QGroupBox(self.tr("Preview filters"))
        filter_form = QFormLayout(filters)
        self._preview_search = QLineEdit()
        self._preview_search.setPlaceholderText(
            self.tr("Pipe ID, FID, status, material, product, or message")
        )
        self._preview_status_filter = QComboBox()
        for label, value in (
            (self.tr("All statuses"), "all"),
            (self.tr("Sized"), "sized"),
            (self.tr("Sized with warning"), "sized with warning"),
            (self.tr("No solution"), "no solution"),
            (self.tr("Insufficient data"), "insufficient data"),
        ):
            self._preview_status_filter.addItem(label, value)
        self._preview_inclusion_filter = QComboBox()
        self._preview_inclusion_filter.addItem(self.tr("All rows"), "all")
        self._preview_inclusion_filter.addItem(
            self.tr("Included only"), "included"
        )
        self._preview_inclusion_filter.addItem(
            self.tr("Excluded only"), "excluded"
        )
        apply_filters = QPushButton(self.tr("Apply filters"))
        apply_filters.clicked.connect(self.preview_filter_requested.emit)
        filter_form.addRow(self.tr("Search:"), self._preview_search)
        filter_form.addRow(self.tr("Status:"), self._preview_status_filter)
        filter_form.addRow(self.tr("Inclusion:"), self._preview_inclusion_filter)
        filter_form.addRow(apply_filters)

        self._preview_status = QLabel(
            self.tr("Run Batch sizing to create a preview snapshot.")
        )
        self._preview_status.setWordWrap(True)
        self._preview_table = QTableWidget(0, 15)
        self._preview_table.setObjectName("SizingPreviewTable")
        self._preview_table.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Expanding
        )
        self._preview_table.setHorizontalHeaderLabels(
            (
                self.tr("Include"),
                self.tr("Pipe ID"),
                "FID",
                self.tr("Status"),
                self.tr("Material"),
                self.tr("Product"),
                self.tr("Flow"),
                self.tr("Length"),
                "V (m/s)",
                "J (m/km)",
                "hf (m)",
                self.tr("Pressure ({unit})").format(unit="Pa"),
                self.tr("Controlling criterion"),
                self.tr("Warnings / issues"),
                self.tr("Cost"),
            )
        )
        edit_trigger = getattr(QAbstractItemView, "EditTrigger", None)
        selection_behavior = getattr(QAbstractItemView, "SelectionBehavior", None)
        selection_mode = getattr(QAbstractItemView, "SelectionMode", None)
        self._preview_table.setEditTriggers(
            edit_trigger.NoEditTriggers
            if edit_trigger
            else QAbstractItemView.NoEditTriggers
        )
        self._preview_table.setSelectionBehavior(
            selection_behavior.SelectRows
            if selection_behavior
            else QAbstractItemView.SelectRows
        )
        self._preview_table.setSelectionMode(
            selection_mode.ExtendedSelection
            if selection_mode
            else QAbstractItemView.ExtendedSelection
        )

        actions = QHBoxLayout()
        include_button = QPushButton(self.tr("Include selected rows"))
        include_button.clicked.connect(
            lambda: self.preview_include_requested.emit(True)
        )
        exclude_button = QPushButton(self.tr("Exclude selected rows"))
        exclude_button.clicked.connect(
            lambda: self.preview_include_requested.emit(False)
        )
        map_button = QPushButton(self.tr("Select selected rows on map"))
        map_button.clicked.connect(self.preview_map_selection_requested.emit)
        export_button = QPushButton(self.tr("Export displayed CSV..."))
        export_button.clicked.connect(self.preview_export_requested.emit)
        actions.addWidget(include_button)
        actions.addWidget(exclude_button)
        actions.addWidget(map_button)
        actions.addWidget(export_button)

        notice = QLabel(
            self.tr(
                "Include/exclude changes only plugin memory. CSV export contains "
                "the currently displayed rows. There is no layer apply action in "
                "this stage."
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #666666;")
        layout.addWidget(hint)
        layout.addWidget(filters)
        layout.addWidget(self._preview_status)
        layout.addWidget(self._preview_table, 1)
        layout.addLayout(actions)
        layout.addWidget(notice)
        return page

    def _build_safe_apply_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Map existing pipe fields explicitly. Prepare reviews current and "
                "proposed values without editing. Apply is enabled only for a "
                "current plan and always asks for confirmation."
            )
        )
        hint.setWordWrap(True)

        mapping_group = QGroupBox(self.tr("Destination fields"))
        form = QFormLayout(mapping_group)
        self._apply_material_field = QComboBox()
        self._apply_nominal_field = QComboBox()
        self._apply_nominal_unit = QComboBox()
        self._apply_internal_field = QComboBox()
        self._apply_internal_unit = QComboBox()
        self._apply_hydraulic_field = QComboBox()
        self._apply_roughness_unit = QComboBox()
        self._apply_pressure_class_field = QComboBox()
        for combo in (self._apply_nominal_unit, self._apply_internal_unit):
            for unit in ("mm", "m", "in"):
                combo.addItem(unit, unit)
        for unit in ("mm", "m", "in"):
            self._apply_roughness_unit.addItem(unit, unit)
        form.addRow(
            self.tr("QGISRed material value ->"), self._apply_material_field
        )
        form.addRow(self.tr("Nominal diameter ->"), self._apply_nominal_field)
        form.addRow(
            self.tr("Nominal destination unit:"), self._apply_nominal_unit
        )
        form.addRow(self.tr("Internal diameter ->"), self._apply_internal_field)
        form.addRow(
            self.tr("Internal destination unit:"), self._apply_internal_unit
        )
        self._apply_hydraulic_label = QLabel(
            self.tr("H-W C / absolute roughness ->")
        )
        form.addRow(self._apply_hydraulic_label, self._apply_hydraulic_field)
        form.addRow(
            self.tr("D-W roughness destination unit:"), self._apply_roughness_unit
        )
        form.addRow(
            self.tr("Pressure class ->"), self._apply_pressure_class_field
        )
        mapping_note = QLabel(
            self.tr(
                "Every mapping is optional, but at least one field is required. "
                "A destination field cannot be used twice. Material mapping "
                "requires qgisred_material_value in every selected product."
            )
        )
        mapping_note.setWordWrap(True)
        form.addRow(mapping_note)

        audit_group = QGroupBox(self.tr("Required audit output"))
        audit_layout = QHBoxLayout(audit_group)
        self._apply_audit_directory = QLineEdit()
        self._apply_audit_directory.setPlaceholderText(
            self.tr("Choose the HydroSizer_Audit directory")
        )
        audit_button = QPushButton(self.tr("Choose directory..."))
        audit_button.clicked.connect(self.apply_audit_browse_requested.emit)
        audit_layout.addWidget(self._apply_audit_directory, 1)
        audit_layout.addWidget(audit_button)

        for combo in (
            self._apply_material_field,
            self._apply_nominal_field,
            self._apply_nominal_unit,
            self._apply_internal_field,
            self._apply_internal_unit,
            self._apply_hydraulic_field,
            self._apply_roughness_unit,
            self._apply_pressure_class_field,
        ):
            combo.currentIndexChanged.connect(
                lambda _index: self.apply_configuration_changed.emit()
            )
        self._apply_audit_directory.editingFinished.connect(
            self.apply_configuration_changed.emit
        )

        actions = QHBoxLayout()
        prepare_button = QPushButton(self.tr("Prepare before/after apply plan"))
        prepare_button.clicked.connect(self.apply_plan_requested.emit)
        self._apply_button = QPushButton(self.tr("Apply confirmed changes"))
        self._apply_button.setEnabled(False)
        self._apply_button.clicked.connect(self.apply_execute_requested.emit)
        actions.addWidget(prepare_button)
        actions.addStretch(1)
        actions.addWidget(self._apply_button)

        self._apply_status = QLabel(
            self.tr(
                "Run Batch sizing and review Preview inclusion before preparing a plan."
            )
        )
        self._apply_status.setWordWrap(True)
        self._apply_output = QPlainTextEdit()
        self._apply_output.setObjectName("SafeApplyOutput")
        self._apply_output.setReadOnly(True)
        notice = QLabel(
            self.tr(
                "Successful values remain pending in the QGIS edit buffer. Use "
                "QGIS Save Layer Edits to persist or Undo to revert. QGISRed DBF "
                "catalog files are never changed."
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #666666;")
        layout.addWidget(hint)
        layout.addWidget(mapping_group)
        layout.addWidget(audit_group)
        layout.addLayout(actions)
        layout.addWidget(self._apply_status)
        layout.addWidget(self._apply_output, 1)
        layout.addWidget(notice)
        return page

    def _build_reports_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            self.tr(
                "Exports the project's hydraulic calculation memory as HTML and "
                "the detailed sizing spreadsheet as CSV. Complete the document "
                "control data before export. To obtain a PDF, print the HTML "
                "directly from the browser."
            )
        )
        hint.setWordWrap(True)

        identification = QGroupBox(
            self.tr("Project and document identification")
        )
        form = QGridLayout(identification)
        self._report_project_title = QLineEdit()
        self._report_client = QLineEdit()
        self._report_location = QLineEdit()
        self._report_project_stage = QLineEdit()
        self._report_scenario = QLineEdit()
        self._report_responsible = QLineEdit()
        self._report_registration = QLineEdit()
        self._report_document_code = QLineEdit()
        self._report_revision = QLineEdit("00")
        self._report_description = QPlainTextEdit()
        self._report_description.setMaximumHeight(58)
        self._report_project_title.setPlaceholderText(self.tr("Project title"))
        self._report_client.setPlaceholderText(self.tr("Client or owner"))
        self._report_location.setPlaceholderText(self.tr("Municipality/state"))
        self._report_project_stage.setPlaceholderText(
            self.tr("Basic design, detailed design...")
        )
        self._report_scenario.setPlaceholderText(
            self.tr("Peak hour, minimum level...")
        )
        self._report_responsible.setPlaceholderText(
            self.tr("Name of the responsible professional")
        )
        self._report_registration.setPlaceholderText(
            self.tr("Professional council and registration number")
        )
        self._report_document_code.setPlaceholderText(
            self.tr("Internal document code")
        )
        self._report_description.setPlaceholderText(
            self.tr("Brief description of the project and adopted design concept")
        )
        fields = (
            (
                self.tr("Project:"),
                self._report_project_title,
                self.tr("Client:"),
                self._report_client,
            ),
            (
                self.tr("Location:"),
                self._report_location,
                self.tr("Project stage:"),
                self._report_project_stage,
            ),
            (
                self.tr("Hydraulic scenario:"),
                self._report_scenario,
                self.tr("Responsible professional:"),
                self._report_responsible,
            ),
            (
                self.tr("Professional registration:"),
                self._report_registration,
                self.tr("Document code:"),
                self._report_document_code,
            ),
        )
        for row, (label1, field1, label2, field2) in enumerate(fields):
            form.addWidget(QLabel(label1), row, 0)
            form.addWidget(field1, row, 1)
            form.addWidget(QLabel(label2), row, 2)
            form.addWidget(field2, row, 3)
        form.addWidget(QLabel(self.tr("Revision:")), 4, 0)
        form.addWidget(self._report_revision, 4, 1)
        form.addWidget(QLabel(self.tr("Description/design concept:")), 5, 0)
        form.addWidget(self._report_description, 5, 1, 1, 3)

        export_button = QPushButton(
            self.tr("Export calculation memory HTML + CSV spreadsheet...")
        )
        export_button.clicked.connect(self.report_export_requested.emit)
        self._report_status = QLabel(
            self.tr("Run batch sizing and review the preview before exporting.")
        )
        self._report_status.setWordWrap(True)
        self._report_output = QPlainTextEdit()
        self._report_output.setObjectName("CalculationMemoryOutput")
        self._report_output.setReadOnly(True)
        notice = QLabel(
            self.tr(
                "The export uses only the in-memory snapshot and does not change "
                "layers or the catalog. The document must be reviewed and signed "
                "by the responsible professional."
            )
        )
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #666666;")

        layout.addWidget(hint)
        layout.addWidget(identification)
        layout.addWidget(export_button)
        layout.addWidget(self._report_status)
        layout.addWidget(self._report_output, 1)
        layout.addWidget(notice)
        return page

    def set_diagnostic_result(self, summary: str, details: str) -> None:
        """Show a successful environment diagnostic and enable JSON export."""
        self._diagnostic_status.setText(summary)
        self._diagnostic_output.setPlainText(details)
        self._export_button.setEnabled(True)

    def set_diagnostic_error(self, message: str) -> None:
        """Show an environment diagnostic error and disable export."""
        self._diagnostic_status.setText(message)
        self._diagnostic_output.clear()
        self._export_button.setEnabled(False)

    def set_qgisred_detection_result(
        self, summary: str, details: str, candidate_found: bool
    ) -> None:
        """Show candidate search details before optional DBF inspection."""
        self._qgisred_status.setText(summary)
        self._detection_output.setPlainText(details)
        if not candidate_found:
            self._options_output.clear()
            self._select_combo_data(self._flow_unit_combo, "")
            self._select_combo_data(self._headloss_combo, "")

    def set_options_inspection_result(
        self,
        summary: str,
        details: str,
        semantics: Mapping[str, Any],
    ) -> None:
        """Show inspected records and prefill reviewable detected settings."""
        self._qgisred_status.setText(summary)
        self._options_output.setPlainText(details)
        self._select_combo_data(
            self._flow_unit_combo,
            semantics["flow_units_code"]
            if semantics["flow_unit_supported"]
            else "",
        )
        self._select_combo_data(
            self._headloss_combo,
            semantics["headloss_code"]
            if semantics["hydraulic_method_supported"]
            else "",
        )

    def set_qgisred_error(self, message: str) -> None:
        """Show a detection or DBF inspection failure."""
        self._qgisred_status.setText(message)
        self._options_output.setPlainText(message)

    def set_mapping_inventory(
        self,
        inventory: Sequence[Mapping[str, Any]],
        suggestions: Mapping[str, str],
    ) -> None:
        """Populate compatible layer and field controls from an inventory."""
        self._mapping_inventory = list(inventory)
        self._mapping_suggestions = dict(suggestions)
        pipe_layers = [layer for layer in inventory if layer["is_line"]]
        result_layers = [
            layer
            for layer in inventory
            if any(field["numeric"] for field in layer["fields"])
        ]
        self._replace_combo_items(
            self._pipe_layer_combo,
            [
                (mapping_display_name(layer), layer["id"])
                for layer in pipe_layers
            ],
            suggestions.get("pipe_layer_id", ""),
        )
        self._replace_combo_items(
            self._result_layer_combo,
            [
                (mapping_display_name(layer), layer["id"])
                for layer in result_layers
            ],
            suggestions.get("result_layer_id", ""),
        )
        self._on_pipe_layer_changed()
        self._on_result_layer_changed()
        self._mapping_status.setText(
            self.tr(
                "Loaded {count} vector layer(s). Review the suggestions and "
                "store the temporary mapping."
            ).format(count=len(inventory))
        )
        self._mapping_summary.clear()
        self.reset_validation(
            self.tr(
                "Layer inventory refreshed. Store the mapping before validation."
            )
        )

    def mapping_configuration(self) -> Dict[str, str]:
        """Return the current user-reviewable selections."""
        pipe_layer = self._layer_by_id(self._pipe_layer_combo.currentData())
        result_layer = self._layer_by_id(self._result_layer_combo.currentData())
        return {
            "pipe_layer_id": self._pipe_layer_combo.currentData() or "",
            "pipe_layer_name": pipe_layer["name"] if pipe_layer else "",
            "pipe_id_field": self._pipe_id_combo.currentData() or "",
            "length_field": self._length_combo.currentData() or "",
            "result_layer_id": self._result_layer_combo.currentData() or "",
            "result_layer_name": result_layer["name"] if result_layer else "",
            "result_id_field": self._result_id_combo.currentData() or "",
            "flow_field": self._flow_combo.currentData() or "",
            "flow_unit_code": self._flow_unit_combo.currentData() or "",
            "headloss_code": self._headloss_combo.currentData() or "",
        }

    def set_mapping_saved(self, summary: str, details: str) -> None:
        """Confirm that the mapping was stored in plugin memory."""
        self._mapping_status.setText(summary)
        self._mapping_summary.setPlainText(details)
        self.reset_validation(
            self.tr("Temporary mapping stored. Ready for validation.")
        )

    def set_mapping_error(self, message: str) -> None:
        """Show an inventory or incomplete-mapping error."""
        self._mapping_status.setText(message)

    def set_validation_result(
        self,
        summary: str,
        report: str,
        pipe_problem_count: int,
        result_problem_count: int,
    ) -> None:
        """Show a validation report and enable applicable highlight actions."""
        self._validation_status.setText(summary)
        self._validation_output.setPlainText(report)
        self._pipe_highlight_button.setEnabled(pipe_problem_count > 0)
        self._result_highlight_button.setEnabled(result_problem_count > 0)

    def set_validation_error(self, message: str) -> None:
        """Show a validation prerequisite or runtime error."""
        self.reset_validation(message)

    def reset_validation(self, message: str) -> None:
        """Clear stale validation output and disable highlight actions."""
        if not hasattr(self, "_validation_status"):
            return
        self._validation_status.setText(message)
        self._validation_output.clear()
        self._pipe_highlight_button.setEnabled(False)
        self._result_highlight_button.setEnabled(False)

    def basic_calculation_inputs(self) -> Dict[str, Any]:
        """Return manual Stage 6 inputs without consulting project layers."""
        return {
            "flow_value": self._demo_flow_value.value(),
            "flow_unit": self._demo_flow_unit.currentData(),
            "diameter_value": self._demo_diameter_value.value(),
            "diameter_unit": self._demo_diameter_unit.currentData(),
            "length_value": self._demo_length_value.value(),
            "length_unit": self._demo_length_unit.currentData(),
            "unit_cost_value": self._demo_cost_value.value(),
            "cost_length_unit": self._demo_cost_unit.currentData(),
        }

    def set_basic_calculation_result(self, summary: str, details: str) -> None:
        """Show a successful demonstration result."""
        self._basic_calculation_status.setText(summary)
        self._basic_calculation_output.setPlainText(details)

    def set_basic_calculation_error(self, message: str) -> None:
        """Show an invalid demonstration input without raising into QGIS."""
        self._basic_calculation_status.setText(message)
        self._basic_calculation_output.clear()

    def hazen_williams_inputs(self) -> Dict[str, Any]:
        """Return manual Stage 8 inputs without consulting project layers."""
        return {
            "flow_value": self._hw_flow_value.value(),
            "flow_unit": self._hw_flow_unit.currentData(),
            "length_value": self._hw_length_value.value(),
            "length_unit": self._hw_length_unit.currentData(),
            "max_gradient_value": self._hw_gradient_value.value(),
            "max_gradient_unit": self._hw_gradient_unit.currentData(),
        }

    def set_hazen_williams_result(self, summary: str, details: str) -> None:
        self._hw_status.setText(summary)
        self._hw_output.setPlainText(details)

    def set_hazen_williams_error(self, message: str) -> None:
        self._hw_status.setText(message)
        self._hw_output.clear()

    def darcy_weisbach_inputs(self) -> Dict[str, Any]:
        """Return manual Stage 9 inputs without consulting project layers."""
        return {
            "flow_value": self._dw_flow_value.value(),
            "flow_unit": self._dw_flow_unit.currentData(),
            "length_value": self._dw_length_value.value(),
            "length_unit": self._dw_length_unit.currentData(),
            "max_gradient_value": self._dw_gradient_value.value(),
            "max_gradient_unit": self._dw_gradient_unit.currentData(),
            "kinematic_viscosity_value": self._dw_viscosity_value.value(),
            "kinematic_viscosity_unit": self._dw_viscosity_unit.currentData(),
        }

    def set_darcy_weisbach_result(self, summary: str, details: str) -> None:
        self._dw_status.setText(summary)
        self._dw_output.setPlainText(details)

    def set_darcy_weisbach_error(self, message: str) -> None:
        self._dw_status.setText(message)
        self._dw_output.clear()

    def combined_sizing_inputs(self) -> Dict[str, Any]:
        """Return project criteria; batch sizing replaces placeholder inputs."""
        return {
            "hydraulic_method": self._combined_method.currentData(),
            "flow_value": 0.0,
            "flow_unit": "LPS",
            "length_value": 0.0,
            "length_unit": "m",
            "max_gradient_enabled": self._combined_gradient_enabled.isChecked(),
            "max_gradient_value": self._combined_gradient_value.value(),
            "max_gradient_unit": self._combined_gradient_unit.currentData(),
            "max_velocity_enabled": self._combined_max_velocity_enabled.isChecked(),
            "max_velocity_m_s": self._combined_max_velocity.value(),
            "min_velocity_mode": self._combined_min_velocity_mode.currentData(),
            "min_velocity_m_s": self._combined_min_velocity.value(),
            "min_nominal_enabled": self._combined_min_nominal_enabled.isChecked(),
            "min_nominal_value": self._combined_min_nominal.value(),
            "min_nominal_unit": self._combined_min_nominal_unit.currentData(),
            "bresse_enabled": self._combined_bresse_enabled.isChecked(),
            "bresse_coefficient": self._combined_bresse_coefficient.value(),
            "pressure_enabled": self._combined_pressure_enabled.isChecked(),
            "verification_pressure_value": 0.0,
            "verification_pressure_unit": "Pa",
            "material_filter": self._project_material_filter.currentData() or "",
            "kinematic_viscosity_value": self._combined_viscosity_value.value(),
            "kinematic_viscosity_unit": self._combined_viscosity_unit.currentData(),
        }

    def set_endpoint_pressure_inventory(
        self,
        inventory: Sequence[Mapping[str, Any]],
        suggestions: Mapping[str, str],
        products: Sequence[Mapping[str, Any]],
    ) -> None:
        """Populate Stage 11 mapping controls and active catalog products."""
        self._mapping_inventory = list(inventory)
        self._endpoint_suggestions = dict(suggestions)
        pipe_layers = [layer for layer in inventory if layer["is_line"]]
        node_layers = [
            layer
            for layer in inventory
            if any(field["numeric"] for field in layer["fields"])
        ]
        self._replace_combo_items(
            self._endpoint_pipe_layer,
            [(mapping_display_name(layer), layer["id"]) for layer in pipe_layers],
            suggestions.get("pipe_layer_id", ""),
        )
        self._replace_combo_items(
            self._endpoint_node_layer,
            [(mapping_display_name(layer), layer["id"]) for layer in node_layers],
            suggestions.get("node_layer_id", ""),
        )
        self._on_endpoint_pipe_layer_changed()
        self._on_endpoint_node_layer_changed()
        self._endpoint_product.clear()
        self._endpoint_product.addItem(self.tr("Not selected"), None)
        for product in products:
            pressure = self._value_with_unit(
                product.get("max_allowable_pressure"),
                product.get("pressure_unit"),
            )
            label = (
                f"ID {product['catalog_id']} — "
                f"{product['material_code']}/{product['product_code']} — "
                f"{pressure}"
            )
            self._endpoint_product.addItem(label, product["catalog_id"])
        self._endpoint_mapping_status.setText(
            self.tr(
                "Automatic pressure mapping refreshed: {layer_count} vector "
                "layer(s); {product_count} active catalog product(s)."
            ).format(
                layer_count=len(inventory),
                product_count=len(products),
            )
        )
        self._endpoint_output.clear()
        self._endpoint_highlight_pipe.setEnabled(False)
        self._endpoint_highlight_nodes.setEnabled(False)

    def endpoint_pressure_configuration(self) -> Dict[str, Any]:
        """Return reviewable Stage 11 mapping and verification inputs."""
        return {
            "pipe_layer_id": self._endpoint_pipe_layer.currentData() or "",
            "pipe_id_field": self._endpoint_pipe_id_field.currentData() or "",
            "node_layer_id": self._endpoint_node_layer.currentData() or "",
            "node_id_field": self._endpoint_node_id_field.currentData() or "",
            "pressure_field": self._endpoint_pressure_field.currentData() or "",
            "pressure_unit": self._endpoint_pressure_unit.currentData(),
            "endpoint_tolerance": self._endpoint_tolerance.value(),
            "requested_pipe_id": self._endpoint_pipe_id_value.text(),
            "catalog_id": self._endpoint_product.currentData(),
            "margin_mode": self._endpoint_margin_mode.currentData(),
            "safety_factor": self._endpoint_factor.value(),
            "additive_margin_value": self._endpoint_additive_value.value(),
            "additive_margin_unit": self._endpoint_additive_unit.currentData(),
        }

    def set_endpoint_pressure_result(self, summary: str, report: str) -> None:
        self._endpoint_status.setText(summary)
        self._endpoint_output.setPlainText(report)
        self._endpoint_highlight_pipe.setEnabled(True)
        self._endpoint_highlight_nodes.setEnabled(True)

    def set_endpoint_pressure_error(self, message: str) -> None:
        self._endpoint_status.setText(message)
        self._endpoint_output.clear()
        self._endpoint_highlight_pipe.setEnabled(False)
        self._endpoint_highlight_nodes.setEnabled(False)

    def set_endpoint_mapping_error(self, message: str) -> None:
        """Show automatic endpoint-mapping errors in the project workflow."""
        self._endpoint_mapping_status.setText(message)

    def batch_sizing_configuration(self) -> Dict[str, Any]:
        """Return Stage 12 scope and mapped length unit."""
        return {
            "selection_mode": self._batch_selection_mode.currentData(),
            "length_unit": self._batch_length_unit.currentData(),
        }

    def set_batch_sizing_result(self, summary: str, report: str) -> None:
        self._batch_status.setText(summary)
        self._batch_output.setPlainText(report)

    def set_batch_sizing_error(self, message: str) -> None:
        self._batch_status.setText(message)
        self._batch_output.clear()

    def preview_filters(self) -> Dict[str, str]:
        return {
            "search": self._preview_search.text(),
            "status": self._preview_status_filter.currentData(),
            "inclusion": self._preview_inclusion_filter.currentData(),
        }

    def selected_preview_fids(self) -> list:
        item_data_role = getattr(Qt, "ItemDataRole", None)
        user_role = item_data_role.UserRole if item_data_role else Qt.UserRole
        selected_rows = sorted(
            {index.row() for index in self._preview_table.selectedIndexes()}
        )
        fids = []
        for row in selected_rows:
            item = self._preview_table.item(row, 2)
            if item is not None:
                fids.append(int(item.data(user_role)))
        return fids

    def displayed_preview_fids(self) -> list:
        item_data_role = getattr(Qt, "ItemDataRole", None)
        user_role = item_data_role.UserRole if item_data_role else Qt.UserRole
        fids = []
        for row in range(self._preview_table.rowCount()):
            item = self._preview_table.item(row, 2)
            if item is not None:
                fids.append(int(item.data(user_role)))
        return fids

    def set_preview_rows(
        self,
        rows: Sequence[Mapping[str, Any]],
        summary: Mapping[str, int],
        operation_message: str = "",
        pressure_unit: str = "Pa",
    ) -> None:
        """Replace the filtered Stage 13 table without changing source data."""
        pressure_header = self._preview_table.horizontalHeaderItem(11)
        if pressure_header is not None:
            pressure_header.setText(
                self.tr("Pressure ({unit})").format(unit=pressure_unit)
            )
        self._preview_table.setSortingEnabled(False)
        self._preview_table.setRowCount(len(rows))
        item_data_role = getattr(Qt, "ItemDataRole", None)
        user_role = item_data_role.UserRole if item_data_role else Qt.UserRole
        for table_row, row in enumerate(rows):
            if row["eligible"]:
                include_label = self.tr("Yes") if row["included"] else self.tr("No")
            else:
                include_label = self.tr("No (ineligible)")
            status_labels = {
                "sized": self.tr("Sized"),
                "sized with warning": self.tr("Sized with warning"),
                "no solution": self.tr("No solution"),
                "insufficient data": self.tr("Insufficient data"),
            }
            values = (
                include_label,
                row["pipe_id"],
                row["pipe_fid"],
                status_labels.get(row["status"], row["status"]),
                row["material_code"],
                row["product_code"],
                self._value_with_unit(row["flow_original"], row["flow_unit"]),
                self._value_with_unit(
                    row["length_original"], row["length_unit"]
                ),
                self._catalog_value(row["velocity_m_s"]),
                self._catalog_value(row["unit_headloss_m_km"]),
                self._catalog_value(row["total_headloss_m"]),
                self._catalog_value(row.get("verification_pressure_display")),
                self._preview_criterion_label(row.get("controlling_criterion")),
                row.get("messages_display") or "—",
                self._catalog_value(row["segment_cost"]),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(user_role, int(row["pipe_fid"]))
                if column in {12, 13}:
                    item.setToolTip(str(value))
                self._preview_table.setItem(table_row, column, item)
        self._preview_table.setSortingEnabled(True)
        self._preview_table.resizeColumnsToContents()
        self._preview_table.setColumnWidth(
            13,
            min(360, max(220, self._preview_table.columnWidth(13))),
        )
        status = self.tr(
            "Displayed {displayed} of {total} row(s); eligible={eligible}; "
            "included={included}; excluded={excluded}."
        ).format(
            displayed=len(rows),
            total=summary["total"],
            eligible=summary["eligible"],
            included=summary["included"],
            excluded=summary["excluded"],
        )
        if operation_message:
            status = f"{operation_message} {status}"
        self._preview_status.setText(status)

    def set_preview_error(self, message: str, clear: bool = False) -> None:
        self._preview_status.setText(message)
        if clear:
            self._preview_table.setRowCount(0)

    def _preview_criterion_label(self, value: Any) -> str:
        labels = {
            "pressure": self.tr("Pressure"),
            "unit headloss": self.tr("Unit headloss"),
            "maximum velocity": self.tr("Maximum velocity"),
            "minimum velocity": self.tr("Minimum velocity"),
            "minimum nominal diameter": self.tr("Minimum nominal diameter"),
            "Bresse initial diameter": self.tr("Bresse initial diameter"),
            "hydraulic data": self.tr("Hydraulic data"),
            "selection order": self.tr("Selection order"),
        }
        return labels.get(str(value or ""), "—" if not value else str(value))

    def set_apply_layer_fields(
        self,
        fields: Sequence[Mapping[str, Any]],
        hydraulic_method: str,
    ) -> None:
        """Populate compatible existing destination fields for Stage 14."""
        numeric = [field for field in fields if field["numeric"]]
        text = [field for field in fields if field["category"] == "text"]
        self._replace_combo_items(
            self._apply_material_field,
            [(field["name"], field["name"]) for field in text],
            "",
        )
        self._replace_combo_items(
            self._apply_nominal_field,
            [(field["name"], field["name"]) for field in numeric],
            self._preferred_apply_field(
                numeric,
                ("DN", "NominalDiameter", "NominalD"),
            ),
        )
        self._replace_combo_items(
            self._apply_internal_field,
            [(field["name"], field["name"]) for field in numeric],
            self._preferred_apply_field(
                numeric,
                ("Diameter", "InternalD", "InternalDiameter", "DiamInt"),
            ),
        )
        self._replace_combo_items(
            self._apply_hydraulic_field,
            [(field["name"], field["name"]) for field in numeric],
            self._preferred_apply_field(
                numeric,
                ("RoughCoeff", "ROUGHNESS", "Roughness"),
            ),
        )
        self._replace_combo_items(
            self._apply_pressure_class_field,
            [(field["name"], field["name"]) for field in text],
            self._preferred_apply_field(
                text,
                ("PressureClass", "PN", "Class"),
            ),
        )
        darcy = hydraulic_method == "D-W"
        self._apply_roughness_unit.setEnabled(darcy)
        self._apply_hydraulic_label.setText(
            self.tr("Absolute roughness ->")
            if darcy
            else self.tr("Hazen-Williams C ->")
        )
        self.invalidate_apply_plan(
            self.tr(
                "Destination mapping loaded for {method}; prepare a plan."
            ).format(method=hydraulic_method)
        )

    def apply_configuration(self) -> Dict[str, str]:
        return {
            "material_field": self._apply_material_field.currentData() or "",
            "nominal_field": self._apply_nominal_field.currentData() or "",
            "nominal_unit": self._apply_nominal_unit.currentData(),
            "internal_field": self._apply_internal_field.currentData() or "",
            "internal_unit": self._apply_internal_unit.currentData(),
            "hydraulic_field": self._apply_hydraulic_field.currentData() or "",
            "roughness_unit": self._apply_roughness_unit.currentData(),
            "pressure_class_field": (
                self._apply_pressure_class_field.currentData() or ""
            ),
            "audit_directory": self._apply_audit_directory.text().strip(),
        }

    def set_apply_audit_directory(self, directory: str) -> None:
        self._apply_audit_directory.setText(directory)
        self.apply_configuration_changed.emit()

    def set_apply_plan(self, summary: str, report: str, change_count: int) -> None:
        self._apply_status.setText(summary)
        self._apply_output.setPlainText(report)
        self._apply_button.setText(
            self.tr("Apply {count} confirmed change(s)").format(
                count=change_count
            )
        )
        self._apply_button.setEnabled(change_count > 0)

    def set_apply_result(self, summary: str, report: str) -> None:
        self._apply_status.setText(summary)
        self._apply_output.setPlainText(report)
        self._apply_button.setEnabled(False)

    def set_apply_error(self, message: str, clear_report: bool = False) -> None:
        self._apply_status.setText(message)
        self._apply_button.setEnabled(False)
        if clear_report:
            self._apply_output.clear()

    def report_configuration(self) -> Dict[str, str]:
        return {
            "project_title": self._report_project_title.text().strip(),
            "client": self._report_client.text().strip(),
            "location": self._report_location.text().strip(),
            "project_stage": self._report_project_stage.text().strip(),
            "hydraulic_scenario": self._report_scenario.text().strip(),
            "responsible": self._report_responsible.text().strip(),
            "professional_registration": self._report_registration.text().strip(),
            "document_code": self._report_document_code.text().strip(),
            "revision": self._report_revision.text().strip() or "00",
            "project_description": self._report_description.toPlainText().strip(),
        }

    def set_report_project_title(self, title: str) -> None:
        if not self._report_project_title.text().strip():
            self._report_project_title.setText(title)

    def set_report_result(self, summary: str, details: str) -> None:
        self._report_status.setText(summary)
        self._report_output.setPlainText(details)

    def set_report_error(self, message: str, clear: bool = False) -> None:
        self._report_status.setText(message)
        if clear:
            self._report_output.clear()

    def invalidate_apply_plan(
        self,
        message: str = "",
    ) -> None:
        if not message:
            message = self.tr(
                "Apply configuration changed. Prepare the plan again."
            )
        self._apply_status.setText(message)
        self._apply_button.setText(self.tr("Apply confirmed changes"))
        self._apply_button.setEnabled(False)
        self._apply_output.clear()

    @staticmethod
    def _preferred_apply_field(fields, preferences) -> str:
        by_casefold = {field["name"].casefold(): field["name"] for field in fields}
        for preferred in preferences:
            if preferred.casefold() in by_casefold:
                return by_casefold[preferred.casefold()]
        return ""

    def catalog_filters(self) -> Dict[str, Any]:
        return {
            "search": self._catalog_search.text(),
            "active_only": self._catalog_active_only.isChecked(),
        }

    def selected_catalog_id(self) -> Optional[int]:
        row = self._catalog_table.currentRow()
        if row < 0:
            return None
        item = self._catalog_table.item(row, 0)
        return int(item.text()) if item is not None else None

    def set_catalog_products(
        self, products: Sequence[Mapping[str, Any]], database_path: str
    ) -> None:
        """Replace the read-only product table and retain header sorting."""
        self._catalog_table.setSortingEnabled(False)
        self._catalog_table.setRowCount(len(products))
        for row, product in enumerate(products):
            values = (
                product["catalog_id"],
                self.tr("Yes") if product["active"] else self.tr("No"),
                product["material_code"],
                product["material_name_pt"],
                product["product_code"],
                self._value_with_unit(
                    product["nominal_diameter"],
                    product["nominal_diameter_unit"],
                ),
                self._value_with_unit(
                    product["internal_diameter"],
                    product["internal_diameter_unit"],
                ),
                self._value_with_unit(
                    product["max_allowable_pressure"],
                    product["pressure_unit"],
                ),
                self._catalog_value(product["hazen_williams_c"]),
                self._value_with_unit(
                    product["absolute_roughness"],
                    product["roughness_unit"],
                ),
                self._value_with_unit(
                    product["cost_per_length"],
                    product["cost_length_unit"],
                ),
            )
            for column, value in enumerate(values):
                self._catalog_table.setItem(
                    row, column, QTableWidgetItem(str(value))
                )
        self._catalog_table.setSortingEnabled(True)
        self._catalog_table.resizeColumnsToContents()
        self._catalog_status.setText(
            self.tr(
                "Catalog contains {count} displayed product(s). Database: {path}"
            ).format(count=len(products), path=database_path)
        )

    def set_project_materials(
        self, products: Sequence[Mapping[str, Any]]
    ) -> None:
        """Populate the temporary per-project material scope from active products."""
        selected = self._project_material_filter.currentData() or ""
        materials = sorted(
            {
                str(product.get("material_code") or "").strip()
                for product in products
                if str(product.get("material_code") or "").strip()
            },
            key=str.casefold,
        )
        combo = self._project_material_filter
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(self.tr("All active materials"), "")
        for material in materials:
            combo.addItem(material, material)
        index = combo.findData(selected if selected in materials else "")
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def set_catalog_report(self, summary: str, details: str = "") -> None:
        self._catalog_status.setText(summary)
        self._catalog_report.setPlainText(details)

    def set_catalog_error(self, message: str) -> None:
        self._catalog_status.setText(message)
        self._catalog_report.setPlainText(message)

    def _on_endpoint_pipe_layer_changed(self, _index: int = -1) -> None:
        layer = self._layer_by_id(self._endpoint_pipe_layer.currentData())
        fields = endpoint_fields(layer, numeric=False)
        selected = self._endpoint_field_choice(
            "pipe_id_field",
            fields,
            ("Id", "pipe_id", "DC_ID"),
        )
        self._replace_field_combo(
            self._endpoint_pipe_id_field,
            fields,
            selected,
        )

    def _on_endpoint_node_layer_changed(self, _index: int = -1) -> None:
        layer = self._layer_by_id(self._endpoint_node_layer.currentData())
        id_fields = endpoint_fields(layer, numeric=False)
        pressure_fields = endpoint_fields(layer, numeric=True)
        node_id = self._endpoint_field_choice(
            "node_id_field",
            id_fields,
            ("Id", "node_id", "DC_ID"),
        )
        pressure = self._endpoint_field_choice(
            "pressure_field",
            pressure_fields,
            ("Pressure", "pressao", "press"),
        )
        self._replace_field_combo(self._endpoint_node_id_field, id_fields, node_id)
        self._replace_field_combo(
            self._endpoint_pressure_field,
            pressure_fields,
            pressure,
        )

    def _endpoint_field_choice(
        self,
        key: str,
        fields: Sequence[Mapping[str, Any]],
        preferences: Sequence[str],
    ) -> str:
        available = {field["name"] for field in fields}
        suggested = getattr(self, "_endpoint_suggestions", {}).get(key, "")
        if suggested in available:
            return suggested
        by_casefold = {field["name"].casefold(): field["name"] for field in fields}
        for preferred in preferences:
            if preferred.casefold() in by_casefold:
                return by_casefold[preferred.casefold()]
        return ""

    def _update_endpoint_margin_controls(self, _index: int = -1) -> None:
        mode = self._endpoint_margin_mode.currentData()
        self._endpoint_factor.setEnabled(mode == "factor")
        additive = mode == "additive"
        self._endpoint_additive_value.setEnabled(additive)
        self._endpoint_additive_unit.setEnabled(additive)

    def _on_pipe_layer_changed(self, _index: int = -1) -> None:
        pipe_layer = self._layer_by_id(self._pipe_layer_combo.currentData())
        pipe_id_fields = compatible_fields(pipe_layer, "pipe_id")
        length_fields = compatible_fields(pipe_layer, "length")
        suggested_pipe_id = self._suggested_or_preferred(
            "pipe_id_field", pipe_id_fields, ("id", "pipe_id", "pipeid", "dc_id")
        )
        suggested_length = self._suggested_or_preferred(
            "length_field", length_fields, ("length", "comprimento", "len")
        )
        self._replace_field_combo(
            self._pipe_id_combo, pipe_id_fields, suggested_pipe_id
        )
        self._replace_field_combo(
            self._length_combo, length_fields, suggested_length
        )
        self._populate_result_id_fields()

    def _on_pipe_id_changed(self, _index: int = -1) -> None:
        self._populate_result_id_fields()

    def _on_result_layer_changed(self, _index: int = -1) -> None:
        result_layer = self._layer_by_id(self._result_layer_combo.currentData())
        flow_fields = compatible_fields(result_layer, "flow")
        suggested_flow = self._suggested_or_preferred(
            "flow_field", flow_fields, ("flow", "vazao", "flow_unsig", "flow_sig")
        )
        self._replace_field_combo(self._flow_combo, flow_fields, suggested_flow)
        self._populate_result_id_fields()

    def _populate_result_id_fields(self) -> None:
        result_layer = self._layer_by_id(self._result_layer_combo.currentData())
        pipe_layer = self._layer_by_id(self._pipe_layer_combo.currentData())
        pipe_id_name = self._pipe_id_combo.currentData() or ""
        pipe_id_category = ""
        if pipe_layer is not None:
            for field in pipe_layer["fields"]:
                if field["name"] == pipe_id_name:
                    pipe_id_category = field["category"]
                    break
        result_id_fields = compatible_fields(
            result_layer, "result_id", pipe_id_category
        )
        suggested_result_id = self._suggested_or_preferred(
            "result_id_field",
            result_id_fields,
            ("id", "pipe_id", "pipeid", "link_id", "linkid", "dc_id"),
        )
        self._replace_field_combo(
            self._result_id_combo, result_id_fields, suggested_result_id
        )

    def _mark_mapping_changed(self, _index: int = -1) -> None:
        if hasattr(self, "_mapping_status"):
            self.mapping_changed.emit()
            self._mapping_status.setText(
                self.tr(
                    "Mapping changed. Review it and click “Store temporary mapping”."
                )
            )
            self.reset_validation(
                self.tr("Mapping changed. Store it again before validation.")
            )

    def _layer_by_id(self, layer_id: Optional[str]):
        for layer in self._mapping_inventory:
            if layer["id"] == layer_id:
                return layer
        return None

    def _suggested_or_preferred(
        self,
        suggestion_key: str,
        fields: Sequence[Mapping[str, Any]],
        preferences: Sequence[str],
    ) -> str:
        available = {field["name"] for field in fields}
        suggested = self._mapping_suggestions.get(suggestion_key, "")
        if suggested in available:
            return suggested
        by_lower_name = {field["name"].casefold(): field["name"] for field in fields}
        for preferred in preferences:
            if preferred in by_lower_name:
                return by_lower_name[preferred]
        return ""

    def _replace_field_combo(
        self,
        combo: QComboBox,
        fields: Sequence[Mapping[str, Any]],
        selected_name: str,
    ) -> None:
        self._replace_combo_items(
            combo,
            [
                (f"{field['name']} — {field['type']}", field["name"])
                for field in fields
            ],
            selected_name,
        )

    def _replace_combo_items(
        self,
        combo: QComboBox,
        items: Sequence[tuple],
        selected_data: str,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(self.tr("Not selected"), "")
        for label, data in items:
            combo.addItem(label, data)
        index = combo.findData(selected_data)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    @staticmethod
    def _numeric_input(minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(6)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setKeyboardTracking(False)
        return spin

    @staticmethod
    def _catalog_value(value: Any) -> str:
        if value is None or value == "":
            return "—"
        if isinstance(value, float):
            return f"{value:.12g}"
        return str(value)

    def _value_with_unit(self, value: Any, unit: Any) -> str:
        if value is None or value == "":
            return "—"
        display_units = {
            "per m": self.tr("per m"),
            "per ft": self.tr("per ft"),
        }
        display_unit = display_units.get(unit, unit)
        return f"{HydroSizerDialog._catalog_value(value)} {display_unit or ''}".strip()
