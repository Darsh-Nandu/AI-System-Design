"""RxNorm drug contraindication rules engine.

Hardcoded subset covering the most common clinical interactions.
Production systems should call the RxNorm API or a licensed drug database.
"""

from __future__ import annotations

from medical_rag.models import DrugInteractionWarning, Severity

_RULES: list[dict] = [
    {
        "drug_a": "metformin",
        "drug_b": "contrast_dye",
        "type": "contraindication",
        "severity": "high",
        "rxnorm": "RxNorm:861004",
        "recommendation": "Hold metformin 48h before and after contrast administration.",
    },
    {
        "drug_a": "metformin",
        "drug_b": "egfr_threshold",
        "type": "dose_restriction",
        "severity": "high",
        "rxnorm": "RxNorm:860975",
        "recommendation": "Metformin contraindicated if eGFR < 30; dose reduce if eGFR 30-45.",
        "threshold": 30.0,
        "threshold_metric": "egfr",
    },
    {
        "drug_a": "warfarin",
        "drug_b": "aspirin",
        "type": "interaction",
        "severity": "moderate",
        "rxnorm": "RxNorm:202421",
        "recommendation": "Increased bleeding risk. Monitor INR closely.",
    },
    {
        "drug_a": "ace_inhibitor",
        "drug_b": "potassium_sparing_diuretic",
        "type": "interaction",
        "severity": "high",
        "rxnorm": "RxNorm:241793",
        "recommendation": "Risk of hyperkalemia. Monitor serum potassium weekly.",
    },
    {
        "drug_a": "nsaid",
        "drug_b": "ace_inhibitor",
        "type": "interaction",
        "severity": "moderate",
        "rxnorm": "RxNorm:253374",
        "recommendation": "NSAIDs reduce ACE inhibitor effectiveness and increase renal risk.",
    },
    {
        "drug_a": "ssri",
        "drug_b": "tramadol",
        "type": "interaction",
        "severity": "high",
        "rxnorm": "RxNorm:861016",
        "recommendation": "Risk of serotonin syndrome. Avoid combination.",
    },
    {
        "drug_a": "statin",
        "drug_b": "gemfibrozil",
        "type": "contraindication",
        "severity": "high",
        "rxnorm": "RxNorm:861022",
        "recommendation": "Avoid simvastatin/lovastatin + gemfibrozil. Rhabdomyolysis risk.",
    },
    {
        "drug_a": "quinolone",
        "drug_b": "antacid",
        "type": "interaction",
        "severity": "moderate",
        "rxnorm": "RxNorm:253380",
        "recommendation": "Antacids reduce quinolone absorption. Separate by 2-4h.",
    },
]

_DRUG_ALIASES: dict[str, list[str]] = {
    "ace_inhibitor": ["lisinopril", "enalapril", "ramipril", "captopril", "perindopril"],
    "nsaid": ["ibuprofen", "naproxen", "diclofenac", "celecoxib", "indomethacin"],
    "ssri": ["fluoxetine", "sertraline", "escitalopram", "paroxetine", "citalopram"],
    "statin": ["atorvastatin", "rosuvastatin", "simvastatin", "pravastatin", "lovastatin"],
    "quinolone": ["ciprofloxacin", "levofloxacin", "moxifloxacin", "ofloxacin"],
    "potassium_sparing_diuretic": ["spironolactone", "eplerenone", "triamterene", "amiloride"],
    "contrast_dye": ["iodinated_contrast", "gadolinium", "contrast"],
    "antacid": ["calcium_carbonate", "magnesium_hydroxide", "aluminum_hydroxide", "antacid"],
}


def _normalize(drug: str) -> set[str]:
    lower = drug.lower().replace("-", "_").replace(" ", "_")
    names = {lower}
    for canonical, aliases in _DRUG_ALIASES.items():
        if lower in aliases or lower == canonical:
            names.add(canonical)
    return names


def check_interactions(
    active_drugs: list[str],
    lab_values: dict[str, float] | None = None,
) -> list[DrugInteractionWarning]:
    warnings: list[DrugInteractionWarning] = []
    labs = lab_values or {}
    drug_sets = [_normalize(d) for d in active_drugs]

    for rule in _RULES:
        a_set = _normalize(rule["drug_a"])
        b_set = _normalize(rule["drug_b"])

        a_matched = any(a_set & ds for ds in drug_sets)
        if not a_matched:
            continue

        if "threshold_metric" in rule:
            metric = rule["threshold_metric"]
            threshold = rule["threshold"]
            actual = labs.get(metric)
            if actual is None or actual >= threshold:
                continue
            b_label = f"{metric} < {threshold}"
        else:
            b_matched = any(b_set & ds for ds in drug_sets)
            if not b_matched:
                continue
            b_label = rule["drug_b"]

        try:
            severity = Severity(rule["severity"])
        except ValueError:
            severity = Severity.MODERATE

        warnings.append(DrugInteractionWarning(
            drug_a=rule["drug_a"],
            drug_b=b_label,
            interaction_type=rule["type"],
            severity=severity,
            rxnorm_source=rule["rxnorm"],
            recommendation=rule["recommendation"],
        ))

    return warnings
