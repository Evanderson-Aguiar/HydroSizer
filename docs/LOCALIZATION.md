# Stage 17 Localization

HydroSizer selects its presentation language from QGIS
`locale/userLocale` when the plugin loads. Locales beginning with `pt` use
Brazilian Portuguese; every other locale uses the English source messages.
Reload the plugin after changing the QGIS language.

The plugin installs its own Qt translator before creating its action or dialog
and removes it during unload. This covers tabs, controls, dialogs, progress,
controller feedback, and locally generated calculation or diagnostic reports.
The HTML calculation memory receives the same language in its immutable run
metadata. Its engineering structure and calculations are identical in both
languages.

Localization is restricted to presentation. Layer names, paths, field names,
pipe/node IDs, catalog codes, units, hydraulic method codes, numerical values,
and format placeholders are never changed. Free text entered for the project,
client, scenario, and description is preserved verbatim. The detailed CSV
keeps its established machine-readable column schema for compatibility.

The source language is English. New visible strings must use `self.tr(...)`
and receive a pt_BR catalog entry. Pure calculation and integration modules
remain independent of QGIS; their final multiline output is localized by the
controller only when displayed.
