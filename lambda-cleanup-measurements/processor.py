import time
from decimal import Decimal
from config import FIELD_SCHEMA, OPTIONAL_PASSTHROUGH_FIELDS
from models import ProcessingResult
from validator import SensorValidator
from repositories import DynamoRepository

class MeasurementProcessor:
    def process(self, raw):
        processed_at = int(time.time())
        errors = []
        clean_item = {
            "processed_at": processed_at,
            "cleaning_status": "clean",
        }

        for field, rules in FIELD_SCHEMA.items():
            raw_value = raw.get(field)
            required = rules.get("required", False)
            normalized, field_errors = self._normalize_field(field, raw_value, rules)
            if field_errors:
                errors.extend(field_errors)
                continue
            if normalized is None:
                if required:
                    errors.append(f"{field}: missing")
                continue
            clean_item[field] = normalized

        if "actuator_state" in clean_item:
            bitmask = clean_item.pop("actuator_state")
            clean_item["relay_state_1"] = 1 if (bitmask & 0b00001) else 0
            clean_item["relay_state_2"] = 1 if (bitmask & 0b00010) else 0
            clean_item["relay_state_3"] = 1 if (bitmask & 0b00100) else 0
            clean_item["relay_state_4"] = 1 if (bitmask & 0b01000) else 0
            clean_item["humidifier_state"] = 1 if (bitmask & 0b10000) else 0

        for field in OPTIONAL_PASSTHROUGH_FIELDS:
            if field in raw:
                clean_item[field] = raw[field]

        if errors:
            return ProcessingResult(
                is_valid=False,
                rejection_reasons=errors,
                clean_item=self._build_rejected_item(raw, errors, processed_at),
            )

        return ProcessingResult(is_valid=True, clean_item=clean_item)

    def _normalize_field(self, field, value, rules):
        if value is None:
            return None, []

        field_type = rules["type"]
        errors = []

        if field_type == "string":
            cleaned = SensorValidator.clean_scalar(value)
            if cleaned is None:
                return None, []
            cleaned = str(cleaned).strip() if rules.get("strip") else str(cleaned)
            if cleaned == "":
                return None, [f"{field}: empty"]
            max_length = rules.get("max_length")
            if max_length and len(cleaned) > max_length:
                return None, [f"{field}: too long"]
            return cleaned, []

        if field_type == "epoch_int":
            parsed = SensorValidator.parse_epoch_int(value)
            if parsed is None:
                return None, [f"{field}: invalid epoch"]
            if "min" in rules and parsed < rules["min"]:
                return None, [f"{field}: below minimum {rules['min']}"]
            if "max" in rules and parsed > rules["max"]:
                return None, [f"{field}: above maximum {rules['max']}"]
            return parsed, []

        if field_type == "bool_int":
            parsed = SensorValidator.parse_bool_int(value)
            if parsed is None:
                return None, [f"{field}: invalid boolean"]
            return parsed, []

        if field_type == "bitmask":
            parsed = SensorValidator.parse_bitmask(value, rules["bits"])
            if parsed is None:
                return None, [f"{field}: invalid bitmask"]
            return parsed, []

        if field_type == "decimal":
            parsed = SensorValidator.parse_decimal(value)
            if parsed is None:
                return None, [f"{field}: invalid numeric"]
            if "min" in rules and parsed < Decimal(str(rules["min"])):
                errors.append(f"{field}: below minimum {rules['min']}")
            if "max" in rules and parsed > Decimal(str(rules["max"])):
                errors.append(f"{field}: above maximum {rules['max']}")
            if errors:
                return None, errors
            return parsed, []

        return None, [f"{field}: unsupported field type {field_type}"]

    def _build_rejected_item(self, raw, reasons, processed_at):
        device_id = str(raw.get("device_id", "unknown")).strip() or "unknown"
        parsed_ts = SensorValidator.parse_epoch_int(raw.get("timestamp"))
        rejected_timestamp = parsed_ts if parsed_ts is not None else processed_at
        return {
            "device_id": device_id,
            "timestamp": rejected_timestamp,
            "processed_at": processed_at,
            "cleaning_status": "rejected",
            "rejection_reasons": reasons,
            "rejection_reason": "; ".join(reasons),
            "raw_payload": DynamoRepository.to_dynamo_compatible(raw),
        }
