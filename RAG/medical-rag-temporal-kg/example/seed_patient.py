"""Seed a realistic patient with CKD + T2DM + declining eGFR on metformin.

Run with: python -m example.seed_patient
"""

from __future__ import annotations

import asyncio
import sys

import httpx


PATIENT_ID = "demo-patient-raj-sharma-001"
API_URL = "http://localhost:8085"


DOCUMENTS = [
    {
        "modality": "lab",
        "date": "2023-06-10",
        "source_id": "apollo-lab-2023-06",
        "labs": [
            {"test_name": "eGFR", "value": 58, "unit": "mL/min/1.73m2"},
            {"test_name": "creatinine", "value": 1.3, "unit": "mg/dL"},
            {"test_name": "HbA1c", "value": 7.8, "unit": "%"},
            {"test_name": "glucose", "value": 142, "unit": "mg/dL"},
            {"test_name": "potassium", "value": 4.8, "unit": "mEq/L"},
            {"test_name": "sodium", "value": 139, "unit": "mEq/L"},
        ],
    },
    {
        "modality": "lab",
        "date": "2023-09-15",
        "source_id": "apollo-lab-2023-09",
        "labs": [
            {"test_name": "eGFR", "value": 52, "unit": "mL/min/1.73m2", "previous_value": 58},
            {"test_name": "creatinine", "value": 1.5, "unit": "mg/dL", "previous_value": 1.3},
            {"test_name": "HbA1c", "value": 7.4, "unit": "%"},
            {"test_name": "potassium", "value": 5.1, "unit": "mEq/L"},
        ],
    },
    {
        "modality": "lab",
        "date": "2024-01-20",
        "source_id": "apollo-lab-2024-01",
        "labs": [
            {"test_name": "eGFR", "value": 44, "unit": "mL/min/1.73m2", "previous_value": 52},
            {"test_name": "creatinine", "value": 1.9, "unit": "mg/dL", "previous_value": 1.5},
            {"test_name": "BUN", "value": 28, "unit": "mg/dL"},
            {"test_name": "HbA1c", "value": 8.1, "unit": "%"},
            {"test_name": "LDL", "value": 132, "unit": "mg/dL"},
            {"test_name": "total_cholesterol", "value": 218, "unit": "mg/dL"},
        ],
    },
    {
        "modality": "text",
        "date": "2023-06-12",
        "source_id": "dr-patel-note-2023-06",
        "content": (
            "Patient: Raj Sharma, 58M. DOB: 1965-03-22. MRN: MH-2019-048821. "
            "Admitted 2023-06-12 for routine diabetes review. "
            "PMH: Type 2 Diabetes Mellitus (ICD: E11.9), Hypertension (ICD: I10). "
            "Current medications: Metformin 1000mg BD, Lisinopril 10mg OD, Atorvastatin 40mg OD. "
            "eGFR 58 mL/min. Continue current regimen. Review in 3 months. "
            "Treating physician: Dr. Anjali Patel (MBBS, MD - Nephrology). "
            "Apollo Hospital, Mumbai."
        ),
    },
    {
        "modality": "text",
        "date": "2024-01-22",
        "source_id": "dr-patel-note-2024-01",
        "content": (
            "Follow-up consultation 2024-01-22. "
            "Significant eGFR decline from 58 to 44 over 7 months. "
            "Patient remains on Metformin 1000mg BD despite declining renal function. "
            "Creatinine now 1.9 mg/dL. Stage 3b CKD (ICD: N18.3). "
            "HbA1c worsened to 8.1%. Patient reports no adverse symptoms. "
            "Risk assessment: Metformin dose reduction required given eGFR < 45. "
            "New findings: LDL elevated at 132 mg/dL, increase atorvastatin dose. "
            "Referral to nephrology clinic. Next review in 6 weeks."
        ),
    },
    {
        "modality": "ecg",
        "date": "2024-01-22",
        "source_id": "ecg-2024-01",
        "rhythm": "normal_sinus",
        "heart_rate_bpm": 76,
        "pr_interval_ms": 162,
        "qrs_duration_ms": 88,
        "qt_corrected_ms": 420,
        "findings": [],
        "interpretation": "Normal sinus rhythm. No acute changes.",
    },
]


async def seed() -> None:
    async with httpx.AsyncClient(timeout=120) as client:
        print(f"Seeding patient {PATIENT_ID}...")
        resp = await client.post(
            f"{API_URL}/ingest",
            json={
                "patient_id": PATIENT_ID,
                "requester_id": "seed-script",
                "documents": DOCUMENTS,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        print(f"Ingestion complete: {data['findings_ingested']} findings indexed")
        print("Patient ready for queries. Run: python -m example.run_query")


if __name__ == "__main__":
    asyncio.run(seed())
