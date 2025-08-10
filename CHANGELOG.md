# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2025-08-10
### Changed
- Added `version` field to `GET /health` response (API versioning introduced).
- Promoted model endpoints from `/online/model/*` to root level: `GET /model/info`, `POST /model/export`.
- Replaced `POST /online/training/restart_policy` with `PATCH /online/training/restart-policy` for RESTful semantics.

### Removed
- Deprecated `POST /online/model/retrain` endpoint (non-online full retrain placeholder) removed.
- Removed embedded changelog section from `README.md` (now separate file).

### Added
- Root-level model export (`POST /model/export`) and aggregated model info now include incremental trainer state when active.
- Separate `CHANGELOG.md` file.

### Migration Notes
- Update any clients calling `/online/model/export` or `/online/model/info` to use root-level equivalents.
- Remove usage of `/online/model/retrain`; implement offline retraining workflow separately if needed.
- Adjust clients expecting restart policy change via POST to use PATCH at new hyphenated path.

## [1.0.0] - 2025-08-01
### Added
- Initial release with core recommendation endpoints: `POST /recommend`, `POST /predict`.
- Health endpoint `GET /health` (without version field).
- Online learning endpoints: data ingestion, incremental training start/stop/status/logs.
- Streaming (Kafka) utilities and incremental updates listing.
- `/online/model/export` and `/online/model/info` (now relocated in 1.1.0).
