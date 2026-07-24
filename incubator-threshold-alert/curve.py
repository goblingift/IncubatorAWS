def interpolate_percent(curve, voltage):
    """curve: (voltage, percent) tuples, sorted descending by voltage,
    spanning 100% down to 0%. Clamps outside the curve's endpoints."""
    voltage = float(voltage)
    top_voltage, top_percent = curve[0]
    bottom_voltage, bottom_percent = curve[-1]
    if voltage >= top_voltage:
        return float(top_percent)
    if voltage <= bottom_voltage:
        return float(bottom_percent)
    for (v_high, p_high), (v_low, p_low) in zip(curve, curve[1:]):
        if v_low <= voltage <= v_high:
            if v_high == v_low:
                return float(p_high)
            fraction = (voltage - v_low) / (v_high - v_low)
            return float(p_low + fraction * (p_high - p_low))
    return float(bottom_percent)  # unreachable if curve is well-formed

def curve_for(relay_state_3, idle_curve, heater_curve):
    """Anything but exactly 1 (missing, None, 0) defaults to idle - covers
    genuinely-idle readings and old rows with no relay fields at all."""
    is_heater_on = int(relay_state_3 or 0) == 1
    return heater_curve if is_heater_on else idle_curve

def percent_for_reading(item, idle_curve, heater_curve):
    curve = curve_for(item.get("relay_state_3"), idle_curve, heater_curve)
    return interpolate_percent(curve, item["voltage"])
