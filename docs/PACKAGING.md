# Packaging and Release Checks

HydroSizer packages are built from an explicit allowlist. Run from the plugin
root:

```powershell
python scripts/package_plugin.py
```

The command creates `dist/HydroSizer-<version>.zip`. Every archive contains a
single `HydroSizer/` directory, the QGIS entry points, runtime Python modules,
the SVG icon, documentation, the bundled initial-catalog CSV, and
`PACKAGE_MANIFEST.json`. The manifest records the version and deterministic
file list without embedding high-entropy digests that secret scanners may
misclassify as credentials. Stable ordering, permissions, and timestamps make
repeated builds byte-for-byte reproducible; the builder reports an external
SHA-256 for the completed archive.

Tests, scripts, caches, SQLite databases, audit output, development-agent
instructions, and the large unused PNG are not distributed. The allowlisted
materials CSV is runtime data used only to initialize an empty profile catalog.
Packaging uses a temporary file, validates the completed ZIP, and only then
atomically replaces the target.

## Local QGIS installation

Use a separate QGIS test profile to avoid replacing the active development
copy. Open **Plugins > Manage and Install Plugins > Install from ZIP**, select
the generated archive, enable HydroSizer, and run the manual gate. Version
`1.0.0` is the first operational release and is not marked as experimental.

For an automated lifecycle smoke test, run `scripts/qgis_package_smoke.py`
with the OSGeo4W QGIS Python runtime and pass the generated ZIP path. This
checks the extracted package entry point, action/icon registration, and unload;
it also verifies the five-step interface, advanced-tools isolation, bounded
window size, navigation, and absence of page-level horizontal overflow. It does
not replace the mandatory clean-profile test in the QGIS application.

## Official repository readiness

The source tree includes the author, email, homepage, public repository,
issue tracker, GPL-2.0-or-later license, user documentation, and release
changelog. The package builder reports any missing publication field or license
as a blocker. The SVG icon is retained because it is the icon validated in the
supported QGIS runtime; verify the current official repository validator before
upload if its accepted image formats change.

## Versioning and release sequence

HydroSizer follows Semantic Versioning: `MAJOR.MINOR.PATCH`. Increase `MAJOR`
for incompatible workflow or data-contract changes, `MINOR` for backward-
compatible functionality, and `PATCH` for compatible corrections. Keep
`metadata.txt`, `__init__.__version__`, `CHANGELOG.md`, the Git tag `vX.Y.Z`,
and the package filename synchronized. Pre-release suffixes such as `-rc.1`
are reserved for explicitly experimental builds and must use
`experimental=True`; normal releases use `experimental=False`.
