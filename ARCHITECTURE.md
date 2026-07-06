# Incubator AWS Pipeline — Architecture & Documentation

This document describes the serverless pipeline that ingests incubator sensor
measurements, cleans/validates them, exposes device settings via an API, and
raises alerts when a measurement falls outside the configured thresholds.

## Overview

```
sensor device
     |
     v
incubator_measurement_raw (DynamoDB, stream enabled)
     |  (INSERT)
     v
lambda-cleanup-measurements  ---->  incubator_measurement_clean
     |                                      |
     |                                      | (INSERT, stream enabled)
     |                                      v
     +----------------------------> incubator-threshold-alert
                                            |         \
                                            v          v
                                   incubator_alerts   SNS topic
                                                       (incubator-measurement-
                                                        outside-allowed-range)
                                                            |
                                                            v
                                                       email/SMS subscribers

incubator_settings (DynamoDB) <---- incubator-settings-post  (HTTP POST, API Gateway)
incubator_settings (DynamoDB) ----> incubator-settings-get   (HTTP GET,  API Gateway)
incubator_measurement_clean   ----> incubator-latest-reading (HTTP GET,  API Gateway)
```

There are two triggers into this system:
- **DynamoDB Streams**, for the automatic cleaning/alerting pipeline.
- **API Gateway (HTTP)**, for reading/writing device settings and querying the
  latest measurement, presumably used by a frontend/dashboard.

---

## DynamoDB Tables

### `incubator_measurement_raw`
Raw, unvalidated sensor measurements as written directly by the incubator
devices. Has DynamoDB Streams enabled (`NEW_IMAGE`), which triggers
`lambda-cleanup-measurements` on every `INSERT`. Schema is device-defined and
not enforced.

### `incubator_measurement_clean`
- **Partition key:** `device_id` (String)
- **Sort key:** `timestamp` (Number, epoch seconds)

Holds validated, normalized, and type-coerced measurements written by
`lambda-cleanup-measurements` once a raw record passes all field checks.
Fields (see `lambda-cleanup-measurements/config.py` `FIELD_SCHEMA`):

| Field | Type | Bounds |
|---|---|---|
| `device_id` | string (required) | max length 128 |
| `timestamp` | epoch int (required) | ≥ 0 |
| `co2_ppm` | decimal | 0–40000 |
| `current` | decimal | 0–100 |
| `humidity_rh` | decimal | 0–100 |
| `light_intensity` | decimal | ≥ 0 |
| `pitch_deg` | decimal | -180–180 |
| `relay_state_1` | bool (0/1) | — |
| `relay_state_2` | bool (0/1) | — |
| `relay_state_3` | bool (0/1) | — |
| `relay_state_4` | bool (0/1) | — |
| `humidifier_state` | bool (0/1) | — |
| `roll_deg` | decimal | -180–180 |
| `sound_intensity` | decimal | ≥ 0 |
| `temperature_celsius` | decimal | -20–80 |
| `voltage` | decimal | 0–60 |
| `water_level` | decimal | ≥ 0 |
| `weight_gram` | decimal | 0–20000 |

Plus `processed_at` (epoch int, when the cleanup Lambda ran) and
`cleaning_status: "clean"`.

DynamoDB Streams is also enabled on this table (`NEW_IMAGE`), which triggers
`incubator-threshold-alert` on every `INSERT`.

### `incubator_measurement_rejected`
Same partition/sort key shape as the clean table. Holds measurements that
failed one or more validation rules, written by `lambda-cleanup-measurements`.
Each item contains:
- `device_id`, `timestamp` (best-effort parsed, or falls back to `"unknown"`/
  the processing time if unparseable)
- `processed_at`
- `cleaning_status: "rejected"`
- `rejection_reasons` (list of human-readable strings, one per failed field)
- `rejection_reason` (same list, joined with `"; "`, for easy console viewing)
- `raw_payload` (the original, unmodified raw item, DynamoDB-compatible)

### `incubator_settings`
- **Partition key:** `device_id` (String)

Per-device configuration of alert thresholds, written via
`incubator-settings-post` and read via `incubator-settings-get` /
`incubator-threshold-alert`. Current fields
(`incubator-settings-post/config.py` `NUMERIC_FIELDS`):

| Field | Applies to measurement |
|---|---|
| `temperature_min`, `temperature_max` | `temperature_celsius` |
| `humidity_min`, `humidity_max` | `humidity_rh` |
| `co2_max` | `co2_ppm` |
| `light_max` | `light_intensity` |
| `sound_max` | `sound_intensity` |
| `weight_min`, `weight_max` | `weight_gram` |
| `pitch_deg_max` | `pitch_deg` (checked against absolute value) |
| `roll_deg_max` | `roll_deg` (checked against absolute value) |
| `voltage_min`, `voltage_max` | `voltage` |
| `current_min`, `current_max` | `current` |
| `water_level_min`, `water_level_max` | `water_level` |

