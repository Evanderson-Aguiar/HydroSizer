"""QGIS lifecycle, translated controller messages, and HydroSizer wiring."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QObject, QSettings, QTranslator
from qgis.PyQt.QtGui import QIcon

try:  # QAction moved from QtWidgets to QtGui in Qt 6.
    from qgis.PyQt.QtGui import QAction
except ImportError:  # QGIS 3 / Qt 5
    from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
    QProgressDialog,
)
from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsProject
from qgis.gui import QgisInterface

from . import __version__
from .catalog.repository import (
    CatalogConflictError,
    CatalogImportError,
    CatalogRepository,
)
from .catalog.validation import CatalogValidationError
from .core.basic_calculations import (
    calculate_basic_demo,
    format_basic_demo_report,
)
from .core.hazen_williams import (
    format_hazen_williams_report,
    size_single_segment_hazen_williams,
)
from .core.darcy_weisbach import (
    format_darcy_weisbach_report,
    size_single_segment_darcy_weisbach,
)
from .core.pressure import (
    evaluate_endpoint_pressure,
    format_endpoint_pressure_report,
)
from .core.batch_sizing import (
    format_batch_sizing_report,
    run_batch_sizing,
)
from .core.preview import (
    create_preview,
    export_preview_csv,
    filter_preview_rows,
    preview_pressure_unit,
    preview_pressure_value,
    set_preview_inclusion,
)
from .core.apply_plan import (
    build_apply_plan,
    format_apply_plan,
    revalidate_input_snapshot,
)
from .audit.audit_writer import write_audit_bundle
from .reports.calculation_memory import (
    build_calculation_memory,
    export_calculation_memory,
)
from .core.validation import format_validation_report, validate_mapped_data
from .integrations.environment_diagnostic import (
    collect_environment_diagnostic,
    format_environment_diagnostic,
    write_diagnostic_json,
)
from .integrations.layer_mapping import (
    collect_layer_mapping_inventory,
    suggest_layer_mapping,
)
from .integrations.layer_reader import read_mapped_records
from .integrations.layer_updater import apply_change_plan, read_apply_records
from .integrations.endpoint_pressure_mapping import (
    suggest_endpoint_pressure_mapping,
)
from .integrations.endpoint_pressure_reader import (
    read_endpoint_pressure_records,
)
from .integrations.qgisred_detector import (
    detect_qgisred_options_from_project,
    format_detection_result,
)
from .integrations.qgisred_options_reader import (
    format_options_inspection,
    inspect_options_dbf,
)
from .ui.main_dialog import HydroSizerDialog
from .ui.catalog_product_dialog import CatalogProductDialog
from .i18n.qt_translator import HydroSizerPortugueseTranslator
from .i18n.text import normalize_locale, translate_report_text

LOG_TAG = "HydroSizer"


def _info_level():
    """Return the information log level across supported QGIS 3 APIs."""
    message_level = getattr(Qgis, "MessageLevel", None)
    if message_level is not None:
        return message_level.Info
    return Qgis.Info


def _critical_level():
    """Return the critical log level across supported QGIS 3 APIs."""
    message_level = getattr(Qgis, "MessageLevel", None)
    if message_level is not None:
        return message_level.Critical
    return Qgis.Critical


class HydroSizerPlugin(QObject):
    """Register and manage the translated Stage 17 action and dialog."""

    MENU_TEXT = "&HydroSizer"

    def __init__(self, iface: QgisInterface) -> None:
        super().__init__()
        self.iface = iface
        self._translator: Optional[QTranslator] = None
        self._locale_name = "en"
        self._menu_text = self.MENU_TEXT
        self.action: Optional[QAction] = None
        self._dialog: Optional[HydroSizerDialog] = None
        self._last_diagnostic: Optional[Dict[str, Any]] = None
        self._last_qgisred_detection: Optional[Dict[str, Any]] = None
        self._mapping_inventory = []
        self._temporary_mapping: Optional[Dict[str, Any]] = None
        self._last_validation: Optional[Dict[str, Any]] = None
        self._catalog_repository: Optional[CatalogRepository] = None
        self._last_endpoint_pressure: Optional[Dict[str, Any]] = None
        self._last_batch_result: Optional[Dict[str, Any]] = None
        self._last_preview: Optional[Dict[str, Any]] = None
        self._last_apply_plan: Optional[Dict[str, Any]] = None
        self._last_applied_plan: Optional[Dict[str, Any]] = None
        self._install_translator()

    def initGui(self) -> None:  # noqa: N802 - required by QGIS
        """Add the plugin action to the Plugins menu and toolbar."""
        if self._translator is None:
            self._install_translator()
        icon_path = Path(__file__).parent / "icons" / "icon.png"
        self.action = QAction(
            QIcon(str(icon_path)), self.tr("HydroSizer"), self.iface.mainWindow()
        )
        self.action.setObjectName("HydroSizerAction")
        self.action.setToolTip(self.tr("Open HydroSizer"))
        self.action.triggered.connect(self.run)
        self._menu_text = self.tr(self.MENU_TEXT)
        self.iface.addPluginToMenu(self._menu_text, self.action)
        self.iface.addToolBarIcon(self.action)
        self._log(self.tr("HydroSizer {version} loaded.").format(version=__version__))

    def _install_translator(self) -> None:
        """Install the supported QGIS-locale translation before creating widgets."""
        configured = QSettings().value("locale/userLocale", "")
        self._locale_name = normalize_locale(
            configured or QLocale.system().name()
        )
        if self._locale_name == "en":
            return
        translator = HydroSizerPortugueseTranslator(self)
        QCoreApplication.installTranslator(translator)
        self._translator = translator

    def _localized_report(self, text: str) -> str:
        """Localize presentation-only multiline output without changing data."""
        return translate_report_text(text, self._locale_name)

    def _localized_error(self, error: Exception) -> str:
        """Localize a domain error only when it crosses the presentation boundary."""
        return self._localized_report(str(error))

    def _remove_translator(self) -> None:
        """Remove the plugin-owned translator without affecting QGIS translators."""
        if self._translator is not None:
            QCoreApplication.removeTranslator(self._translator)
            self._translator.deleteLater()
            self._translator = None

    @property
    def locale_name(self) -> str:
        """Return the active HydroSizer locale (``pt_BR`` or English fallback)."""
        return self._locale_name

    def unload(self) -> None:
        """Remove UI elements and release the dialog during plugin unload."""
        if self._dialog is not None:
            self._dialog.close()
            self._dialog.deleteLater()
            self._dialog = None
        self._catalog_repository = None
        self._last_endpoint_pressure = None
        self._last_batch_result = None
        self._last_preview = None
        self._last_apply_plan = None
        self._last_applied_plan = None

        if self.action is not None:
            self.iface.removePluginMenu(self._menu_text, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None

        self._log(self.tr("HydroSizer {version} unloaded.").format(version=__version__))
        self._remove_translator()

    def run(self) -> None:
        """Show the Stage 17 dialog and initialize persistent catalog access."""
        dialog_created = False
        if self._dialog is None:
            dialog_created = True
            self._dialog = HydroSizerDialog(
                version=__version__, parent=self.iface.mainWindow()
            )
            self._dialog.diagnostic_requested.connect(self._run_diagnostic)
            self._dialog.export_requested.connect(self._export_diagnostic)
            self._dialog.qgisred_detection_requested.connect(
                self._detect_qgisred_options
            )
            self._dialog.options_browse_requested.connect(
                self._browse_qgisred_options
            )
            self._dialog.mapping_refresh_requested.connect(
                self._refresh_layer_mapping
            )
            self._dialog.mapping_save_requested.connect(
                self._store_temporary_mapping
            )
            self._dialog.mapping_changed.connect(
                self._invalidate_temporary_mapping
            )
            self._dialog.validation_requested.connect(
                self._validate_temporary_mapping
            )
            self._dialog.pipe_highlight_requested.connect(
                self._highlight_pipe_problems
            )
            self._dialog.result_highlight_requested.connect(
                self._highlight_result_problems
            )
            self._dialog.basic_calculation_requested.connect(
                self._run_basic_calculation
            )
            self._dialog.catalog_refresh_requested.connect(self._refresh_catalog)
            self._dialog.catalog_add_requested.connect(self._add_catalog_product)
            self._dialog.catalog_edit_requested.connect(self._edit_catalog_product)
            self._dialog.catalog_duplicate_requested.connect(
                self._duplicate_catalog_product
            )
            self._dialog.catalog_toggle_active_requested.connect(
                self._toggle_catalog_product
            )
            self._dialog.catalog_delete_requested.connect(
                self._delete_catalog_product
            )
            self._dialog.catalog_import_requested.connect(self._import_catalog_csv)
            self._dialog.catalog_export_requested.connect(self._export_catalog_csv)
            self._dialog.catalog_validate_requested.connect(self._validate_catalog)
            self._dialog.hazen_williams_requested.connect(
                self._run_hazen_williams_demo
            )
            self._dialog.darcy_weisbach_requested.connect(
                self._run_darcy_weisbach_demo
            )
            self._dialog.sizing_criteria_changed.connect(
                self._invalidate_sizing_criteria
            )
            self._dialog.endpoint_refresh_requested.connect(
                self._refresh_endpoint_pressure_mapping
            )
            self._dialog.endpoint_evaluate_requested.connect(
                self._evaluate_endpoint_pressure
            )
            self._dialog.endpoint_highlight_pipe_requested.connect(
                self._highlight_endpoint_pipe
            )
            self._dialog.endpoint_highlight_nodes_requested.connect(
                self._highlight_endpoint_nodes
            )
            self._dialog.batch_sizing_requested.connect(self._run_batch_sizing)
            self._dialog.preview_filter_requested.connect(self._refresh_preview)
            self._dialog.preview_include_requested.connect(
                self._set_preview_inclusion
            )
            self._dialog.preview_map_selection_requested.connect(
                self._select_preview_on_map
            )
            self._dialog.preview_export_requested.connect(
                self._export_preview_csv
            )
            self._dialog.apply_configuration_changed.connect(
                self._invalidate_apply_plan
            )
            self._dialog.apply_audit_browse_requested.connect(
                self._browse_apply_audit_directory
            )
            self._dialog.apply_plan_requested.connect(self._prepare_apply_plan)
            self._dialog.apply_execute_requested.connect(self._execute_apply_plan)
            self._dialog.report_export_requested.connect(
                self._export_calculation_memory
            )
            self._dialog.finished.connect(self._on_dialog_closed)
            self._initialize_catalog()

        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()
        self._log(self.tr("HydroSizer dialog opened."))
        if dialog_created:
            self._detect_qgisred_options()
            self._refresh_layer_mapping()
            self._refresh_endpoint_pressure_mapping()
            project = QgsProject.instance()
            project_file = project.fileName()
            self._dialog.set_report_project_title(
                project.title()
                or (Path(project_file).stem if project_file else "")
            )

    def _run_diagnostic(self) -> None:
        """Collect and display read-only project and layer metadata."""
        try:
            report = collect_environment_diagnostic()
            details = self._localized_report(format_environment_diagnostic(report))
            self._last_diagnostic = report
            counts = report["layer_counts"]
            summary = self.tr(
                "Environment diagnostic completed: {total} layers "
                "({vector} spatial vector, {tables} tables)."
            ).format(
                total=counts["total"],
                vector=counts["vector"],
                tables=counts["table"],
            )
            self._log(summary)
            if self._dialog is not None:
                self._dialog.set_diagnostic_result(summary, details)
        except Exception as error:
            self._last_diagnostic = None
            message = self.tr(
                "Environment diagnostic failed: {error_type}: {error}"
            ).format(
                error_type=type(error).__name__,
                error=self._localized_error(error),
            )
            self._log(message, level=_critical_level())
            if self._dialog is not None:
                self._dialog.set_diagnostic_error(message)
                QMessageBox.critical(
                    self._dialog, self.tr("HydroSizer diagnostic"), message
                )

    def _export_diagnostic(self) -> None:
        """Ask for a destination and export the last diagnostic as JSON."""
        if self._last_diagnostic is None or self._dialog is None:
            return

        project_file = self._last_diagnostic["project"]["file"]
        initial_directory = (
            Path(project_file).parent if project_file else Path.home()
        )
        default_path = initial_directory / "hydrosizer_environment_diagnostic.json"
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self._dialog,
            self.tr("Export QGIS environment diagnostic"),
            str(default_path),
            self.tr("JSON files (*.json)"),
        )
        if not selected_path:
            return

        target = Path(selected_path)
        if target.suffix.lower() != ".json":
            target = target.with_suffix(".json")

        try:
            written_path = write_diagnostic_json(self._last_diagnostic, target)
        except Exception as error:
            message = self.tr(
                "Diagnostic export failed: {error_type}: {error}"
            ).format(
                error_type=type(error).__name__,
                error=self._localized_error(error),
            )
            self._log(message, level=_critical_level())
            QMessageBox.critical(self._dialog, self.tr("HydroSizer export"), message)
            return

        message = self.tr("Environment diagnostic exported to: {path}").format(
            path=written_path
        )
        self._log(message)
        QMessageBox.information(self._dialog, self.tr("HydroSizer export"), message)

    def _detect_qgisred_options(self) -> None:
        """Find and inspect the best local `*_Options.dbf` candidate."""
        if self._dialog is None:
            return
        try:
            detection = detect_qgisred_options_from_project()
            self._last_qgisred_detection = detection
            candidate = detection["recommended"]
            candidate_count = len(detection["candidates"])
            if candidate is None:
                summary = self.tr(
                    "QGISRed detection completed: no *_Options.dbf candidate "
                    "was found. Choose a file manually if available."
                )
            else:
                summary = self.tr(
                    "QGISRed detection completed: {count} candidate(s); "
                    "recommended network base is {network_base}."
                ).format(
                    count=candidate_count,
                    network_base=candidate["network_base"],
                )
            self._dialog.set_qgisred_detection_result(
                summary,
                self._localized_report(format_detection_result(detection)),
                candidate_found=candidate is not None,
            )
            self._log(summary)
            if candidate is not None:
                self._inspect_qgisred_options(Path(candidate["path"]))
        except Exception as error:
            self._last_qgisred_detection = None
            message = self.tr(
                "QGISRed detection failed: {error_type}: {error}"
            ).format(
                error_type=type(error).__name__,
                error=self._localized_error(error),
            )
            self._log(message, level=_critical_level())
            self._dialog.set_qgisred_error(message)
            QMessageBox.critical(
                self._dialog, self.tr("HydroSizer QGISRed detection"), message
            )

    def _browse_qgisred_options(self) -> None:
        """Allow explicit selection when automatic detection is unavailable."""
        if self._dialog is None:
            return
        project_directory = ""
        if self._last_qgisred_detection is not None:
            project_directory = self._last_qgisred_detection["project_directory"]
        initial_directory = Path(project_directory) if project_directory else Path.home()
        selected_path, _selected_filter = QFileDialog.getOpenFileName(
            self._dialog,
            self.tr("Choose QGISRed Options DBF"),
            str(initial_directory),
            self.tr("QGISRed options (*_Options.dbf);;DBF files (*.dbf)"),
        )
        if selected_path:
            self._inspect_qgisred_options(Path(selected_path))

    def _inspect_qgisred_options(self, options_path: Path) -> None:
        """Open and display one options DBF through the read-only adapter."""
        if self._dialog is None:
            return
        try:
            inspection = inspect_options_dbf(options_path)
            semantics = inspection["semantics"]
            summary = self.tr(
                "Options opened read-only: {name}; {count} records; "
                "units={units}; headloss={headloss}."
            ).format(
                name=Path(inspection["path"]).name,
                count=inspection["feature_count"],
                units=semantics["flow_units_code"] or self.tr("not detected"),
                headloss=semantics["headloss_code"] or self.tr("not detected"),
            )
            self._dialog.set_options_inspection_result(
                summary,
                self._localized_report(format_options_inspection(inspection)),
                semantics,
            )
            self._log(self.tr(
                "QGISRed options opened read-only: {path}; {count} records."
            ).format(path=inspection["path"], count=inspection["feature_count"]))
            self._log(self.tr(
                "Detected QGISRed settings: flow units={units}; headloss={headloss}."
            ).format(
                units=semantics["flow_units_code"] or self.tr("not detected"),
                headloss=semantics["headloss_code"] or self.tr("not detected"),
            ))
        except Exception as error:
            message = self.tr(
                "QGISRed options inspection failed: {error_type}: {error}"
            ).format(
                error_type=type(error).__name__,
                error=self._localized_error(error),
            )
            self._log(message, level=_critical_level())
            self._dialog.set_qgisred_error(message)
            QMessageBox.critical(
                self._dialog, self.tr("HydroSizer QGISRed options"), message
            )

    def _refresh_layer_mapping(self) -> None:
        """Refresh the metadata-only layer inventory and mapping suggestions."""
        if self._dialog is None:
            return
        try:
            inventory = collect_layer_mapping_inventory()
            suggestions = suggest_layer_mapping(inventory)
            self._mapping_inventory = inventory
            self._temporary_mapping = None
            self._last_validation = None
            self._dialog.set_mapping_inventory(inventory, suggestions)
            pipe_name = self._layer_name(suggestions["pipe_layer_id"])
            result_name = self._layer_name(suggestions["result_layer_id"])
            summary = self.tr(
                "Layer mapping inventory refreshed: {count} vector layer(s); "
                "suggested pipes={pipes}; results={results}."
            ).format(
                count=len(inventory),
                pipes=pipe_name or self.tr("none"),
                results=result_name or self.tr("none"),
            )
            self._log(summary)
        except Exception as error:
            self._mapping_inventory = []
            self._temporary_mapping = None
            self._last_validation = None
            message = self.tr(
                "Layer mapping inventory failed: {error_type}: {error}"
            ).format(
                error_type=type(error).__name__,
                error=self._localized_error(error),
            )
            self._log(message, level=_critical_level())
            self._dialog.set_mapping_error(message)
            QMessageBox.critical(
                self._dialog, self.tr("HydroSizer layer mapping"), message
            )

    def _store_temporary_mapping(self) -> None:
        """Store complete user selections in memory without reading features."""
        if self._dialog is None:
            return
        self._last_applied_plan = None
        configuration = self._dialog.mapping_configuration()
        required = {
            "pipe_layer_id": self.tr("pipe layer"),
            "pipe_id_field": self.tr("pipe ID field"),
            "length_field": self.tr("pipe length field"),
            "result_layer_id": self.tr("result layer/table"),
            "result_id_field": self.tr("result ID field"),
            "flow_field": self.tr("flow field"),
        }
        missing = [label for key, label in required.items() if not configuration[key]]
        if missing:
            self._temporary_mapping = None
            self._last_validation = None
            message = self.tr("Temporary mapping is incomplete: {fields}").format(
                fields=", ".join(missing)
            )
            self._dialog.set_mapping_error(message)
            self._dialog.reset_validation(
                self.tr(
                    "Mapping is incomplete. Store a complete mapping before validation."
                )
            )
            self._log(message)
            return

        pipe_layer = self._inventory_layer(configuration["pipe_layer_id"])
        result_layer = self._inventory_layer(configuration["result_layer_id"])
        configuration.update(
            {
                "project_file": QgsProject.instance().fileName() or "",
                "pipe_layer_source": pipe_layer["source"] if pipe_layer else "",
                "result_layer_source": (
                    result_layer["source"] if result_layer else ""
                ),
                "stored_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._temporary_mapping = configuration
        self._last_validation = None
        summary = self.tr(
            "Temporary mapping stored in memory. No features were read."
        )
        details = "\n".join(
            [
                self.tr("HydroSizer temporary mapping — Stage 4"),
                self.tr("Project: {project}").format(
                    project=configuration["project_file"] or self.tr("<unsaved>")
                ),
                self.tr("Pipe layer: {layer}").format(
                    layer=configuration["pipe_layer_name"]
                ),
                self.tr("Pipe ID field: {field}").format(
                    field=configuration["pipe_id_field"]
                ),
                self.tr("Length field: {field} (attribute only)").format(
                    field=configuration["length_field"]
                ),
                self.tr("Result layer/table: {layer}").format(
                    layer=configuration["result_layer_name"]
                ),
                self.tr("Result ID field: {field}").format(
                    field=configuration["result_id_field"]
                ),
                self.tr("Flow field: {field}").format(
                    field=configuration["flow_field"]
                ),
                self.tr("Flow unit code: {code}").format(
                    code=configuration["flow_unit_code"] or self.tr("<not set>")
                ),
                self.tr("Headloss code: {code}").format(
                    code=configuration["headloss_code"] or self.tr("<not set>")
                ),
                self.tr("Persistence: memory only; cleared on plugin reload"),
                self.tr("Feature access: none"),
                self.tr("Layer changes: none"),
            ]
        )
        self._dialog.set_mapping_saved(summary, details)
        self._log(self.tr(
            "Temporary layer mapping stored: pipes={pipe_layer}[{pipe_id}]; "
            "results={result_layer}[{result_id}]; flow={flow}; length={length}."
        ).format(
            pipe_layer=configuration["pipe_layer_name"],
            pipe_id=configuration["pipe_id_field"],
            result_layer=configuration["result_layer_name"],
            result_id=configuration["result_id_field"],
            flow=configuration["flow_field"],
            length=configuration["length_field"],
        ))

    def _invalidate_temporary_mapping(self) -> None:
        """Discard a stored mapping when the user changes any mapped control."""
        self._temporary_mapping = None
        self._last_validation = None
        self._last_batch_result = None
        self._last_preview = None
        self._last_apply_plan = None
        self._last_applied_plan = None
        if self._dialog is not None:
            self._dialog.set_preview_error(
                self.tr("Mapping changed. Run validation and Batch sizing again."),
                clear=True,
            )
            self._dialog.invalidate_apply_plan(
                self.tr("Mapping changed. Run validation and Batch sizing again.")
            )

    def _invalidate_sizing_criteria(self) -> None:
        """Discard results when project criteria or pressure settings change."""
        had_results = any(
            value is not None
            for value in (
                self._last_batch_result,
                self._last_preview,
                self._last_apply_plan,
                self._last_applied_plan,
            )
        )
        self._last_batch_result = None
        self._last_preview = None
        self._last_apply_plan = None
        self._last_applied_plan = None
        if self._dialog is not None and had_results:
            message = self.tr(
                "Project sizing criteria changed. Run sizing and review again."
            )
            self._dialog.set_batch_sizing_error(message)
            self._dialog.set_preview_error(message, clear=True)
            self._dialog.invalidate_apply_plan(message)
            self._dialog.set_report_error(message, clear=True)

    def _validate_temporary_mapping(self) -> None:
        """Read mapped attributes without geometry and build a validation report."""
        if self._dialog is None:
            return
        self._last_batch_result = None
        self._last_preview = None
        self._last_apply_plan = None
        self._last_applied_plan = None
        self._dialog.set_preview_error(
            self.tr(
                "Data validation rerun. Run Batch sizing again to create a preview."
            ),
            clear=True,
        )
        self._dialog.invalidate_apply_plan(
            self.tr("Data validation rerun. Run Batch sizing again.")
        )
        if self._temporary_mapping is None:
            message = self.tr(
                "No stored mapping is available. Store the mapping first."
            )
            self._dialog.set_validation_error(message)
            self._log(message)
            return
        try:
            dataset = read_mapped_records(self._temporary_mapping)
            result = validate_mapped_data(dataset)
            report = self._localized_report(format_validation_report(dataset, result))
            self._last_validation = {"dataset": dataset, "result": result}
            summary_data = result["summary"]
            if result["valid_for_sizing"] and result["warning_count"]:
                status = self.tr("passed with warnings")
            elif result["valid_for_sizing"]:
                status = self.tr("passed")
            else:
                status = self.tr("failed")
            summary = self.tr(
                "Validation {status}: {errors} error(s), {warnings} warning(s), "
                "{matched} matched ID(s)."
            ).format(
                status=status,
                errors=result["error_count"],
                warnings=result["warning_count"],
                matched=summary_data["matched_ids"],
            )
            self._dialog.set_validation_result(
                summary,
                report,
                len(result["pipe_problem_fids"]),
                len(result["result_problem_fids"]),
            )
            self._log(self.tr(
                "Data validation completed: pipes={pipes}; results={results}; "
                "matched={matched}; errors={errors}; warnings={warnings}."
            ).format(
                pipes=summary_data["pipe_records"],
                results=summary_data["result_records"],
                matched=summary_data["matched_ids"],
                errors=result["error_count"],
                warnings=result["warning_count"],
            ))
        except Exception as error:
            self._last_validation = None
            message = self.tr(
                "Data validation failed: {error_type}: {error}"
            ).format(
                error_type=type(error).__name__,
                error=self._localized_error(error),
            )
            self._log(message, level=_critical_level())
            self._dialog.set_validation_error(message)
            QMessageBox.critical(
                self._dialog, self.tr("HydroSizer data validation"), message
            )

    def _highlight_pipe_problems(self) -> None:
        self._highlight_validation_problems("pipe")

    def _highlight_result_problems(self) -> None:
        self._highlight_validation_problems("result")

    def _highlight_validation_problems(self, entity: str) -> None:
        """Select problem FIDs on explicit request without changing attributes."""
        if self._last_validation is None or self._dialog is None:
            return
        dataset = self._last_validation["dataset"]
        result = self._last_validation["result"]
        if entity == "pipe":
            layer_id = dataset["pipe_layer_id"]
            fids = result["pipe_problem_fids"]
        else:
            layer_id = dataset["result_layer_id"]
            fids = result["result_problem_fids"]
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            entity_label = self.tr("pipe") if entity == "pipe" else self.tr("result")
            message = self.tr(
                "Cannot select {entity} problems: the layer no longer exists."
            ).format(entity=entity_label)
            self._log(message, level=_critical_level())
            self._dialog.set_validation_error(message)
            return
        layer.selectByIds(fids)
        if fids and layer.isSpatial():
            self.iface.mapCanvas().zoomToSelected(layer)
        entity_label = self.tr("pipe") if entity == "pipe" else self.tr("result")
        self._log(self.tr(
            "Selected {count} problematic {entity} feature(s) on layer {layer}; "
            "attributes unchanged."
        ).format(count=len(fids), entity=entity_label, layer=layer.name()))

    def _run_basic_calculation(self) -> None:
        """Run the isolated Stage 6 calculation using manual dialog inputs."""
        if self._dialog is None:
            return
        inputs = self._dialog.basic_calculation_inputs()
        try:
            result = calculate_basic_demo(**inputs)
        except ValueError as error:
            message = self.tr("Basic calculation input error: {error}").format(
                error=self._localized_error(error)
            )
            self._dialog.set_basic_calculation_error(message)
            self._log(message)
            return

        summary = self.tr(
            "Basic calculation completed: velocity={velocity:.6g} m/s; "
            "segment cost={cost:.6g}."
        ).format(
            velocity=result["velocity_m_s"], cost=result["segment_cost"]
        )
        self._dialog.set_basic_calculation_result(
            summary,
            self._localized_report(format_basic_demo_report(inputs, result)),
        )
        self._log(self.tr(
            "Basic calculation completed without layer access: |Q|={flow:.12g} "
            "m³/s; Di={diameter:.12g} m; V={velocity:.12g} m/s; cost={cost:.12g}."
        ).format(
            flow=result["flow_m3_s_magnitude"],
            diameter=result["diameter_m"],
            velocity=result["velocity_m_s"],
            cost=result["segment_cost"],
        ))

    def _initialize_catalog(self) -> None:
        """Create or open the HydroSizer-owned catalog in the QGIS profile."""
        if self._dialog is None:
            return
        try:
            catalog_path = (
                Path(QgsApplication.qgisSettingsDirPath())
                / "HydroSizer"
                / "catalog.sqlite"
            )
            repository = CatalogRepository(catalog_path)
            repository.initialize()
            seed_path = (
                Path(__file__).resolve().parent
                / "hydrosizer_catalog_materials.csv"
            )
            seeded_count, seed_warnings = repository.seed_from_csv_if_empty(
                seed_path
            )
            self._catalog_repository = repository
            self._refresh_catalog()
            self._log(self.tr("HydroSizer catalog initialized: {path}").format(
                path=catalog_path
            ))
            if seeded_count:
                self._log(self.tr(
                    "HydroSizer catalog seeded: {count} bundled product(s); "
                    "{warnings} validation warning(s)."
                ).format(
                    count=seeded_count,
                    warnings=len(seed_warnings),
                ))
        except Exception as error:
            self._catalog_repository = None
            self._handle_catalog_error(self.tr("Catalog initialization failed"), error)

    def _run_hazen_williams_demo(self) -> None:
        """Evaluate one manual segment without reading or changing layers."""
        if self._dialog is None or self._catalog_repository is None:
            return
        try:
            products = self._catalog_repository.list_products(
                active_only=True,
                sort_by="nominal_diameter",
            )
            result = size_single_segment_hazen_williams(
                products=products,
                **self._dialog.hazen_williams_inputs(),
            )
        except ValueError as error:
            message = self.tr("Hazen–Williams input error: {error}").format(
                error=self._localized_error(error)
            )
            self._dialog.set_hazen_williams_error(message)
            self._log(message)
            return
        except Exception as error:
            message = self.tr("Hazen–Williams calculation failed: {error}").format(
                error=self._localized_error(error)
            )
            self._dialog.set_hazen_williams_error(message)
            self._log(message, level=_critical_level())
            return

        selected = result["selected"]
        if selected is None:
            summary = self.tr(
                "Hazen–Williams demonstration completed: {count} active product(s) "
                "considered; no admissible product found."
            ).format(count=len(result["evaluated"]))
        else:
            summary = self.tr(
                "Hazen–Williams demonstration completed: {count} active product(s) "
                "considered; selected catalog ID {catalog_id} "
                "({material}/{product})."
            ).format(
                count=len(result["evaluated"]),
                catalog_id=selected["catalog_id"],
                material=selected["material_code"],
                product=selected["product_code"],
            )
        self._dialog.set_hazen_williams_result(
            summary,
            self._localized_report(format_hazen_williams_report(result)),
        )
        self._log(self.tr(
            "{summary} No project layer was accessed or changed."
        ).format(summary=summary))

    def _refresh_catalog(self) -> None:
        """Refresh the filtered product table without changing the catalog."""
        if self._dialog is None or self._catalog_repository is None:
            return
        try:
            filters = self._dialog.catalog_filters()
            products = self._catalog_repository.list_products(**filters)
            active_products = self._catalog_repository.list_products(
                active_only=True,
                sort_by="material_code",
            )
            self._dialog.set_catalog_products(
                products,
                str(self._catalog_repository.database_path),
            )
            self._dialog.set_project_materials(active_products)
            self._log(self.tr("Catalog view refreshed: {count} product(s).").format(
                count=len(products)
            ))
        except Exception as error:
            self._handle_catalog_error(self.tr("Catalog refresh failed"), error)

    def _run_darcy_weisbach_demo(self) -> None:
        """Evaluate one manual segment without reading or changing layers."""
        if self._dialog is None or self._catalog_repository is None:
            return
        try:
            products = self._catalog_repository.list_products(
                active_only=True,
                sort_by="nominal_diameter",
            )
            result = size_single_segment_darcy_weisbach(
                products=products,
                **self._dialog.darcy_weisbach_inputs(),
            )
        except ValueError as error:
            message = self.tr("Darcy–Weisbach input error: {error}").format(
                error=self._localized_error(error)
            )
            self._dialog.set_darcy_weisbach_error(message)
            self._log(message)
            return
        except Exception as error:
            message = self.tr("Darcy–Weisbach calculation failed: {error}").format(
                error=self._localized_error(error)
            )
            self._dialog.set_darcy_weisbach_error(message)
            self._log(message, level=_critical_level())
            return

        selected = result["selected"]
        if selected is None:
            summary = self.tr(
                "Darcy–Weisbach demonstration completed: {count} active product(s) "
                "considered; no admissible product found."
            ).format(count=len(result["evaluated"]))
        else:
            summary = self.tr(
                "Darcy–Weisbach demonstration completed: {count} active product(s) "
                "considered; selected catalog ID {catalog_id} "
                "({material}/{product})."
            ).format(
                count=len(result["evaluated"]),
                catalog_id=selected["catalog_id"],
                material=selected["material_code"],
                product=selected["product_code"],
            )
        self._dialog.set_darcy_weisbach_result(
            summary,
            self._localized_report(format_darcy_weisbach_report(result)),
        )
        self._log(self.tr(
            "{summary} No project layer was accessed or changed."
        ).format(summary=summary))

    def _refresh_endpoint_pressure_mapping(self) -> None:
        """Refresh Stage 11 layer metadata and active products without features."""
        if self._dialog is None or self._catalog_repository is None:
            return
        try:
            inventory = collect_layer_mapping_inventory()
            suggestions = suggest_endpoint_pressure_mapping(inventory)
            products = self._catalog_repository.list_products(
                active_only=True,
                sort_by="nominal_diameter",
            )
            self._mapping_inventory = inventory
            self._last_endpoint_pressure = None
            self._dialog.set_endpoint_pressure_inventory(
                inventory,
                suggestions,
                products,
            )
            self._log(self.tr(
                "Endpoint pressure mapping refreshed without feature access: "
                "vectors={vectors}; active products={products}; pipe layer={pipe}; "
                "node results={nodes}."
            ).format(
                vectors=len(inventory),
                products=len(products),
                pipe=self._layer_name(suggestions["pipe_layer_id"])
                or self.tr("none"),
                nodes=self._layer_name(suggestions["node_layer_id"])
                or self.tr("none"),
            ))
        except Exception as error:
            self._last_endpoint_pressure = None
            message = self.tr("Endpoint pressure mapping failed: {error}").format(
                error=self._localized_error(error)
            )
            self._dialog.set_endpoint_mapping_error(message)
            self._log(message, level=_critical_level())

    def _evaluate_endpoint_pressure(self) -> None:
        """Resolve one pipe's endpoints and verify one product pressure rating."""
        if self._dialog is None or self._catalog_repository is None:
            return
        configuration = self._dialog.endpoint_pressure_configuration()
        required = {
            "pipe_layer_id": self.tr("pipe layer"),
            "pipe_id_field": self.tr("pipe ID field"),
            "node_layer_id": self.tr("node result layer/table"),
            "node_id_field": self.tr("node result ID field"),
            "pressure_field": self.tr("pressure field"),
            "requested_pipe_id": self.tr("pipe ID to evaluate"),
            "catalog_id": self.tr("catalog product"),
        }
        missing = [
            label for key, label in required.items() if not configuration.get(key)
        ]
        if missing:
            message = self.tr(
                "Endpoint pressure configuration is incomplete: {fields}"
            ).format(fields=", ".join(missing))
            self._last_endpoint_pressure = None
            self._dialog.set_endpoint_pressure_error(message)
            self._log(message)
            return
        pipe_layer = self._inventory_layer(configuration["pipe_layer_id"])
        node_layer = self._inventory_layer(configuration["node_layer_id"])
        configuration["pipe_layer_source"] = (
            pipe_layer["source"] if pipe_layer else ""
        )
        configuration["node_layer_source"] = (
            node_layer["source"] if node_layer else ""
        )
        try:
            product = self._catalog_repository.get_product(
                int(configuration["catalog_id"])
            )
            if product is None or not product["active"]:
                raise ValueError(
                    self.tr("selected catalog product is unavailable or inactive")
                )
            dataset = read_endpoint_pressure_records(configuration)
            result = evaluate_endpoint_pressure(
                dataset=dataset,
                requested_pipe_id=configuration["requested_pipe_id"],
                pressure_unit=configuration["pressure_unit"],
                margin_mode=configuration["margin_mode"],
                safety_factor=configuration["safety_factor"],
                additive_margin_value=configuration["additive_margin_value"],
                additive_margin_unit=configuration["additive_margin_unit"],
                product=product,
            )
            report = self._localized_report(
                format_endpoint_pressure_report(dataset, result)
            )
        except ValueError as error:
            self._last_endpoint_pressure = None
            message = self.tr(
                "Endpoint pressure verification input error: {error}"
            ).format(error=self._localized_error(error))
            self._dialog.set_endpoint_pressure_error(message)
            self._log(message)
            return
        except Exception as error:
            self._last_endpoint_pressure = None
            message = self.tr(
                "Endpoint pressure verification failed: {error}"
            ).format(error=self._localized_error(error))
            self._dialog.set_endpoint_pressure_error(message)
            self._log(message, level=_critical_level())
            return

        self._last_endpoint_pressure = {"dataset": dataset, "result": result}
        summary = self.tr(
            "Endpoint pressure verification {status}: pipe={pipe}; "
            "initial={initial:.12g} Pa; final={final:.12g} Pa; "
            "verification={verification:.12g} Pa; allowable={allowable:.12g} Pa."
        ).format(
            status=result["status"],
            pipe=result["pipe_id"],
            initial=result["initial_pressure_pa"],
            final=result["final_pressure_pa"],
            verification=result["verification_pressure_pa"],
            allowable=result["allowable_pressure_pa"],
        )
        self._dialog.set_endpoint_pressure_result(summary, report)
        self._log(self.tr(
            "{summary} Endpoint and node geometries were read for topology "
            "matching; layers were not changed."
        ).format(summary=summary))

    def _highlight_endpoint_pipe(self) -> None:
        """Select the verified pipe without changing its attributes."""
        if self._last_endpoint_pressure is None:
            return
        dataset = self._last_endpoint_pressure["dataset"]
        result = self._last_endpoint_pressure["result"]
        self._select_and_zoom(
            dataset["pipe_layer_id"],
            [result["pipe_fid"]],
            self.tr("verified pipe"),
        )

    def _highlight_endpoint_nodes(self) -> None:
        """Select both resolved node-result features without editing them."""
        if self._last_endpoint_pressure is None:
            return
        dataset = self._last_endpoint_pressure["dataset"]
        result = self._last_endpoint_pressure["result"]
        fids = sorted(
            set(result["initial_node_fids"] + result["final_node_fids"])
        )
        self._select_and_zoom(
            dataset["node_layer_id"],
            fids,
            self.tr("endpoint pressure nodes"),
        )

    def _select_and_zoom(self, layer_id: str, fids: list, label: str) -> None:
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            message = self.tr(
                "Cannot select {label}: mapped layer no longer exists."
            ).format(label=label)
            if self._dialog is not None:
                self._dialog.set_endpoint_pressure_error(message)
            self._log(message, level=_critical_level())
            return
        layer.selectByIds(fids)
        if fids and layer.isSpatial():
            self.iface.mapCanvas().zoomToSelected(layer)
        self._log(self.tr(
            "Selected {count} {label} feature(s); attributes unchanged."
        ).format(count=len(fids), label=label))

    def _run_batch_sizing(self) -> None:
        """Size mapped pipes into memory with cooperative cancellation."""
        if self._dialog is None or self._catalog_repository is None:
            return
        self._last_batch_result = None
        self._last_preview = None
        self._last_apply_plan = None
        self._last_applied_plan = None
        self._dialog.set_preview_error(
            self.tr("Batch sizing is running; the previous preview was cleared."),
            clear=True,
        )
        self._dialog.invalidate_apply_plan(
            self.tr("Batch sizing is running; the previous apply plan was cleared.")
        )
        if self._temporary_mapping is None or self._last_validation is None:
            message = self.tr(
                "Sizing requires completed layer mapping and data validation in "
                "the Project step."
            )
            self._dialog.set_batch_sizing_error(message)
            self._log(message)
            return
        validation = self._last_validation["result"]
        if not validation["valid_for_sizing"]:
            message = self.tr(
                "Batch sizing is blocked because Data validation failed."
            )
            self._dialog.set_batch_sizing_error(message)
            self._log(message)
            return
        flow_unit = self._temporary_mapping.get("flow_unit_code", "")
        if not flow_unit:
            message = self.tr(
                "Sizing requires a reviewed QGISRed flow unit before the project "
                "mapping is stored."
            )
            self._dialog.set_batch_sizing_error(message)
            self._log(message)
            return

        batch_configuration = self._dialog.batch_sizing_configuration()
        criteria = self._dialog.combined_sizing_inputs()
        dataset = self._last_validation["dataset"]
        pipe_layer = QgsProject.instance().mapLayer(dataset["pipe_layer_id"])
        if pipe_layer is None:
            message = self.tr("Batch sizing pipe layer no longer exists.")
            self._dialog.set_batch_sizing_error(message)
            self._log(message, level=_critical_level())
            return
        selected_fids = list(pipe_layer.selectedFeatureIds())

        endpoint_dataset = None
        endpoint_settings = None
        try:
            if criteria["pressure_enabled"]:
                endpoint_settings = self._dialog.endpoint_pressure_configuration()
                endpoint_required = {
                    "pipe_layer_id": self.tr("endpoint pipe layer"),
                    "pipe_id_field": self.tr("endpoint pipe ID field"),
                    "node_layer_id": self.tr("node result layer/table"),
                    "node_id_field": self.tr("node result ID field"),
                    "pressure_field": self.tr("pressure field"),
                }
                missing = [
                    label
                    for key, label in endpoint_required.items()
                    if not endpoint_settings.get(key)
                ]
                if missing:
                    raise ValueError(self.tr(
                        "endpoint pressure mapping is incomplete: {fields}"
                    ).format(fields=", ".join(missing)))
                if endpoint_settings["pipe_layer_id"] != dataset["pipe_layer_id"]:
                    raise ValueError(self.tr(
                        "batch and endpoint mappings must use the same pipe layer"
                    ))
                if endpoint_settings["pipe_id_field"] != dataset["pipe_id_field"]:
                    raise ValueError(self.tr(
                        "batch and endpoint mappings must use the same pipe ID field"
                    ))
                endpoint_pipe = self._inventory_layer(
                    endpoint_settings["pipe_layer_id"]
                )
                endpoint_nodes = self._inventory_layer(
                    endpoint_settings["node_layer_id"]
                )
                endpoint_settings["pipe_layer_source"] = (
                    endpoint_pipe["source"] if endpoint_pipe else ""
                )
                endpoint_settings["node_layer_source"] = (
                    endpoint_nodes["source"] if endpoint_nodes else ""
                )
                endpoint_dataset = read_endpoint_pressure_records(
                    endpoint_settings
                )
            products = self._catalog_repository.list_products(
                active_only=True,
                sort_by="nominal_diameter",
            )
        except (ValueError, OSError) as error:
            message = self.tr("Batch sizing prerequisite error: {error}").format(
                error=self._localized_error(error)
            )
            self._last_batch_result = None
            self._dialog.set_batch_sizing_error(message)
            self._log(message)
            return
        except Exception as error:
            message = self.tr("Batch sizing preparation failed: {error}").format(
                error=self._localized_error(error)
            )
            self._last_batch_result = None
            self._dialog.set_batch_sizing_error(message)
            self._log(message, level=_critical_level())
            return

        candidate_records = dataset["pipe_records"]
        if batch_configuration["selection_mode"] == "selected":
            selected_set = set(selected_fids)
            candidate_records = [
                record
                for record in candidate_records
                if record["fid"] in selected_set
            ]
        total = len(candidate_records)
        progress = QProgressDialog(
            self.tr("Preparing memory-only sizing…"),
            self.tr("Cancel"),
            0,
            max(total, 1),
            self._dialog,
        )
        progress.setWindowTitle(self.tr("HydroSizer batch sizing"))
        progress.setMinimumDuration(0)
        progress.setValue(0)
        progress.show()
        QApplication.processEvents()

        def update_progress(done: int, count: int, pipe_id: str) -> None:
            progress.setMaximum(max(count, 1))
            progress.setLabelText(
                self.tr(
                    "Sizing pipe {pipe_id}: {done} of {count} processed"
                ).format(pipe_id=pipe_id, done=done, count=count)
            )
            progress.setValue(done)
            QApplication.processEvents()

        try:
            result = run_batch_sizing(
                validation_dataset=dataset,
                products=products,
                criteria=criteria,
                flow_unit=flow_unit,
                length_unit=batch_configuration["length_unit"],
                selection_mode=batch_configuration["selection_mode"],
                selected_pipe_fids=selected_fids,
                endpoint_dataset=endpoint_dataset,
                endpoint_settings=endpoint_settings,
                progress_callback=update_progress,
                cancel_callback=progress.wasCanceled,
            )
        except ValueError as error:
            progress.close()
            message = self.tr("Batch sizing input error: {error}").format(
                error=self._localized_error(error)
            )
            self._last_batch_result = None
            self._dialog.set_batch_sizing_error(message)
            self._log(message)
            return
        except Exception as error:
            progress.close()
            message = self.tr("Batch sizing failed: {error}").format(
                error=self._localized_error(error)
            )
            self._last_batch_result = None
            self._dialog.set_batch_sizing_error(message)
            self._log(message, level=_critical_level())
            return
        progress.close()

        self._last_batch_result = result
        self._last_preview = create_preview(result)
        self._last_preview["pipe_layer_id"] = dataset["pipe_layer_id"]
        pipe_inventory = self._inventory_layer(dataset["pipe_layer_id"])
        self._dialog.set_apply_layer_fields(
            pipe_inventory["fields"] if pipe_inventory else [],
            criteria["hydraulic_method"],
        )
        suggested_audit = self._suggest_audit_directory(
            self._temporary_mapping.get("pipe_layer_source", "")
        )
        if suggested_audit:
            self._dialog.set_apply_audit_directory(str(suggested_audit))
        summary_data = result["summary"]
        state = self.tr("cancelled safely") if result["cancelled"] else self.tr("completed")
        summary = self.tr(
            "Batch sizing {state}: {processed} of {requested} pipe(s) processed; "
            "sized={sized}; warnings={warnings}; no solution={no_solution}; "
            "insufficient={insufficient}."
        ).format(
            state=state,
            processed=result["processed_count"],
            requested=result["total_requested"],
            sized=summary_data["sized"],
            warnings=summary_data["sized_with_warning"],
            no_solution=summary_data["no_solution"],
            insufficient=summary_data["insufficient_data"],
        )
        self._dialog.set_batch_sizing_result(
            summary,
            self._localized_report(format_batch_sizing_report(result)),
        )
        self._refresh_preview(
            self.tr("Preview snapshot created from the latest batch.")
        )
        self._log(self.tr(
            "{summary} Results are memory-only; layers unchanged."
        ).format(summary=summary))

    def _refresh_preview(self, operation_message: str = "") -> None:
        """Apply Stage 13 filters to the current in-memory snapshot."""
        if self._dialog is None:
            return
        if self._last_preview is None:
            self._dialog.set_preview_error(
                self.tr("No preview is available. Run Batch sizing first."),
                clear=True,
            )
            return
        try:
            filters = self._dialog.preview_filters()
            rows = filter_preview_rows(self._last_preview, **filters)
            all_rows = self._last_preview.get("rows", [])
            configured_unit = self._dialog.endpoint_pressure_configuration().get(
                "pressure_unit", "Pa"
            )
            pressure_unit = preview_pressure_unit(all_rows, configured_unit)
            display_rows = []
            for row in rows:
                display_row = dict(row)
                display_row["verification_pressure_display"] = (
                    preview_pressure_value(row, pressure_unit)
                )
                display_row["messages_display"] = self._localized_report(
                    "; ".join(str(message) for message in row.get("messages") or [])
                )
                display_rows.append(display_row)
            self._dialog.set_preview_rows(
                display_rows,
                self._last_preview["summary"],
                operation_message,
                pressure_unit,
            )
        except ValueError as error:
            message = self.tr("Preview filter error: {error}").format(
                error=self._localized_error(error)
            )
            self._dialog.set_preview_error(message)
            self._log(message)

    def _set_preview_inclusion(self, included: bool) -> None:
        """Include or exclude selected eligible preview rows in memory only."""
        if self._dialog is None or self._last_preview is None:
            if self._dialog is not None:
                self._dialog.set_preview_error(
                    self.tr("No preview is available. Run Batch sizing first.")
                )
            return
        try:
            fids = self._dialog.selected_preview_fids()
            result = set_preview_inclusion(self._last_preview, fids, included)
        except ValueError as error:
            self._dialog.set_preview_error(
                self.tr("Preview inclusion error: {error}").format(
                    error=self._localized_error(error)
                )
            )
            return
        action = self.tr("included") if included else self.tr("excluded")
        message = self.tr(
            "{changed} row(s) {action}; {ineligible} ineligible row(s) unchanged."
        ).format(
            changed=result["changed"],
            action=action,
            ineligible=result["ineligible"],
        )
        self._invalidate_apply_plan(
            self.tr("Preview inclusion changed. Prepare the apply plan again.")
        )
        self._last_applied_plan = None
        self._refresh_preview(message)
        self._log(self.tr(
            "Preview inclusion updated: requested={requested}; changed={changed}; "
            "ineligible={ineligible}. Plugin memory only; layers unchanged."
        ).format(
            requested=result["requested"],
            changed=result["changed"],
            ineligible=result["ineligible"],
        ))

    def _select_preview_on_map(self) -> None:
        """Select highlighted preview rows in the mapped pipe layer."""
        if self._dialog is None or self._last_preview is None:
            if self._dialog is not None:
                self._dialog.set_preview_error(
                    self.tr("No preview is available. Run Batch sizing first.")
                )
            return
        fids = self._dialog.selected_preview_fids()
        if not fids:
            self._dialog.set_preview_error(
                self.tr("Select one or more preview table rows first.")
            )
            return
        layer = QgsProject.instance().mapLayer(
            self._last_preview.get("pipe_layer_id", "")
        )
        if layer is None:
            message = self.tr(
                "Cannot select preview rows: the mapped pipe layer is missing."
            )
            self._dialog.set_preview_error(message)
            self._log(message, level=_critical_level())
            return
        layer.selectByIds(fids)
        if layer.isSpatial():
            self.iface.mapCanvas().zoomToSelected(layer)
        message = self.tr(
            "Selected {count} preview pipe(s) on the map."
        ).format(count=len(fids))
        self._refresh_preview(message)
        self._log(self.tr(
            "{message} Attributes and geometries unchanged."
        ).format(message=message))

    def _export_preview_csv(self) -> None:
        """Atomically export the currently displayed Stage 13 rows."""
        if self._dialog is None or self._last_preview is None:
            if self._dialog is not None:
                self._dialog.set_preview_error(
                    self.tr("No preview is available. Run Batch sizing first.")
                )
            return
        displayed_fids = self._dialog.displayed_preview_fids()
        rows_by_fid = {
            int(row["pipe_fid"]): row for row in self._last_preview["rows"]
        }
        rows = [
            rows_by_fid[fid]
            for fid in displayed_fids
            if fid in rows_by_fid
        ]
        project_file = QgsProject.instance().fileName()
        destination = (
            Path(project_file).parent
            if project_file
            else Path.home()
        ) / "hydrosizer_sizing_preview.csv"
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self._dialog,
            self.tr("Export HydroSizer sizing preview CSV"),
            str(destination),
            self.tr("CSV files (*.csv)"),
        )
        if not selected_path:
            return
        target = Path(selected_path)
        if target.suffix.casefold() != ".csv":
            target = target.with_suffix(".csv")
        try:
            configured_unit = self._dialog.endpoint_pressure_configuration().get(
                "pressure_unit", "Pa"
            )
            pressure_unit = preview_pressure_unit(
                self._last_preview.get("rows", []),
                configured_unit,
            )
            count = export_preview_csv(target, rows, pressure_unit)
        except (OSError, ValueError) as error:
            message = self.tr("Preview CSV export failed: {error}").format(
                error=self._localized_error(error)
            )
            self._dialog.set_preview_error(message)
            self._log(message, level=_critical_level())
            return
        message = self.tr(
            "Exported {count} displayed preview row(s) to {target}."
        ).format(count=count, target=target)
        self._refresh_preview(message)
        self._log(self.tr(
            "{message} Export only; project layers and catalog unchanged."
        ).format(message=message))

    def _export_calculation_memory(self) -> None:
        """Export the Stage 17 localized HTML and CSV memory snapshot."""
        if self._dialog is None:
            return
        if (
            self._last_batch_result is None
            or self._last_preview is None
            or self._temporary_mapping is None
        ):
            self._dialog.set_report_error(
                self.tr(
                    "No current sizing is available. Complete Sizing and review "
                    "the included pipe results."
                ),
                clear=True,
            )
            return
        project = QgsProject.instance()
        project_file = project.fileName()
        destination = (
            Path(project_file).parent if project_file else Path.home()
        ) / "memoria_calculo_hidraulico.html"
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self._dialog,
            self.tr("Export hydraulic calculation memory"),
            str(destination),
            self.tr("HTML files (*.html)"),
        )
        if not selected_path:
            return
        target = Path(selected_path)
        if target.suffix.casefold() != ".html":
            target = target.with_suffix(".html")
        csv_target = target.with_suffix(".csv")
        if csv_target.exists():
            standard = getattr(QMessageBox, "StandardButton", None)
            yes = standard.Yes if standard else QMessageBox.Yes
            no = standard.No if standard else QMessageBox.No
            response = QMessageBox.question(
                self._dialog,
                self.tr("Replace calculation memory"),
                self.tr(
                    "The associated CSV spreadsheet already exists:\n{path}\n\n"
                    "Do you want to replace the HTML and CSV files?"
                ).format(path=csv_target),
                yes | no,
                no,
            )
            if response != yes:
                return
        try:
            metadata = self._calculation_memory_metadata()
            model = build_calculation_memory(
                self._last_batch_result,
                self._last_preview,
                metadata,
                applied_plan=self._last_applied_plan,
            )
            result = export_calculation_memory(target, model)
        except (OSError, ValueError, KeyError) as error:
            message = self.tr(
                "Calculation memory export failed: {error}"
            ).format(error=self._localized_error(error))
            self._dialog.set_report_error(message)
            self._log(message, level=_critical_level())
            return
        except Exception as error:
            message = self.tr(
                "Calculation memory export failed: {error_type}: {error}"
            ).format(
                error_type=type(error).__name__,
                error=self._localized_error(error),
            )
            self._dialog.set_report_error(message)
            self._log(message, level=_critical_level())
            return
        summary = self.tr(
            "Calculation memory issued: {rows} pipe(s), HTML and CSV spreadsheet."
        ).format(rows=result["rows"])
        details = "\n".join(
            (
                self.tr("Hydraulic calculation memory — Stage 15"),
                self.tr("Operation: export only; layers and catalog unchanged"),
                "",
                self.tr("HTML: {path}").format(path=result["html_path"]),
                self.tr("CSV spreadsheet: {path}").format(
                    path=result["csv_path"]
                ),
                self.tr("Pipes: {count}").format(count=result["rows"]),
                self.tr("Included: {count}").format(
                    count=model["summary"]["included_count"]
                ),
                self.tr("No solution: {count}").format(
                    count=model["summary"]["no_solution_count"]
                ),
                self.tr("Insufficient data: {count}").format(
                    count=model["summary"]["insufficient_count"]
                ),
            )
        )
        self._dialog.set_report_result(summary, details)
        self._log(self.tr(
            "{summary} HTML={html}; CSV={csv}. No layers or catalog were changed."
        ).format(
            summary=summary,
            html=result["html_path"],
            csv=result["csv_path"],
        ))

    def _calculation_memory_metadata(self) -> Dict[str, Any]:
        project = QgsProject.instance()
        project_file = project.fileName()
        criteria = dict(self._last_batch_result.get("criteria", {}))
        endpoint = self._dialog.endpoint_pressure_configuration()
        node_layer = self._inventory_layer(endpoint.get("node_layer_id", ""))
        mapping = {
            "pipe_layer_name": self._temporary_mapping.get(
                "pipe_layer_name", ""
            ),
            "pipe_layer_source": self._temporary_mapping.get(
                "pipe_layer_source", ""
            ),
            "pipe_id_field": self._temporary_mapping.get("pipe_id_field", ""),
            "length_field": self._temporary_mapping.get("length_field", ""),
            "result_layer_name": self._temporary_mapping.get(
                "result_layer_name", ""
            ),
            "result_layer_source": self._temporary_mapping.get(
                "result_layer_source", ""
            ),
            "result_id_field": self._temporary_mapping.get(
                "result_id_field", ""
            ),
            "flow_field": self._temporary_mapping.get("flow_field", ""),
            "node_result_layer_name": node_layer["name"] if node_layer else "",
            "node_result_layer_source": (
                node_layer["source"] if node_layer else ""
            ),
            "node_result_id_field": endpoint.get("node_id_field", ""),
            "pressure_field": endpoint.get("pressure_field", ""),
        }
        report = self._dialog.report_configuration()
        return {
            **report,
            "project_name": project.title()
            or (Path(project_file).stem if project_file else ""),
            "project_file": project_file,
            "project_crs": project.crs().authid(),
            "hydrosizer_version": __version__,
            "qgis_version": getattr(Qgis, "QGIS_VERSION", ""),
            "qgisred_version": "Not identified",
            "language": self._locale_name,
            "mapping": mapping,
            "flow_unit": self._last_batch_result.get("flow_unit", ""),
            "length_unit": self._last_batch_result.get("length_unit", ""),
            "hydraulic_method": criteria.get("hydraulic_method", ""),
            "endpoint_relationship": "geometry",
            "endpoint_tolerance": endpoint.get("endpoint_tolerance"),
            "endpoint_pressure_unit": endpoint.get("pressure_unit", ""),
            "pressure_margin_mode": endpoint.get("margin_mode", "none"),
            "safety_factor": endpoint.get("safety_factor", 1.0),
            "additive_margin_value": endpoint.get(
                "additive_margin_value", 0.0
            ),
            "additive_margin_unit": endpoint.get(
                "additive_margin_unit", ""
            ),
            "catalog_path": str(self._catalog_repository.database_path)
            if self._catalog_repository is not None
            else "",
            "catalog_snapshot_sha256": self._catalog_snapshot_sha256(),
        }

    def _invalidate_apply_plan(self, message: str = "") -> None:
        """Discard a prepared plan whenever its reviewed inputs change."""
        self._last_apply_plan = None
        if self._dialog is not None:
            self._dialog.invalidate_apply_plan(
                message
                or self.tr("Apply configuration changed. Prepare the plan again.")
            )

    def _browse_apply_audit_directory(self) -> None:
        if self._dialog is None:
            return
        current = self._dialog.apply_configuration().get("audit_directory", "")
        selected = QFileDialog.getExistingDirectory(
            self._dialog,
            self.tr("Choose HydroSizer audit directory"),
            current or str(Path.home()),
        )
        if selected:
            self._dialog.set_apply_audit_directory(selected)

    def _prepare_apply_plan(self) -> None:
        """Read current target values and build a no-write before/after plan."""
        if (
            self._dialog is None
            or self._last_preview is None
            or self._last_batch_result is None
            or self._temporary_mapping is None
        ):
            if self._dialog is not None:
                self._dialog.set_apply_error(
                    self.tr("Safe apply requires a current Batch sizing preview."),
                    clear_report=True,
                )
            return
        self._last_apply_plan = None
        mapping = self._dialog.apply_configuration()
        audit_directory = Path(mapping["audit_directory"]).expanduser()
        if not mapping["audit_directory"]:
            self._dialog.set_apply_error(
                self.tr(
                    "Choose an audit directory before preparing the apply plan."
                ),
                clear_report=True,
            )
            return
        if not audit_directory.is_absolute():
            self._dialog.set_apply_error(
                self.tr("Audit directory must be an absolute path."),
                clear_report=True,
            )
            return
        target_fields = list(
            dict.fromkeys(
                mapping[key]
                for key in (
                    "material_field",
                    "nominal_field",
                    "internal_field",
                    "hydraulic_field",
                    "pressure_class_field",
                )
                if mapping[key]
            )
        )
        protected_fields = {
            self._temporary_mapping["pipe_id_field"],
            self._temporary_mapping["length_field"],
        }
        protected_targets = sorted(set(target_fields) & protected_fields)
        if protected_targets:
            self._dialog.set_apply_error(
                self.tr(
                    "Safe apply cannot overwrite mapped pipe ID or length fields: "
                    "{fields}"
                ).format(fields=", ".join(protected_targets)),
                clear_report=True,
            )
            return
        included_fids = [
            int(row["pipe_fid"])
            for row in self._last_preview["rows"]
            if row["included"]
        ]
        layer_configuration = {
            "layer_id": self._temporary_mapping["pipe_layer_id"],
            "layer_source": self._temporary_mapping.get(
                "pipe_layer_source", ""
            ),
            "pipe_id_field": self._temporary_mapping["pipe_id_field"],
            "target_fields": target_fields,
        }
        try:
            current = read_apply_records(layer_configuration, included_fids)
            plan = build_apply_plan(
                self._last_preview,
                current,
                mapping,
                self._last_batch_result["criteria"]["hydraulic_method"],
            )
        except (KeyError, OSError, ValueError) as error:
            message = self.tr("Safe apply plan blocked: {error}").format(
                error=self._localized_error(error)
            )
            self._dialog.set_apply_error(message, clear_report=True)
            self._log(message)
            return
        except Exception as error:
            message = self.tr(
                "Safe apply plan failed: {error_type}: {error}"
            ).format(
                error_type=type(error).__name__,
                error=self._localized_error(error),
            )
            self._dialog.set_apply_error(message, clear_report=True)
            self._log(message, level=_critical_level())
            return
        plan["layer_configuration"] = layer_configuration
        plan["audit_directory"] = str(audit_directory)
        self._last_apply_plan = plan
        summary = self.tr(
            "Apply plan ready: included={included}; changes={changes}; "
            "maintained={maintained}. No layer edits yet."
        ).format(
            included=plan["included_count"],
            changes=plan["change_count"],
            maintained=plan["maintained_count"],
        )
        self._dialog.set_apply_plan(
            summary,
            self._localized_report(format_apply_plan(plan)),
            plan["change_count"],
        )
        self._log(self.tr(
            "{summary} IDs and current target values captured for revalidation."
        ).format(summary=summary))

    def _execute_apply_plan(self) -> None:
        """Confirm, revalidate, audit, and apply one undoable edit command."""
        if self._dialog is None or self._last_apply_plan is None:
            if self._dialog is not None:
                self._dialog.set_apply_error(
                    self.tr(
                        "No current apply plan. Prepare the before/after plan first."
                    )
                )
            return
        plan = self._last_apply_plan
        layer = QgsProject.instance().mapLayer(
            plan["layer_configuration"]["layer_id"]
        )
        layer_name = layer.name() if layer is not None else self.tr("<missing layer>")
        standard = getattr(QMessageBox, "StandardButton", None)
        yes = standard.Yes if standard else QMessageBox.Yes
        no = standard.No if standard else QMessageBox.No
        response = QMessageBox.question(
            self._dialog,
            self.tr("Confirm HydroSizer safe apply"),
            self.tr(
                "This operation will alter {count} pipe(s) in layer {layer}. "
                "Previous and proposed values will be written to CSV/JSON audit "
                "files. Changes will remain pending in the QGIS edit buffer so "
                "they can be undone or saved. Continue?"
            ).format(count=plan["change_count"], layer=layer_name),
            yes | no,
            no,
        )
        if response != yes:
            self._log(self.tr(
                "Safe apply cancelled at the explicit confirmation dialog."
            ))
            return

        try:
            current_dataset = read_mapped_records(self._temporary_mapping)
            current_validation = validate_mapped_data(current_dataset)
            if not current_validation["valid_for_sizing"]:
                raise ValueError(self.tr(
                    "mapped pipe/result IDs no longer pass Data validation"
                ))
            revalidate_input_snapshot(
                self._last_validation["dataset"],
                current_dataset,
            )
        except Exception as error:
            self._last_apply_plan = None
            message = self.tr(
                "Safe apply blocked by last-moment input revalidation: {error}. "
                "Run Data validation and Batch sizing again."
            ).format(error=self._localized_error(error))
            self._dialog.set_apply_error(message)
            self._log(message, level=_critical_level())
            QMessageBox.critical(
                self._dialog, self.tr("HydroSizer safe apply"), message
            )
            return

        metadata = self._apply_audit_metadata(layer_name)

        def write_audit():
            return write_audit_bundle(
                Path(plan["audit_directory"]),
                plan,
                metadata,
            )

        try:
            result = apply_change_plan(
                plan["layer_configuration"],
                plan,
                write_audit,
            )
        except Exception as error:
            self._last_apply_plan = None
            message = self.tr(
                "Safe apply failed and the HydroSizer edit command was rolled "
                "back: {error_type}: {error}"
            ).format(
                error_type=type(error).__name__,
                error=self._localized_error(error),
            )
            self._dialog.set_apply_error(message)
            self._log(message, level=_critical_level())
            QMessageBox.critical(
                self._dialog, self.tr("HydroSizer safe apply"), message
            )
            return

        self._last_applied_plan = plan
        self._last_apply_plan = None
        audit = result["audit"]
        report = "\n".join(
            [
                self.tr("HydroSizer Safe Apply — Stage 14"),
                self.tr(
                    "Status: SUCCESS; changes are pending in the QGIS edit buffer"
                ),
                "",
                self.tr("Changed pipe features: {count}").format(
                    count=result["changed_features"]
                ),
                self.tr("Changed attributes: {count}").format(
                    count=result["changed_attributes"]
                ),
                self.tr("Edit session started by HydroSizer: {answer}").format(
                    answer=self.tr("yes")
                    if result["edit_session_started"]
                    else self.tr("no")
                ),
                self.tr("Run ID: {run_id}").format(run_id=audit["run_id"]),
                self.tr("Audit CSV: {path}").format(path=audit["csv_path"]),
                self.tr("Metadata JSON: {path}").format(path=audit["json_path"]),
                "",
                self.tr("Use QGIS Save Layer Edits to persist, or Undo to revert."),
                self.tr(
                    "Rerun QGISRed manually after saving the proposed pipe values."
                ),
            ]
        )
        summary = self.tr(
            "Safe apply succeeded: {features} pipe(s), {attributes} attribute(s); "
            "edits pending save."
        ).format(
            features=result["changed_features"],
            attributes=result["changed_attributes"],
        )
        self._dialog.set_apply_result(summary, report)
        self._log(self.tr(
            "{summary} Audit CSV={csv}; metadata JSON={json}."
        ).format(summary=summary, csv=audit["csv_path"], json=audit["json_path"]))

    def _apply_audit_metadata(self, layer_name: str) -> Dict[str, Any]:
        project = QgsProject.instance()
        criteria = dict(self._last_batch_result.get("criteria", {}))
        endpoint = self._dialog.endpoint_pressure_configuration()
        project_file = project.fileName()
        return {
            "hydrosizer_version": __version__,
            "qgis_version": getattr(Qgis, "QGIS_VERSION", ""),
            "qgisred_version": "not detected",
            "project_name": project.title()
            or (Path(project_file).stem if project_file else ""),
            "project_file": project_file,
            "layer_name": layer_name,
            "layer_source": self._temporary_mapping.get("pipe_layer_source", ""),
            "layer_sources": {
                "pipe": self._temporary_mapping.get("pipe_layer_source", ""),
                "result": self._temporary_mapping.get("result_layer_source", ""),
            },
            "mapped_fields": {
                "input": dict(self._temporary_mapping),
                "output": dict(self._last_apply_plan["field_mapping"]),
            },
            "flow_unit": self._last_batch_result.get("flow_unit", ""),
            "length_unit": self._last_batch_result.get("length_unit", ""),
            "pressure_unit": endpoint.get("pressure_unit", ""),
            "hydraulic_method": criteria.get("hydraulic_method", ""),
            "criteria": criteria,
            "selection_strategy": (
                "smallest DN, lowest cost, highest pressure, stable catalog ID"
            ),
            "catalog_snapshot_sha256": self._catalog_snapshot_sha256(),
            "batch_processed_count": self._last_batch_result.get(
                "processed_count", 0
            ),
        }

    def _catalog_snapshot_sha256(self) -> str:
        """Hash the products captured in the current included preview rows."""
        if self._last_preview is None:
            return ""
        fields = (
            "selected_catalog_id",
            "material_code",
            "product_code",
            "nominal_diameter",
            "nominal_diameter_unit",
            "internal_diameter",
            "internal_diameter_unit",
            "pressure_class",
            "max_allowable_pressure",
            "pressure_unit",
            "hazen_williams_c",
            "absolute_roughness",
            "roughness_unit",
            "cost_per_length",
            "cost_length_unit",
            "qgisred_material_value",
        )
        products = [
            {key: row.get(key) for key in fields}
            for row in self._last_preview["rows"]
            if row["included"]
        ]
        payload = json.dumps(
            products,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _suggest_audit_directory(layer_source: str) -> Optional[Path]:
        raw_source = str(layer_source or "").split("|", 1)[0]
        if raw_source and not raw_source.casefold().startswith(
            ("dbname=", "http://", "https://")
        ):
            path = Path(raw_source)
            if path.is_absolute():
                return path.parent / "HydroSizer_Audit"
        project_file = QgsProject.instance().fileName()
        if project_file:
            return Path(project_file).parent / "HydroSizer_Audit"
        return None

    def _add_catalog_product(self) -> None:
        if self._dialog is None or self._catalog_repository is None:
            return
        editor = CatalogProductDialog(parent=self._dialog)
        while editor.run():
            try:
                catalog_id, warnings = self._catalog_repository.add_product(
                    editor.values()
                )
                self._refresh_catalog()
                self._show_catalog_operation(
                    self.tr("Catalog product {catalog_id} added.").format(
                        catalog_id=catalog_id
                    ),
                    warnings,
                )
                self._log(self.tr(
                    "Catalog product added: catalog_id={catalog_id}."
                ).format(catalog_id=catalog_id))
                return
            except Exception as error:
                self._handle_catalog_error(
                    self.tr("Could not add catalog product"), error
                )
                if not self._is_expected_catalog_error(error):
                    return

    def _edit_catalog_product(self) -> None:
        product = self._selected_catalog_product(self.tr("edit"))
        if (
            product is None
            or self._dialog is None
            or self._catalog_repository is None
        ):
            return
        editor = CatalogProductDialog(product=product, parent=self._dialog)
        while editor.run():
            try:
                warnings = self._catalog_repository.update_product(
                    product["catalog_id"], editor.values()
                )
                self._refresh_catalog()
                self._show_catalog_operation(
                    self.tr("Catalog product {catalog_id} updated.").format(
                        catalog_id=product["catalog_id"]
                    ),
                    warnings,
                )
                self._log(self.tr(
                    "Catalog product updated: catalog_id={catalog_id}."
                ).format(catalog_id=product["catalog_id"]))
                return
            except Exception as error:
                self._handle_catalog_error(
                    self.tr("Could not update catalog product"), error
                )
                if not self._is_expected_catalog_error(error):
                    return

    def _duplicate_catalog_product(self) -> None:
        product = self._selected_catalog_product(self.tr("duplicate"))
        if product is None or self._catalog_repository is None:
            return
        try:
            catalog_id, warnings = self._catalog_repository.duplicate_product(
                product["catalog_id"]
            )
            self._refresh_catalog()
            self._show_catalog_operation(
                self.tr("Catalog product duplicated as ID {catalog_id}.").format(
                    catalog_id=catalog_id
                ),
                warnings,
            )
            self._log(self.tr(
                "Catalog product duplicated: source={source}; new={new}."
            ).format(source=product["catalog_id"], new=catalog_id))
        except Exception as error:
            self._handle_catalog_error(
                self.tr("Could not duplicate catalog product"), error
            )

    def _toggle_catalog_product(self) -> None:
        product = self._selected_catalog_product(self.tr("activate or deactivate"))
        if product is None or self._catalog_repository is None:
            return
        new_state = not bool(product["active"])
        try:
            self._catalog_repository.set_active(product["catalog_id"], new_state)
            self._refresh_catalog()
            state_label = self.tr("active") if new_state else self.tr("inactive")
            self._show_catalog_operation(
                self.tr("Catalog product {catalog_id} is now {state}.").format(
                    catalog_id=product["catalog_id"], state=state_label
                )
            )
            self._log(self.tr(
                "Catalog product state changed: catalog_id={catalog_id}; "
                "active={active}."
            ).format(catalog_id=product["catalog_id"], active=new_state))
        except Exception as error:
            self._handle_catalog_error(
                self.tr("Could not change product state"), error
            )

    def _delete_catalog_product(self) -> None:
        product = self._selected_catalog_product(self.tr("delete"))
        if (
            product is None
            or self._dialog is None
            or self._catalog_repository is None
        ):
            return
        standard = getattr(QMessageBox, "StandardButton", None)
        yes = standard.Yes if standard else QMessageBox.Yes
        no = standard.No if standard else QMessageBox.No
        response = QMessageBox.question(
            self._dialog,
            self.tr("Delete HydroSizer catalog product"),
            self.tr(
                "Delete catalog ID {catalog_id} ({material} / {product})?"
            ).format(
                catalog_id=product["catalog_id"],
                material=product["material_code"],
                product=product["product_code"],
            ),
            yes | no,
            no,
        )
        if response != yes:
            return
        try:
            deleted = self._catalog_repository.delete_product(
                product["catalog_id"]
            )
            if not deleted:
                raise KeyError(
                    self.tr("Catalog product {catalog_id} no longer exists").format(
                        catalog_id=product["catalog_id"]
                    )
                )
            self._refresh_catalog()
            self._show_catalog_operation(
                self.tr("Catalog product {catalog_id} deleted.").format(
                    catalog_id=product["catalog_id"]
                )
            )
            self._log(self.tr(
                "Catalog product deleted: catalog_id={catalog_id}."
            ).format(catalog_id=product["catalog_id"]))
        except Exception as error:
            self._handle_catalog_error(
                self.tr("Could not delete catalog product"), error
            )

    def _import_catalog_csv(self) -> None:
        if self._dialog is None or self._catalog_repository is None:
            return
        selected_path, _selected_filter = QFileDialog.getOpenFileName(
            self._dialog,
            self.tr("Import HydroSizer catalog CSV"),
            str(self._catalog_repository.database_path.parent),
            self.tr("CSV files (*.csv)"),
        )
        if not selected_path:
            return
        try:
            count, warnings = self._catalog_repository.import_csv(
                Path(selected_path)
            )
            self._refresh_catalog()
            self._show_catalog_operation(
                self.tr(
                    "Imported {count} catalog product(s) atomically."
                ).format(count=count),
                warnings,
            )
            self._log(self.tr(
                "Catalog CSV imported: {path}; products={count}."
            ).format(path=selected_path, count=count))
        except Exception as error:
            self._handle_catalog_error(self.tr("Catalog CSV import failed"), error)

    def _export_catalog_csv(self) -> None:
        if self._dialog is None or self._catalog_repository is None:
            return
        default_path = (
            self._catalog_repository.database_path.parent
            / "hydrosizer_catalog.csv"
        )
        selected_path, _selected_filter = QFileDialog.getSaveFileName(
            self._dialog,
            self.tr("Export HydroSizer catalog CSV"),
            str(default_path),
            self.tr("CSV files (*.csv)"),
        )
        if not selected_path:
            return
        target = Path(selected_path)
        if target.suffix.casefold() != ".csv":
            target = target.with_suffix(".csv")
        try:
            count = self._catalog_repository.export_csv(target)
            self._show_catalog_operation(
                self.tr("Exported {count} catalog product(s) to {target}.").format(
                    count=count, target=target
                )
            )
            self._log(self.tr(
                "Catalog CSV exported: {target}; products={count}."
            ).format(target=target, count=count))
        except Exception as error:
            self._handle_catalog_error(self.tr("Catalog CSV export failed"), error)

    def _validate_catalog(self) -> None:
        if self._catalog_repository is None:
            return
        try:
            validation = self._catalog_repository.validate_catalog()
            lines = [
                self.tr("HydroSizer Catalog Validation — Stage 7"),
                self.tr("Products: {count}").format(
                    count=validation["product_count"]
                ),
                self.tr("Invalid products: {count}").format(
                    count=validation["invalid_count"]
                ),
                self.tr("Warnings: {count}").format(
                    count=validation["warning_count"]
                ),
            ]
            for item in validation["items"]:
                for error in item["errors"]:
                    lines.append(
                        self.tr(
                            "[ERROR] ID {catalog_id} {material}/{product}: {error}"
                        ).format(
                            catalog_id=item["catalog_id"],
                            material=item["material_code"],
                            product=item["product_code"],
                            error=self._localized_report(str(error)),
                        )
                    )
                for warning in item["warnings"]:
                    lines.append(
                        self.tr(
                            "[WARNING] ID {catalog_id} {material}/{product}: {warning}"
                        ).format(
                            catalog_id=item["catalog_id"],
                            material=item["material_code"],
                            product=item["product_code"],
                            warning=warning,
                        )
                    )
            summary = self.tr(
                "Catalog validation completed: {invalid} invalid product(s), "
                "{warnings} warning(s)."
            ).format(
                invalid=validation["invalid_count"],
                warnings=validation["warning_count"],
            )
            if self._dialog is not None:
                self._dialog.set_catalog_report(summary, "\n".join(lines))
            self._log(summary)
        except Exception as error:
            self._handle_catalog_error(self.tr("Catalog validation failed"), error)

    def _selected_catalog_product(self, action: str):
        if self._dialog is None or self._catalog_repository is None:
            return None
        catalog_id = self._dialog.selected_catalog_id()
        if catalog_id is None:
            self._dialog.set_catalog_error(
                self.tr("Select one catalog product to {action}.").format(
                    action=action
                )
            )
            return None
        product = self._catalog_repository.get_product(catalog_id)
        if product is None:
            self._dialog.set_catalog_error(
                self.tr(
                    "Catalog product {catalog_id} no longer exists; refresh the view."
                ).format(catalog_id=catalog_id)
            )
        return product

    def _show_catalog_operation(
        self, summary: str, warnings: Optional[list] = None
    ) -> None:
        if self._dialog is None:
            return
        details = ""
        if warnings:
            details = self.tr("Warnings:") + "\n" + "\n".join(
                f"- {warning}" for warning in warnings
            )
        self._dialog.set_catalog_report(summary, details)

    def _handle_catalog_error(self, title: str, error: Exception) -> None:
        if isinstance(error, CatalogValidationError):
            details = "; ".join(error.errors)
        else:
            details = str(error)
        message = self.tr("{title}: {details}").format(
            title=title, details=details
        )
        expected = self._is_expected_catalog_error(error)
        self._log(message, level=None if expected else _critical_level())
        if self._dialog is not None:
            self._dialog.set_catalog_error(message)
            message_box = QMessageBox.warning if expected else QMessageBox.critical
            message_box(self._dialog, self.tr("HydroSizer catalog"), message)

    @staticmethod
    def _is_expected_catalog_error(error: Exception) -> bool:
        return isinstance(
            error,
            (
                CatalogValidationError,
                CatalogConflictError,
                CatalogImportError,
                KeyError,
                ValueError,
                OSError,
            ),
        )

    def _inventory_layer(self, layer_id: str):
        for layer in self._mapping_inventory:
            if layer["id"] == layer_id:
                return layer
        return None

    def _layer_name(self, layer_id: str) -> str:
        layer = self._inventory_layer(layer_id)
        return layer["name"] if layer else ""

    def _on_dialog_closed(self, _result: int) -> None:
        self._log(self.tr("HydroSizer dialog closed."))

    @staticmethod
    def _log(message: str, level=None) -> None:
        QgsMessageLog.logMessage(
            message, LOG_TAG, level=level if level is not None else _info_level()
        )
