from decimal import Decimal
from config import THRESHOLD_FIELDS

class ThresholdChecker:
    @staticmethod
    def check(measurement, settings):
        violations = []

        for field, bounds in THRESHOLD_FIELDS.items():
            if field not in measurement:
                continue

            value = measurement[field]
            check_value = abs(value) if bounds.get("abs") else value

            min_field = bounds.get("min")
            if min_field and min_field in settings:
                threshold = Decimal(str(settings[min_field]))
                if check_value < threshold:
                    violations.append({
                        "field": field,
                        "value": value,
                        "bound": "min",
                        "threshold": threshold,
                    })
                    continue

            max_field = bounds.get("max")
            if max_field and max_field in settings:
                threshold = Decimal(str(settings[max_field]))
                if check_value > threshold:
                    violations.append({
                        "field": field,
                        "value": value,
                        "bound": "max",
                        "threshold": threshold,
                    })

        return violations