Plus `device_id` and `updated_at` (ISO-8601 timestamp of last update).

`relay_state_1`–`relay_state_4` and `humidifier_state` intentionally have no
thresholds — they're boolean actuator states, not range-checkable
measurements.

> **Note (historical):** this table previously used `gyroscope_x_max`,
> `gyroscope_y_max`, `gyroscope_z_max` instead of `pitch_deg_max`/
> `roll_deg_max`. Any pre-existing rows written before this change will not
> have the new fields — see [Migration notes](#migration-notes).

> **Note (historical):** this table previously also had `temperature_target`
> and `humidity_target` fields (an operator-facing "ideal value" shown on the
> frontend dashboard, separate from the min/max alert bounds). They were
> dropped as redundant with min/max — pre-existing rows may still carry these
> keys, but no Lambda reads or writes them anymore.

### `incubator_alerts`
- **Partition key:** `device_id` (String)
- **Sort key:** `alert_id` (String, generated UUID)

One row per threshold violation, written by `incubator-threshold-alert`.
Fields:
- `device_id`, `alert_id`
- `timestamp` — the timestamp of the offending measurement
- `checked_at` — epoch seconds when the alert Lambda ran
- `field` — which measurement field violated its threshold (e.g.
  `temperature_celsius`)
- `value` — the measured value
- `bound` — `"min"` or `"max"`, which side of the threshold was crossed
- `threshold` — the configured threshold value that was violated

---

## Lambdas

### `lambda-cleanup-measurements`
**Trigger:** DynamoDB Stream on `incubator_measurement_raw` (`INSERT` events
only; other event types are skipped).
**Files:** `lambda_function.py`, `config.py`, `models.py`, `processor.py`,
`repositories.py`, `validator.py`

For each new raw record:
1. Deserializes the DynamoDB stream `NewImage` into a plain Python dict
   (`DynamoRepository.ddb_to_python`).
2. Runs it through `MeasurementProcessor.process`, which validates/normalizes
   every field defined in `FIELD_SCHEMA` (type coercion, min/max bounds,
   string cleanup — trimming, stripping stray leading quotes, rejecting
   non-numeric strings that `Decimal()` would otherwise accept like `"nan"`
   or `"1e5"`).
3. Writes the result to `incubator_measurement_clean` if valid, or
   `incubator_measurement_rejected` (with reasons + raw payload) if not.

Uses the standard DynamoDB-Streams **partial batch failure** pattern:
exceptions during a single record's processing are caught, and that record's
stream sequence number is reported back in `batchItemFailures` so only the
failed record is retried, not the whole batch.

### `incubator-settings-post`
**Trigger:** API Gateway HTTP `POST` (proxy integration).
**Files:** `lambda_function.py`, `config.py`, `repository.py`,
`response_utils.py`

Accepts a JSON body containing `device_id` plus all fields in
`NUMERIC_FIELDS`, converts each numeric field to `Decimal` (DynamoDB does not
support native floats), stamps `updated_at` with the current UTC time, and
overwrites (`put_item`) the settings row for that device. Responds `400` on
invalid JSON or a missing required field, `500` on unexpected errors, `200`
with the saved item on success. Handles `OPTIONS` preflight for CORS.

### `incubator-settings-get`
**Trigger:** API Gateway HTTP `GET` (proxy integration), expects
`{device_id}` as a path parameter.
**Files:** `lambda_function.py`, `config.py`, `repository.py`,
`response_utils.py`

Looks up the settings row for the given `device_id`. If none exists, returns
a default settings object (`DEFAULT_SETTINGS` in `config.py`) covering the
full current schema, so a not-yet-configured device still gets a usable
response shape instead of an error or a stale/incomplete field set.

### `incubator-latest-reading`
**Trigger:** API Gateway HTTP `GET` (proxy integration), optional
`{device_id}` path parameter.
**Files:** `lambda_function.py` (single file)

If `device_id` is given, queries `incubator_measurement_clean` for that
device's most recent item (`ScanIndexForward=False, Limit=1`). If omitted,
falls back to a full table `scan()` and picks the most recent item across all
devices — note this is O(table size) and will not scale well as the table
grows; fine for small/prototype-scale usage.

### `incubator-threshold-alert`
**Trigger:** DynamoDB Stream on `incubator_measurement_clean` (`INSERT`/
`MODIFY` events; `REMOVE` is skipped since it has no `NewImage` to check).
**Files:** `lambda_function.py`, `config.py`, `checker.py`, `repository.py`

For each new clean measurement:
1. Skips anything not `cleaning_status: "clean"` (defensive; rejected items
   live in a different table anyway).
2. Looks up that device's row in `incubator_settings`. If none exists, the
   record is skipped entirely (no thresholds to check against).
3. `ThresholdChecker.check` compares each measurement field present against
   its corresponding min/max threshold field(s) from `THRESHOLD_FIELDS` in
   `config.py`. `pitch_deg`/`roll_deg` are compared by absolute value against
   a single max (symmetric tilt tolerance).
4. For every violation found:
   - writes a row to `incubator_alerts`
   - publishes a message to the SNS topic
     `incubator-measurement-outside-allowed-range`, with a human-readable
     subject/body describing the device, field, value, and violated
     threshold.

Same partial-batch-failure pattern as the cleanup Lambda.

---

## Notifications (SNS)

Topic: `incubator-measurement-outside-allowed-range`
(`arn:aws:sns:eu-north-1:683966915447:incubator-measurement-outside-allowed-range`)

Published to by `incubator-threshold-alert` once per violation (a single
measurement with multiple out-of-range fields produces multiple messages).
Subscribers (e.g. email) receive one notification per violated field, per
measurement. Confirmed working via a live end-to-end test (temperature
violation → `incubator_alerts` row + email delivered).

No further downstream automation (e.g. auto-adjusting a heater relay) is
wired up yet — that's an open, explicitly deferred discussion.

---

## IAM Notes

The `incubator-threshold-alert` Lambda's execution role includes the inline
policy `AccessDynamoDBSettingsAndPublishSNS`, which must grant:
- `dynamodb:GetItem` on `incubator_settings`
- `dynamodb:PutItem` on `incubator_alerts`
- `sns:Publish` on the `incubator-measurement-outside-allowed-range` topic

plus the AWS-managed `AWSLambdaDynamoDBExecutionRole` (stream read access) and
`AWSLambdaBasicExecutionRole` (CloudWatch Logs).

---

## Migration Notes

The settings schema changed from a 3-axis gyroscope model to a 2-axis
pitch/roll model:

| Old field | New field |
|---|---|
| `gyroscope_x_max` | *(removed)* |
| `gyroscope_y_max` | `pitch_deg_max` |
| `gyroscope_z_max` | `roll_deg_max` |
| *(none)* | `voltage_min` / `voltage_max` |
| *(none)* | `current_min` / `current_max` |
| *(none)* | `water_level_min` / `water_level_max` |

Existing `incubator_settings` rows written before this change will be missing
`pitch_deg_max`, `roll_deg_max`, `voltage_min/max`, `current_min/max`, and
`water_level_min/max`. `incubator-threshold-alert`'s `ThresholdChecker` simply
skips a field's check if its threshold key isn't present in the settings row
(no error, no false alert) — so old rows degrade gracefully but silently
under-alert until re-submitted via `incubator-settings-post` with the full,
current field set.

`temperature_target` and `humidity_target` were removed from the settings
schema — they were only ever a display value for the frontend dashboard and
were never read by `incubator-threshold-alert`'s threshold checks. Existing
rows may still carry these keys; they're simply ignored (`incubator-settings-
post` no longer accepts or writes them, and `incubator-settings-get`'s
`DEFAULT_SETTINGS` no longer includes them).

The incoming device/gateway field for relay state was renamed from
`relay_state` to `actuator_state`. It's still a single `uint8_t` bitmask sent
over LoRa/MQTT (wire size unchanged — no new bytes were added to the
`SensorReading` struct or the LoRa packet), but it now carries 5 bits instead
of 4: bit0–bit3 are unchanged (relay channels 1–4), and the previously-unused
bit4 now represents the humidifier's on/off state.

On the AWS side, `lambda-cleanup-measurements` decomposes this single
incoming `actuator_state` value into 5 stored attributes instead of the old
single `relay_state`:

| Old field | New field(s) |
|---|---|
| `relay_state` (bitmask bit0–bit3) | `relay_state_1`, `relay_state_2`, `relay_state_3`, `relay_state_4` |
| *(none — bit4 was unused)* | `humidifier_state` |

Existing `incubator_measurement_clean`/`incubator_measurement_rejected` rows
written before this change will have the old `relay_state` key and will not
have `relay_state_1`–`relay_state_4` or `humidifier_state`. Rows written
after this change will have the 5 new keys and will not have `relay_state`.

---

## Test Events

Each Lambda directory contains one or more `test-event-*.json` files for use
in the Lambda console's "Test" tab:

| File | Lambda | Purpose |
|---|---|---|
| `lambda-cleanup-measurements/test-event-success.json` | lambda-cleanup-measurements | valid measurement → clean table |
| `lambda-cleanup-measurements/test-event-rejected.json` | lambda-cleanup-measurements | out-of-bounds measurement → rejected table |
| `incubator-settings-post/test-event-post-settings.json` | incubator-settings-post | full valid settings payload |
| `incubator-settings-get/test-event-existing-device.json` | incubator-settings-get | fetch a configured device |
| `incubator-settings-get/test-event-unknown-device.json` | incubator-settings-get | fetch an unconfigured device → defaults |
| `incubator-threshold-alert/test-event-violation.json` | incubator-threshold-alert | one field (temperature) out of range → one alert + SNS publish |
