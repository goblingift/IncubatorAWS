HOURLY_TABLE_NAME = "incubator_light_hourly"

HOUR_SECONDS = 3600

# How long a stale hourly bucket is kept around before DynamoDB TTL reaps it.
# Must comfortably exceed the 24h lookback window used by
# incubator-light-average-alert. TTL deletion itself is best-effort (AWS may
# take up to ~48h after expiry to actually purge), which is fine since
# correctness never depends on old buckets being physically gone.
BUCKET_TTL_SECONDS = 48 * HOUR_SECONDS
