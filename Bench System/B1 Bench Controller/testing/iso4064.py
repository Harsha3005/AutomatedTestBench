"""ISO 4064 water density lookup table for gravimetric volume calculation.

Usage:
    from testing.iso4064 import water_density
    density = water_density(22.1)  # kg/L at 22.1°C
    ref_volume = net_weight / density
"""

# ISO 4064 Annex — Water density (kg/L) at various temperatures (°C)
# at standard atmospheric pressure (101.325 kPa).
DENSITY_TABLE = {
    4:  0.99997,
    5:  0.99996,
    6:  0.99994,
    7:  0.99990,
    8:  0.99985,
    9:  0.99978,
    10: 0.99970,
    11: 0.99961,
    12: 0.99950,
    13: 0.99938,
    14: 0.99924,
    15: 0.99910,
    16: 0.99894,
    17: 0.99877,
    18: 0.99860,
    19: 0.99841,
    20: 0.99820,
    21: 0.99799,
    22: 0.99777,
    23: 0.99754,
    24: 0.99730,
    25: 0.99705,
    26: 0.99678,
    27: 0.99651,
    28: 0.99623,
    29: 0.99594,
    30: 0.99565,
    31: 0.99534,
    32: 0.99503,
    33: 0.99470,
    34: 0.99437,
    35: 0.99403,
    36: 0.99368,
    37: 0.99333,
    38: 0.99297,
    39: 0.99259,
    40: 0.99222,
}


def water_density(temperature_c: float) -> float:
    """Return water density in kg/L for a given temperature (°C).

    Uses linear interpolation between the nearest integer values
    from the ISO 4064 density table. Clamps to 4–40°C range.
    """
    temp = max(4.0, min(40.0, temperature_c))
    lower = int(temp)
    upper = lower + 1

    if upper > 40:
        return DENSITY_TABLE[40]

    d_lower = DENSITY_TABLE[lower]
    d_upper = DENSITY_TABLE[upper]
    fraction = temp - lower

    return d_lower + (d_upper - d_lower) * fraction


def calculate_error(ref_volume_l: float, dut_volume_l: float) -> float:
    """Calculate meter error percentage per ISO 4064."""
    if ref_volume_l == 0:
        return 0.0
    return ((dut_volume_l - ref_volume_l) / ref_volume_l) * 100.0


def check_pass(error_pct: float, mpe_pct: float) -> bool:
    """Check if error is within Maximum Permissible Error."""
    return abs(error_pct) <= abs(mpe_pct)
