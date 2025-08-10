# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Semantic Versioning](https://semver.org/).

## [1.2.0] - 2025-08-10
### Added
- Dedicated `TrainingDataProducer` component (Kafka producer abstraction with confluent_kafka / kafka-python fallback).
- Monitoring streaming endpoints: `GET /online/streaming/config`, `GET /online/streaming/status`, `POST /online/streaming/consume` (separate monitoring consumer group `<group>-monitor`).
- Support for inline `kafka_config` in `POST /online/data/add` (bootstrap mode before training starts).
- HTTP 207 partial success response for `POST /online/data/add` when some but not all samples are published.

### Changed
- `POST /online/data/add` now publishes directly to Kafka (was mock). Requires prior `POST /online/training/start` unless inline Kafka config supplied.
- Centralized Kafka config management inside `routes_online.py`; trainer no longer owns data ingestion.
- Internal EasyRec consumer (training) and external monitoring consumer separated; documentation clarifies roles.
- API docs updated to emphasize calling `/online/training/start` before regular data ingestion.

### Deprecated
- Implicit mock ingestion path (previous `EasyRecOnlineTrainer.add_training_data`) retained only for backward compatibility; will be removed in a future release.

### Migration Notes
- Ensure clients call `POST /online/training/start` to establish Kafka config before relying on `POST /online/data/add` (unless using bootstrap inline config pattern).
- Update any code referencing trainer.add_training_data to use the REST endpoint or integrate directly with Kafka.
- If you previously scraped messages via the same consumer group, switch to the monitoring endpoints to avoid interfering with training offsets.

## [1.1.0] - 2025-08-10
### Changed
- Added `version` field to `GET /health` response (API versioning introduced).
- Promoted model endpoints from `/online/model/*` to root level: `GET /model/info`, `POST /model/export`.
- Replaced `POST /online/training/restart_policy` with `PATCH /online/training/restart-policy` for RESTful semantics.
- Prediction endpoints (`POST /predict`, `POST /recommend`) now return HTTP 503 with `status: model_unavailable` when the model is not loaded instead of returning random fallback scores.

### Removed
- Deprecated `POST /online/model/retrain` endpoint (non-online full retrain placeholder) removed.
- Removed embedded changelog section from `README.md` (now separate file).

### Added
- Root-level model export (`POST /model/export`) and aggregated model info now include incremental trainer state when active.
- Separate `CHANGELOG.md` file.
- Stronger path sanitization for model/config directories.

### Migration Notes
- Update any clients calling `/online/model/export` or `/online/model/info` to use root-level equivalents.
- Remove usage of `/online/model/retrain`; implement offline retraining workflow separately if needed.
- Adjust clients expecting restart policy change via POST to use PATCH at new hyphenated path.
- Adjust client error handling: treat 503 `model_unavailable` as a retriable state and avoid using stale or placeholder predictions.

## [1.0.0] - 2025-08-01
### Added
- Initial release with core recommendation endpoints: `POST /recommend`, `POST /predict`.
- Health endpoint `GET /health` (without version field).
- Online learning endpoints: data ingestion, incremental training start/stop/status/logs.
- Streaming (Kafka) utilities and incremental updates listing.
- `/online/model/export` and `/online/model/info` (now relocated in 1.1.0).
