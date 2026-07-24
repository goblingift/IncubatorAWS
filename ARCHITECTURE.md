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
incubator_measurement_clean   ----> incubator-latest-reading (HTTP GET,  API Gateway,
                                                               /sensor/latest/{device_id})
incubator_measurement_clean   ----> incubator-measurements-range (HTTP GET, API Gateway,
                                                                   /sensor/measurements/{device_id}
                                                                   ?range=1h|2h|24h|7d)
incubator_measurement_clean   ----> incubator-battery-status (HTTP GET,  API Gateway,
                                                               /sensor/battery/{device_id})
incubator_alerts (DynamoDB)   ----> incubator-alerts-get     (HTTP GET,  API Gateway,
                                                               Cognito-authorized)

incubator_measurement_clean
     |  (INSERT only, second stream consumer — see note below)
     v
incubator-light-rollup  ---->  incubator_light_hourly (TTL'd hourly buckets)
                                        |
                                        | queried on an hourly EventBridge schedule
                                        v
                          incubator-light-average-alert
                                   |         \
                                   v          v
                          incubator_alerts   SNS topic
                                             (incubator-measurement-
                                              outside-allowed-range)

incubator_settings ----> incubator-light-average-alert (scanned each run for
                                                          devices with
                                                          light_sleep_max and
                                                          light_sleep_min_hours set)

incubator_light_hourly ----> incubator-light-average-status (HTTP GET, API Gateway,
                                                               /sensor/light-average/{device_id})
incubator_settings     ----> incubator-light-average-status (GetItem per device, for its
                                                               light_sleep_max/min_hours)

Note: incubator-light-average-alert/-status, their EventBridge rule
(incubator-light-average-hourly), and the /sensor/light-average route all
predate the "sleep-friendly hours" redesign (see Migration Notes) — their
names are now partial misnomers, kept as-is deliberately rather than
recreating deployed AWS resources for a cosmetic rename.

incubator_measurement_rejected
     |  (scanned on an hourly EventBridge schedule)
     v
incubator-measurements-rejected-alert  ---->  SNS topic
                                               (incubator-measurement-rejected)
                                                    |
                                                    v
                                               email subscribers
```

Note: `incubator_measurement_clean`'s DynamoDB Stream has two independent
consumers (`incubator-threshold-alert` and `incubator-light-rollup`) — this is
at DynamoDB Streams' documented limit of 2 concurrent Lambda readers per
shard. A 3rd consumer would need restructuring (e.g. combining concerns into
one Lambda, or moving to Kinesis Data Streams for DynamoDB).

There are three triggers into this system:
- **DynamoDB Streams**, for the automatic cleaning/alerting/rollup pipeline.
- **API Gateway (HTTP)**, for reading/writing device settings, querying the
  latest measurement or a historical range, browsing a device's alert
  history, and projecting remaining battery runtime — presumably used by a
  frontend/dashboard.
- **EventBridge (scheduled)**, for the hourly rolling-average light check and
  the hourly rejected-measurements check.

---

## AWS IoT Rule

Not represented as code anywhere else (console-configured, like API Gateway) —
recorded here so it doesn't drift out of sync with the firmware unnoticed
again (see Migration Notes: the `relayState`/`actuator_state` mismatch below).

The gateway (`esp32-gateway-platformio`) publishes one MQTT message per
reading to topic `incubator/data`, with a JSON body whose keys are now
identical to `incubator_measurement_raw`'s expected field names (see
`formatDeviceId()` and the `doc[...]` assignments in
`esp32-gateway-platformio/src/main.cpp`). Because of that, the rule that
inserts into `incubator_measurement_raw` is a plain passthrough — no
`SELECT ... AS ...` aliasing needed:

```sql
SELECT * FROM 'incubator/data'
```

Action: DynamoDBv2, table `incubator_measurement_raw`.

**Historical note:** before the firmware sent AWS-native field names
directly, this rule did the renaming itself (`lux AS light_intensity`, `co2
AS co2_ppm`, etc.). One line — `relayState AS relay_state` — referenced a
field the gateway never actually published (it sent `actuatorState`, not
`relayState`) and aliased it to a name `lambda-cleanup-measurements` doesn't
recognize either (it expects `actuator_state`, singular, which it then
decomposes into `relay_state_1..4` + `humidifier_state`). Since
`actuator_state` isn't a required field, this failed silently — every
measurement's real relay/humidifier state was dropped before reaching
`incubator_measurement_clean`, with no error anywhere. Moving the
renaming into firmware (version-controlled, code-reviewed) instead of an
IoT Rule (console-only state, no diff, no tests) was a deliberate fix for
that class of bug, not just this one instance of it.

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
- `device_id` (falls back to `"unknown"` if missing/unparseable in the raw
  payload)
- `timestamp` (the raw payload's own timestamp if it parsed as a valid
  epoch int, otherwise falls back to `processed_at` — so this field is
  always a valid epoch int, never a placeholder string)
- `processed_at` (epoch int, always server-side/reliable — this is what
  `incubator-measurements-rejected-alert` filters on, since a rejected
  record's own `timestamp` can't always be trusted as "when it actually
  happened")
- `cleaning_status: "rejected"`
- `rejection_reasons` (list of human-readable strings, one per failed field)
- `rejection_reason` (same list, joined with `"; "`, for easy console viewing)
- `raw_payload` (the original, unmodified raw item, DynamoDB-compatible)

Read (via full-table `scan()`) by `incubator-measurements-rejected-alert` on
an hourly schedule.

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
| `light_sleep_max` | `light_intensity` (max hourly-average lux for an hour to count as "sleep-friendly" — see `incubator-light-average-alert`) |
| `light_sleep_min_hours` | derived: count of sleep-friendly hours in the last 24h (not a raw measurement field — see `incubator-light-average-alert`) |
| `sound_max` | `sound_intensity` |
| `weight_min`, `weight_max` | `weight_gram` |
| `pitch_deg_max` | `pitch_deg` (checked against absolute value) |
| `roll_deg_max` | `roll_deg` (checked against absolute value) |
| `voltage_min`, `voltage_max` | `voltage` |
| `current_min`, `current_max` | `current` |
| `water_level_min`, `water_level_max` | `water_level` |
| `battery_percent_min` | `battery_percent` (computed via discharge-curve interpolation over the current measurement's voltage — not a raw measurement field; see `incubator-threshold-alert`) |

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

> **Note (historical):** this table previously had `light_max`, an
> instantaneous per-reading cap on `light_intensity`. It was replaced with
> `light_avg_max`, a threshold on the rolling 24-hour average of
> `light_intensity` (evaluated hourly by `incubator-light-average-alert`, not
> per-measurement) — a single momentary bright flash no longer trips an
> alert, but a sustained elevated light level over a day does. Existing rows
> written before this change will have `light_max` but not `light_avg_max`;
> since `incubator-settings-post` overwrites the whole item via `put_item`,
> the stale `light_max` key is dropped automatically the next time that
> device's settings are re-submitted.

> **Note (historical):** this table previously had `light_avg_max`, a
> threshold on the rolling 24-hour *average* of `light_intensity`. It was
> replaced with `light_sleep_max` + `light_sleep_min_hours`, since an average
> doesn't answer the question that actually matters — whether the incubator
> got enough dark, sleep-friendly time in a day — a device lit brightly for 2
> hours and dark for 22 could still average low enough to pass, and vice
> versa. `light_sleep_max` now defines what counts as a sleep-friendly hour
> (that hour's own average <= this value), and `light_sleep_min_hours` is the
> minimum required count of such hours per 24h — see `incubator-light-
> average-alert`. Existing rows written before this change will have
> `light_avg_max` but not the two new fields; since `incubator-settings-post`
> overwrites the whole item via `put_item`, the stale key is dropped
> automatically the next time that device's settings are re-submitted — but
> until then, `incubator-light-average-alert`'s scan (which now requires
> *both* new fields to exist) simply won't match that device, meaning it
> silently stops being checked for light at all. See Migration Notes for the
> deploy-order recommendation this implies.

### `incubator_light_hourly`
- **Partition key:** `device_id` (String)
- **Sort key:** `hour_bucket` (Number, epoch seconds floored to the start of
  the UTC hour: `int(timestamp // 3600 * 3600)`)

Rolling accumulator populated by `incubator-light-rollup`, one item per
device per hour. Fields:
- `light_sum` — running sum of `light_intensity` (lux) for readings that
  fell in this hour bucket
- `reading_count` — number of readings summed into `light_sum`
- `expires_at` — epoch seconds TTL attribute (`hour_bucket + 48h`); DynamoDB
  auto-deletes old buckets, no cleanup job needed. 48h gives ~2x headroom
  over the 24h lookback window used by `incubator-light-average-alert`; TTL
  deletion itself is best-effort (AWS may take up to ~48h after `expires_at`
  to actually purge), which doesn't matter for correctness since consumers
  always bound their `hour_bucket` query range explicitly.

`light_sum`/`reading_count` were deliberately named as compound identifiers
rather than the bare words `sum`/`count`, since those are DynamoDB reserved
words in expression syntax; DynamoDB's reserved-word check is whole-token
(not substring), so compound names like these are unaffected — the same way
this schema already uses `timestamp` (itself reserved) safely elsewhere.

Also read on-demand by `incubator-light-average-status` (HTTP GET), which
exposes the same rolling 24h average `light_intensity` that
`incubator-light-average-alert` computes hourly for alerting — same query,
same math, different trigger/cadence, so the dashboard can show a live
number instead of the alert's frozen-at-the-hour value.

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

### `incubator-alerts-get`
**Trigger:** API Gateway HTTP `GET` (proxy integration), expects
`{device_id}` as a path parameter. Unlike the other read Lambdas, this
method's API Gateway route is protected by the same Cognito User Pool
authorizer used for `POST /settings` — alert history is treated as more
sensitive than raw sensor readings or settings.
**Files:** `lambda_function.py`, `config.py`, `repository.py`,
`response_utils.py`

Queries `incubator_alerts` for every row matching the given `device_id`
(`table.query`, paginating on `LastEvaluatedKey` — bounded to a single
partition, not a full-table scan), then sorts the combined list by
`checked_at` descending in Python, since the table's sort key (`alert_id`,
a generated UUID) carries no chronological ordering. Returns the array
directly (`200` with a JSON array, `[]` if the device has no alerts), rather
than wrapping it in an object. Responds `400` if `device_id` is missing.
Handles `OPTIONS` preflight for CORS.

No response-side limit/pagination is applied — matches this repo's existing
"fine at prototype scale" philosophy (e.g. `incubator-latest-reading`'s
full-scan fallback) — worth revisiting if a chronically-alerting device
accumulates enough rows to make the response slow or large.

### `incubator-latest-reading`
**Trigger:** API Gateway HTTP `GET` (proxy integration), optional
`{device_id}` path parameter.
**Files:** `lambda_function.py`, `response_utils.py`

If `device_id` is given, queries `incubator_measurement_clean` for that
device's most recent item (`ScanIndexForward=False, Limit=1`). If omitted,
falls back to a full table `scan()` and picks the most recent item across all
devices — note this is O(table size) and will not scale well as the table
grows; fine for small/prototype-scale usage.

Returns the full item unfiltered — every field written by
`lambda-cleanup-measurements` is present in the response, nothing is
dropped. Originally serialized with `json.dumps(body, default=str)`, which
silently stringified every `Decimal` (e.g. `temperature_celsius` came back
as `"37.5"`, a string, not a number); fixed to use the same
`response_utils.py` (`DecimalEncoder`-based) helper as `incubator-settings-
get`/`incubator-alerts-get`/`incubator-measurements-range`, so numeric
fields are now real JSON numbers.

### `incubator-measurements-range`
**Trigger:** API Gateway HTTP `GET` (proxy integration) at
`/sensor/measurements/{device_id}` — a sibling resource under the same
`/sensor` path as `incubator-latest-reading`'s `/sensor/latest/{device_id}`,
rather than its own top-level resource. Expects `{device_id}` as a path
parameter and an optional `range` query-string parameter (`1h`, `2h`, `24h`,
or `7d`; defaults to `24h`, `400` on any other value).
**Files:** `lambda_function.py`, `config.py`, `repository.py`,
`downsampler.py`, `response_utils.py`

Computes `start`/`end` epoch bounds from the requested range, then queries
`incubator_measurement_clean` for that device across the window
(`Key("device_id").eq(device_id) & Key("timestamp").between(start, end)`,
`ScanIndexForward=True` — ascending, correct order for a time series),
paginating on `LastEvaluatedKey` (bounded to one partition/time window, not
a full scan).

If the query returns more than `MAX_POINTS` (750 — chosen so the "last 2
hours" range stays at full ~10s-per-reading resolution, since the incubator
reports roughly every 10s and 2h × 6/min = ~720 readings) items,
`downsampler.py` buckets them into `MAX_POINTS` evenly-sized time windows
(`bucket_width = (end - start) / MAX_POINTS`, same flooring idea as
`incubator-light-rollup`'s `hour_bucket`) and averages every numeric field
per bucket — including the 0/1 actuator fields (`relay_state_1-4`,
`humidifier_state`), which average out to a meaningful "fraction of time
on" for that bucket rather than being dropped. Below the threshold, points
are returned raw and unaveraged — so the "last hour" view is typically full
resolution, while "last 7 days" is usually downsampled.

Returns the array directly (`200`, `[]` if the device has no data in the
window). Handles `OPTIONS` preflight for CORS. Unlike `incubator-alerts-
get`, this endpoint is **not** behind the Cognito authorizer — it's public,
matching `incubator-latest-reading` and the fact it backs the (unprotected)
Dashboard page.

### `incubator-battery-status`
**Trigger:** API Gateway HTTP `GET` (proxy integration) at
`/sensor/battery/{device_id}` — a sibling resource under the same `/sensor`
path as `incubator-latest-reading`'s `/sensor/latest/{device_id}` and
`incubator-measurements-range`'s `/sensor/measurements/{device_id}`. Expects
`{device_id}` as a path parameter; takes no query-string parameters (the
lookback window is fixed at 60 minutes, not user-selectable like `range` on
`-measurements-range`).
**Files:** `lambda_function.py`, `config.py`, `repository.py`, `curve.py`,
`regression.py`, `response_utils.py`

Predicts remaining incubator runtime on battery power:
1. Queries `incubator_measurement_clean` for the last 60 minutes of
   `(timestamp, voltage, relay_state_3)` (`Key("device_id").eq(device_id) &
   Key("timestamp").between(start, end)`, `ScanIndexForward=True`, paginated
   on `LastEvaluatedKey` — same bounded single-partition shape as
   `-measurements-range`, with a `ProjectionExpression` added since only 3 of
   the ~17 clean-table fields are needed; its `#ts` alias is required because
   `ProjectionExpression`, unlike `KeyConditionExpression`'s `Key()` helper,
   doesn't auto-escape reserved words, and `timestamp` is one).
2. For each reading, picks a discharge curve — `IDLE_CURVE` or `HEATER_CURVE`
   in `config.py` — based on that reading's own `relay_state_3` (the heater
   relay channel, per firmware's `RELAY_CH_HEATER`), defaulting to
   `IDLE_CURVE` when `relay_state_3` is `0`, `None`, or absent entirely (older
   rows predating the `actuator_state` migration have no relay fields at
   all — see Migration Notes).
3. Linearly interpolates voltage against the chosen curve
   (`curve.interpolate_percent`), clamping to 100%/0% outside the curve's
   endpoints rather than rejecting the reading.
4. **Before fitting, restricts the series to the trailing run of readings
   that share the latest reading's `relay_state_3`** (`
   _trailing_same_state_segment` — walks backward from the most recent
   reading and stops at the first heater-state change). This is a
   correctness fix, not an optimization: the idle and heater curves are two
   independently-measured tables, not perfectly reconciled against each
   other, so a heater on↔off transition mid-window produces a voltage (and
   thus percent) jump that isn't real battery drain/charge — regressing
   across it read a heater turning off as "charging" and a heater turning on
   as "draining fast," neither of which reflects the true trend. Restricting
   to the same-state tail avoids mixing curves in one fit, at the cost of a
   shorter (or empty) series immediately after a heater toggle.
5. Fits an ordinary-least-squares line (`regression.linear_regression`, plain
   Python, no numpy — same precedent as `incubator-light-average-alert`'s
   arithmetic) over that segment's `(timestamp, percent)` series. Timestamps
   are re-centered on the segment's first reading before fitting purely for
   float precision: epoch-second timestamps are ~1.75×10⁹-scale, so squaring
   them in the textbook slope formula subtracts two ~10²³-scale sums to
   recover a signal many orders of magnitude smaller — a classic
   catastrophic-cancellation trap. Centering keeps every value under ~3600
   and sidesteps it; slope is translation-invariant, so the answer is
   unchanged, only its numerical safety.
6. Slope is negated and converted to percent/hour so a positive number
   always means "draining."
7. If the drain rate is at or below `MIN_DRAIN_RATE_PERCENT_PER_HOUR`
   (config, default `0.1` — avoids a razor-thin positive slope from
   measurement noise producing an absurd "312 days remaining"), the battery
   is reported `"stable_or_charging"` and `remaining_hours`/
   `predicted_shutdown_at` are `null`.
8. Otherwise `remaining_hours = current_percent / drain_rate_percent_per_hour`
   and `predicted_shutdown_at = now + remaining_hours` (epoch seconds,
   matching every other timestamp in this pipeline).

`current_percent`/`current_voltage`/`heater_active` come from the single
most recent reading in the full window (same "just return the latest row"
philosophy as `incubator-latest-reading`), not the regression line's fitted
value at "now" — only the drain-rate regression itself is restricted to the
same-state segment above. `sample_count` reflects the segment actually used
for the regression, not the full window's reading count.

Graceful degradation, matching this repo's "never 500 for 'no data yet'"
convention: zero readings in the window → `200`, `"status": "no_data"`; one
reading in the same-state segment, or a segment whose readings all share a
single timestamp (degenerate regression) → `200`,
`"status": "insufficient_data"` (commonly right after a heater toggle,
before enough same-state readings have accumulated), current
voltage/percent still reported, drain-rate fields `null`; otherwise
`"status": "draining"` with every field populated.

**Curve data is calibrated from a real discharge test** (2026-07-22):
`IDLE_CURVE`/`HEATER_CURVE` in `config.py` are 21-point tables (0–100% in 5%
steps) measured by discharging the incubator's actual battery under idle and
heater-loaded conditions — not the straight-line guess this Lambda originally
shipped with. `CURVE_CALIBRATED = True` is threaded into every response as
`"curve_calibrated": true`; the frontend's uncalibrated-data warning banner
no longer shows. Both curves are strictly monotonic (voltage decreases as
percent decreases), which `curve.interpolate_percent` relies on. If a future
re-measurement delivers finer-grained data (e.g. 1% steps), it's still a
drop-in replacement of the same two constants — no other file changes.

Public — not behind the Cognito authorizer. Sensor-derived operational
status, the same class of data as `incubator-latest-reading`/
`incubator-measurements-range` (both public); Cognito-gating in this
pipeline is reserved specifically for alert history
(`incubator-alerts-get`).

### `incubator-threshold-alert`
**Trigger:** DynamoDB Stream on `incubator_measurement_clean` (`INSERT`/
`MODIFY` events; `REMOVE` is skipped since it has no `NewImage` to check).
**Files:** `lambda_function.py`, `config.py`, `checker.py`, `repository.py`,
`curve.py`

For each new clean measurement:
1. Skips anything not `cleaning_status: "clean"` (defensive; rejected items
   live in a different table anyway).
2. If the measurement has a `voltage` field, computes a synthetic
   `battery_percent` field via the same discharge-curve interpolation as
   `incubator-battery-status` (`curve.py`, `IDLE_CURVE`/`HEATER_CURVE`
   duplicated verbatim — no shared Lambda layer in this repo; if the curves
   are ever re-measured, update both files together, nothing enforces them
   staying in sync), selecting the idle or heater-load curve by the
   measurement's own `relay_state_3`. Because this runs per-measurement via
   the stream (not a periodic scan), battery alerts fire as fast as any
   other threshold check — within seconds of the device reporting — unlike
   `incubator-light-average-alert`'s hourly cadence. Wrapped in
   `Decimal(str(round(..., 2)))` before being added to the measurement dict:
   `curve.py`'s interpolation returns a native Python `float`, and on a
   violation this value flows straight into `incubator_alerts` via
   `put_item`, which rejects native floats (`TypeError: Float types are not
   supported` — same class of bug `lambda-cleanup-measurements`'
   `to_dynamo_compatible` exists to prevent elsewhere in this pipeline).
3. Looks up that device's row in `incubator_settings`. If none exists, the
   record is skipped entirely (no thresholds to check against).
4. `ThresholdChecker.check` compares each measurement field present
   (including the synthetic `battery_percent`, if computed) against its
   corresponding min/max threshold field(s) from `THRESHOLD_FIELDS` in
   `config.py`. `pitch_deg`/`roll_deg` are compared by absolute value against
   a single max (symmetric tilt tolerance).
5. For every violation found:
   - writes a row to `incubator_alerts`
   - publishes a message to the SNS topic
     `incubator-measurement-outside-allowed-range`, with a human-readable
     subject/body describing the device, field, value, and violated
     threshold.

Same partial-batch-failure pattern as the cleanup Lambda.

Note: `voltage_min` (default 11V) already fires on low voltage independent of
`battery_percent_min` — a real low-battery event will likely trip both checks
and send two separate notifications for what's conceptually one event, since
`voltage_min` is a flat cutoff regardless of heater-load state while
`battery_percent_min` is load-aware. Not addressed; revisit if the double
notification becomes annoying.

### `incubator-light-rollup`
**Trigger:** DynamoDB Stream on `incubator_measurement_clean` — this is the
stream's **second** independent consumer, alongside
`incubator-threshold-alert` (`INSERT` events only; unlike
`incubator-threshold-alert`, `MODIFY` is intentionally skipped here since
this Lambda accumulates a running sum, and re-processing a `MODIFY` on an
already-counted reading would double-count it, with no `OldImage` available
to reconcile against since the stream is `NEW_IMAGE`-only).
**Files:** `lambda_function.py`, `config.py`, `repository.py`

For each new clean measurement with `cleaning_status: "clean"` and a
present, non-null `light_intensity` (checked by presence/`None`, not
truthiness — `0` lux is a legitimate, common reading and must still count):
1. Computes `hour_bucket` by flooring the measurement's `timestamp` to the
   start of its UTC hour.
2. Atomically increments that device/hour's row in `incubator_light_hourly`
   (`ADD light_sum, reading_count`), creating the row if it doesn't exist
   yet, and refreshes its TTL (`expires_at`).

Same partial-batch-failure pattern as the other stream Lambdas.

### `incubator-light-average-alert`
**Trigger:** EventBridge scheduled rule, hourly (`cron(0 * * * ? *)`) — the
first use of EventBridge in this repo. **Note:** this Lambda's name (and its
EventBridge rule, `incubator-light-average-hourly`) predates the
"sleep-friendly hours" redesign below and is now a partial misnomer — kept
as-is rather than recreating a deployed AWS resource for a cosmetic rename
(see Migration Notes).
**Files:** `lambda_function.py`, `config.py`, `repository.py`

Once per hour:
1. Scans `incubator_settings` for devices with **both** `light_sleep_max`
   and `light_sleep_min_hours` configured (small table, few devices — same
   "fine at prototype scale" justification as `incubator-latest-reading`'s
   full-table-scan fallback).
2. For each such device, queries `incubator_light_hourly` for the current
   hour bucket plus the previous 23 (~24h trailing window).
3. Skips the device entirely if **no readings at all** were found in that
   window (e.g. device offline) — no false alert, same "skip when data is
   absent" philosophy as `incubator-threshold-alert` skipping devices with no
   settings row. This whole-window guard is distinct from a single missing
   hour within an otherwise-reporting window — see next step.
4. Counts how many of the returned hour buckets are "sleep-friendly": an
   hour qualifies if that hour's own average (`light_sum / reading_count`)
   is `<= light_sleep_max`. An hour with no readings at all has no bucket
   row to begin with (`incubator-light-rollup`'s `add_reading` only ever
   creates a row via `ADD light_sum, reading_count` together — there's no
   code path that writes `reading_count: 0`), so a reporting gap is silently
   excluded from the count rather than needing special-case handling — a gap
   can't masquerade as evidence of darkness.
5. If the resulting count is below `light_sleep_min_hours`: writes a row to
   `incubator_alerts` (`field: "light_sleep_hours_24h"`, `value`: the actual
   count, `bound: "min"`, `threshold: light_sleep_min_hours`, `timestamp` set
   to the current hour bucket rather than a single offending measurement's
   timestamp, since this is an aggregate check, not a per-measurement one)
   and publishes to the same SNS topic as `incubator-threshold-alert`, same
   plain `sns.publish(...)` style.

Unlike `incubator-threshold-alert`, this can raise at most one alert per
device per hour, rather than one per violating measurement.

### `incubator-light-average-status`
**Trigger:** API Gateway HTTP `GET` (proxy integration) at
`/sensor/light-average/{device_id}` — a sibling resource under the same
`/sensor` path as `incubator-latest-reading`/`incubator-measurements-range`/
`incubator-battery-status`. Expects `{device_id}` as a path parameter.
**Note:** same naming caveat as `incubator-light-average-alert` above — the
Lambda name and route path predate this redesign.
**Files:** `lambda_function.py`, `config.py`, `repository.py`,
`response_utils.py`

Exposes the same "sleep-friendly hours" count that
`incubator-light-average-alert` computes hourly for alerting, but on-demand
for the dashboard. Fetches the device's `light_sleep_max`/
`light_sleep_min_hours` via `GetItem` on `incubator_settings` (a **new**
access this Lambda didn't previously need — computing the count requires
knowing the device's threshold) — falling back to
`DEFAULT_LIGHT_SLEEP_MAX`/`DEFAULT_LIGHT_SLEEP_MIN_HOURS` in `config.py`
(duplicated from `incubator-settings-get`'s `DEFAULT_SETTINGS` — same
duplication-across-files precedent as the battery discharge curves; update
both together if the defaults ever change) if the device has no settings row
yet, or one predating this feature. Then queries `incubator_light_hourly`
for the current hour bucket plus the previous 23 (identical window/query
shape to `incubator-light-average-alert`) and counts sleep-friendly hours
the same way — deliberately the same logic, so the number shown on the
dashboard is the same one the hourly alert check acts on, modulo cadence:
this Lambda recomputes fresh on every request against current data, while
the alert Lambda only recomputes once an hour, so the two can diverge
between alert evaluations by design, not by bug (the dashboard should show a
live number; the alert's decision was frozen at the top of its hour).

Returns `{"device_id", "status": "ok", "sleep_friendly_hours",
"light_sleep_min_hours", "light_sleep_max", "passing", "sample_count",
"bucket_count"}` on success, where `passing = sleep_friendly_hours >=
light_sleep_min_hours`. If no light readings at all exist in the 24h window
(new device, or one that stopped reporting more than `incubator_light_hourly`'s
~48h TTL ago), returns `{"device_id", "status": "no_data", "message",
"sleep_friendly_hours": null, "light_sleep_min_hours", "light_sleep_max",
"passing": null, "sample_count": 0, "bucket_count"}` instead of an error —
this `no_data` status is reserved specifically for "no data to compute
from," distinct from "no configured threshold" (which has a default
fallback, not an error). Handles `OPTIONS` preflight for CORS; `500` on
unexpected errors.

Public — not behind the Cognito authorizer, same reasoning as
`incubator-battery-status`: sensor-derived operational data, not alert
history.

### `incubator-measurements-rejected-alert`
**Trigger:** EventBridge scheduled rule, hourly (`cron(0 * * * ? *)`).
**Files:** `lambda_function.py`, `config.py`, `repository.py`

Once per hour:
1. Scans `incubator_measurement_rejected` (full-table `scan()` with a
   `FilterExpression` on `processed_at >= now - 60min` — this table has no
   index suited to "everything rejected across all devices in the last
   hour," and rejections are the exception path rather than the common one,
   so a scan should stay cheap).
2. If any rows matched, publishes a single SNS notification listing each
   rejected item's `device_id`, `timestamp`, and `rejection_reason`. If none
   matched, does nothing — no notification, no `incubator_alerts` row (this
   Lambda deliberately doesn't write to `incubator_alerts`, since that
   table's schema — `field`/`value`/`bound`/`threshold` — models a range
   violation, not a validation failure with a list of free-text reasons; a
   direct SNS notification fits better).

Publishes to its own dedicated SNS topic, separate from
`incubator-measurement-outside-allowed-range` — see Notifications below.

---

## Notifications (SNS)

Two independent topics, with separate email subscriptions — a subscriber to
one does not automatically receive the other:

### `incubator-measurement-outside-allowed-range`
(`arn:aws:sns:eu-north-1:683966915447:incubator-measurement-outside-allowed-range`)

Published to by `incubator-threshold-alert` once per violation (a single
measurement with multiple out-of-range fields produces multiple messages)
and by `incubator-light-average-alert` at most once per device per hour.
Subscribers (e.g. email) receive one notification per violated
field/check. Confirmed working via a live end-to-end test (temperature
violation → `incubator_alerts` row + email delivered).

No further downstream automation (e.g. auto-adjusting a heater relay) is
wired up yet — that's an open, explicitly deferred discussion.

### `incubator-measurement-rejected`
(`arn:aws:sns:eu-north-1:683966915447:incubator-measurement-rejected`)

Published to by `incubator-measurements-rejected-alert`, at most once per
hour, only when at least one measurement was rejected in that window. This
is a data-quality signal (validation failures), deliberately kept separate
from the threshold-violation topic above.

---

## IAM Notes

The `incubator-threshold-alert` Lambda's execution role includes the inline
policy `AccessDynamoDBSettingsAndPublishSNS`, which must grant:
- `dynamodb:GetItem` on `incubator_settings`
- `dynamodb:PutItem` on `incubator_alerts`
- `sns:Publish` on the `incubator-measurement-outside-allowed-range` topic

plus the AWS-managed `AWSLambdaDynamoDBExecutionRole` (stream read access) and
`AWSLambdaBasicExecutionRole` (CloudWatch Logs). No new permissions were
needed to add the `battery_percent` check above — it works entirely from the
measurement already delivered via the stream event and doesn't query
`incubator_measurement_clean` itself.

`incubator-light-rollup`'s execution role includes the inline policy
`AccessLightHourlyRollup`, granting:
- `dynamodb:UpdateItem` on `incubator_light_hourly`

plus `AWSLambdaDynamoDBExecutionRole` (stream read access) and
`AWSLambdaBasicExecutionRole` (CloudWatch Logs).

`incubator-light-average-alert`'s execution role includes the inline policy
`AccessLightAverageAlert`, granting:
- `dynamodb:Scan` on `incubator_settings`
- `dynamodb:Query` on `incubator_light_hourly`
- `dynamodb:PutItem` on `incubator_alerts`
- `sns:Publish` on the `incubator-measurement-outside-allowed-range` topic

(Unchanged by the "sleep-friendly hours" redesign — same four operations,
just a different settings field name in the scan filter and a different
alert `field` value; no policy edit needed.)

plus `AWSLambdaBasicExecutionRole` (CloudWatch Logs) — **not**
`AWSLambdaDynamoDBExecutionRole`, since this Lambda is EventBridge-triggered,
not a stream consumer. It also needs a resource-based Lambda permission
(`lambda:InvokeFunction` for principal `events.amazonaws.com`, scoped to the
EventBridge rule's ARN) so the schedule can invoke it — this is separate
from the execution role above and is usually added automatically if the
trigger is wired up via the Lambda console's "Add trigger" flow.

`incubator-measurements-rejected-alert`'s execution role includes the inline
policy `AccessRejectedAlert`, granting:
- `dynamodb:Scan` on `incubator_measurement_rejected`
- `sns:Publish` on the `incubator-measurement-rejected` topic

plus `AWSLambdaBasicExecutionRole` (CloudWatch Logs) — same EventBridge
invoke-permission note as `incubator-light-average-alert` above applies here
too.

`incubator-alerts-get`'s execution role includes the inline policy
`ReadIncubatorAlerts`, granting:
- `dynamodb:Query` on `incubator_alerts`

plus `AWSLambdaBasicExecutionRole` (CloudWatch Logs) — no stream role, this
is API-Gateway-triggered like `incubator-settings-get`/`-post` and
`incubator-latest-reading`. Its API Gateway `GET` method (not the Lambda
itself) is additionally gated by the Cognito authorizer shared with
`POST /settings` — the Lambda code performs no token validation of its own,
consistent with how `incubator-settings-post` also trusts API Gateway to
reject unauthorized requests before invocation.

`incubator-measurements-range`'s execution role includes the inline policy
`ReadIncubatorMeasurements`, granting:
- `dynamodb:Query` on `incubator_measurement_clean`

plus `AWSLambdaBasicExecutionRole` (CloudWatch Logs) — no stream role
(API-Gateway-triggered). Its `GET` method has Authorization set to NONE,
same as `incubator-latest-reading`.

`incubator-battery-status`'s execution role includes the inline policy
`ReadIncubatorMeasurementsForBattery`, granting:
- `dynamodb:Query` on `incubator_measurement_clean`

plus `AWSLambdaBasicExecutionRole` (CloudWatch Logs) — no stream role
(API-Gateway-triggered). Its `GET` method has Authorization set to NONE,
same as `incubator-latest-reading`/`incubator-measurements-range`.

`incubator-light-average-status`'s execution role includes the inline
policy `ReadIncubatorLightHourly`, granting:
- `dynamodb:Query` on `incubator_light_hourly`
- `dynamodb:GetItem` on `incubator_settings` (added for the "sleep-friendly
  hours" redesign — this endpoint now needs the device's `light_sleep_max`/
  `light_sleep_min_hours` to compute the count; it didn't need any settings
  access before)

plus `AWSLambdaBasicExecutionRole` (CloudWatch Logs) — no stream role
(API-Gateway-triggered). Its `GET` method has Authorization set to NONE,
same as the other public sensor-data read Lambdas. Still narrower than
`incubator-light-average-alert`'s role: `GetItem` only (not `Scan`) on
`incubator_settings`, and still no `incubator_alerts`/SNS access (it never
writes an alert, only reads).

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

**This migration is what caused the bug described in "AWS IoT Rule" above.**
The firmware and `lambda-cleanup-measurements` were both updated to the new
`actuator_state` name, but the IoT Rule's `SELECT` — console-only state, not
part of either code review — kept its pre-migration alias (`relayState AS
relay_state`), which matched neither the old nor the new name correctly.
Every real device's relay/humidifier state silently failed to reach
`incubator_measurement_clean` from that point on. Fixed by moving field
naming out of the IoT Rule entirely (see above) rather than just correcting
this one alias, so the same class of drift can't happen again.

Existing `incubator_measurement_clean`/`incubator_measurement_rejected` rows
written before this change will have the old `relay_state` key and will not
have `relay_state_1`–`relay_state_4` or `humidifier_state`. Rows written
after this change will have the 5 new keys and will not have `relay_state`.

`light_max` (instantaneous per-reading cap, checked by
`incubator-threshold-alert` on every measurement) was replaced with
`light_avg_max` (24h rolling average threshold, checked hourly by the new
`incubator-light-average-alert`):

| Old field | New field |
|---|---|
| `light_max` (instant per-reading cap) | `light_avg_max` (24h rolling average threshold, checked hourly) |

`light_avg_max` (24h rolling average threshold) was itself replaced with
`light_sleep_max` + `light_sleep_min_hours` (sleep-friendly-hour-count
threshold — see the `incubator_settings` historical note above and the
`incubator-light-average-alert`/`incubator-light-average-status` writeups
for the full rationale):

| Old field | New field |
|---|---|
| `light_avg_max` (24h rolling average threshold) | `light_sleep_max` + `light_sleep_min_hours` (sleep-friendly-hour-count threshold, checked hourly) |

**Deploy-order/monitoring-gap warning:** the moment `incubator-light-average-
alert` is redeployed with the new scan filter (requiring *both* new fields to
exist), any device that hasn't re-saved its settings yet stops being checked
for light at all — silently, no error, just no more light alerts for that
device until it re-saves. A device actively relying on the old `light_avg_max`
check goes dark on this specific check the instant this deploys. Recommended
deploy order: `incubator-settings-get` → frontend → `incubator-settings-post`
→ re-save settings on real devices → `incubator-light-average-alert`/
`-status` last (same shape of warning as the `battery_percent_min` rollout,
but worth restating since this one silently *disables* a check rather than
just returning a stale default).

**Naming note:** `incubator-light-average-alert`, `incubator-light-average-
status`, their EventBridge rule (`incubator-light-average-hourly`), and the
`/sensor/light-average` route all predate this change and are now partial
misnomers ("average" no longer describes what's computed). Kept as-is
deliberately — there's no IaC in this repo, so renaming any of these means
manually recreating the Lambda (name is baked into its ARN) and rewiring its
trigger/route/IAM role, for a purely cosmetic gain.

`battery_percent_min` was added to `incubator_settings` (default 20).
Existing rows written before this change will be missing it;
`incubator-threshold-alert`'s `ThresholdChecker` simply skips the
`battery_percent` check if the key isn't present (same graceful behavior as
any other missing threshold field) until re-submitted via
`incubator-settings-post` — at which point it becomes present, and mandatory
on every subsequent POST (`NUMERIC_FIELDS` requires it). Deploy order
matters: roll out `incubator-settings-get` and the frontend before making it
required in `incubator-settings-post`, or existing open frontend sessions
will get 400s on save.

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
| `incubator-threshold-alert/test-event-low-battery.json` | incubator-threshold-alert | low voltage → battery_percent below threshold → one alert + SNS publish |
| `incubator-light-rollup/test-event-rollup.json` | incubator-light-rollup | one clean measurement → hourly bucket incremented |
| `incubator-light-average-alert/test-event-scheduled.json` | incubator-light-average-alert | simulated hourly EventBridge tick |
| `incubator-measurements-rejected-alert/test-event-scheduled.json` | incubator-measurements-rejected-alert | simulated hourly EventBridge tick |
| `incubator-alerts-get/test-event-existing-device.json` | incubator-alerts-get | fetch alerts for a device with rows |
| `incubator-alerts-get/test-event-unknown-device.json` | incubator-alerts-get | fetch alerts for a device with none → `[]` |
| `incubator-measurements-range/test-event-last-hour.json` | incubator-measurements-range | `range=1h`, typically raw/undownsampled |
| `incubator-measurements-range/test-event-last-2h.json` | incubator-measurements-range | `range=2h`, typically raw/undownsampled |
| `incubator-measurements-range/test-event-last-24h.json` | incubator-measurements-range | `range=24h` |
| `incubator-measurements-range/test-event-last-7d.json` | incubator-measurements-range | `range=7d`, typically triggers downsampling |
| `incubator-measurements-range/test-event-unknown-device.json` | incubator-measurements-range | device with no data → `[]` |
| `incubator-battery-status/test-event-existing-device.json` | incubator-battery-status | fetch battery status for a device with recent readings |
| `incubator-battery-status/test-event-unknown-device.json` | incubator-battery-status | fetch battery status for a device with no recent readings → `no_data` |
| `incubator-light-average-status/test-event-existing-device.json` | incubator-light-average-status | fetch 24h light average for a device with recent hourly buckets |
| `incubator-light-average-status/test-event-unknown-device.json` | incubator-light-average-status | fetch for a device with no buckets in the window → `no_data` |
