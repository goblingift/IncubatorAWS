from decimal import Decimal
from config import MAX_POINTS

def downsample(items, start, end):
    """Buckets items into MAX_POINTS evenly-sized time windows and averages
    every numeric field per bucket. Below the threshold, returns items
    unchanged (raw), so short ranges keep full resolution."""
    if len(items) <= MAX_POINTS:
        return items

    bucket_width = max(1, (end - start) // MAX_POINTS)
    buckets = {}

    for item in items:
        timestamp = int(item.get("timestamp", start))
        bucket_index = (timestamp - start) // bucket_width
        buckets.setdefault(bucket_index, []).append(item)

    return [
        _average_bucket(buckets[bucket_index], start + bucket_index * bucket_width)
        for bucket_index in sorted(buckets)
    ]

def _average_bucket(bucket_items, bucket_timestamp):
    sums = {}
    counts = {}
    passthrough = {}

    for item in bucket_items:
        for key, value in item.items():
            if key in ("device_id", "timestamp"):
                continue
            if isinstance(value, Decimal):
                sums[key] = sums.get(key, Decimal(0)) + value
                counts[key] = counts.get(key, 0) + 1
            elif key not in passthrough:
                passthrough[key] = value

    averaged = {key: total / counts[key] for key, total in sums.items()}
    return {
        "device_id": bucket_items[0].get("device_id"),
        "timestamp": bucket_timestamp,
        **passthrough,
        **averaged,
    }
