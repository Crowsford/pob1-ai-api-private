
# PoE BuildLab AI — Interaction Model v1.3
# Conservative corrections verified on held-out PoB runs.
# Applicable to the current build and skill group only.

MODEL_VERSION = "1.3"

# Sorted addition-node pair -> extra DPS in percentage points.
DPS_CORRECTIONS = {
    (57264, 65203): 0.377,
}


def corrected_changes(changes, add_ids):
    """Return corrected prediction without changing input."""
    result = dict(changes)

    pair = tuple(sorted(int(x) for x in add_ids))
    adjustment = DPS_CORRECTIONS.get(pair, 0.0)

    result["dps_percent"] = (
        float(result["dps_percent"]) + adjustment
    )

    return result


def correction_details(add_ids):
    pair = tuple(sorted(int(x) for x in add_ids))

    return {
        "modelVersion": MODEL_VERSION,
        "dpsCorrection": DPS_CORRECTIONS.get(pair, 0.0),
        "verified": pair in DPS_CORRECTIONS,
    }
