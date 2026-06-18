"""Seed sample legal documents into the index.

Ingests three realistic sample documents (case law, statute, advisory)
so the query pipeline can be exercised end-to-end.
"""

from __future__ import annotations

import asyncio
from datetime import date

from rag.indexing.ingestion import IngestionPipeline
from rag.logging import configure_logging
from rag.models import DocType, RawDocument
from rag.storage.postgres import create_tables
from rag.storage.qdrant_store import QdrantStore

configure_logging()

_DOCUMENTS: list[RawDocument] = [
    RawDocument(
        country_code="IN",
        state_code="MH",
        district_code="MUM",
        year=2019,
        doc_type=DocType.CASE_LAW,
        serial="4821",
        name="TechCorp Ltd vs Data Protection Board",
        date=date(2019, 3, 14),
        text="""
JUDGMENT

IN THE HIGH COURT OF JUDICATURE AT BOMBAY
Case No. CR/4821/2019

PARTIES:
Petitioner: TechCorp Ltd (software technology company)
Respondent: Data Protection Board of India

FACTS:
TechCorp Ltd suffered a data breach in November 2018 that exposed personal
information of 45,000 registered users including names, email addresses,
and payment card details. The breach occurred due to an unpatched vulnerability
in the company's authentication module.

The Data Protection Board initiated proceedings under Section 43A of the
Information Technology Act, 2000 asserting that TechCorp had failed to
implement reasonable security practices.

HOLDING:
The court finds TechCorp Ltd liable for negligence in maintaining adequate
data security measures. The defendant failed to apply security patches within
a reasonable timeframe and did not maintain an adequate incident response plan.

DAMAGES:
Compensatory damages are awarded at INR 12.5 crore to be distributed among
affected users at INR 2,778 per user (45,000 users affected).

The defendant is further directed to implement a comprehensive information
security management system certified to ISO 27001 within 180 days.

PRECEDENT:
This ruling establishes that software technology companies processing user
data have a duty of care equivalent to that of financial institutions when
the volume of affected users exceeds 10,000.
""",
        jurisdiction=["IN", "MH"],
        tags=["data_breach", "software_liability", "it_act", "negligence"],
        version=1,
    ),
    RawDocument(
        country_code="IN",
        state_code="NA",
        district_code="NA",
        year=2021,
        doc_type=DocType.STATUTE,
        serial="PDPB",
        name="Personal Data Protection Bill 2021 - Key Provisions",
        date=date(2021, 12, 16),
        text="""
PERSONAL DATA PROTECTION BILL 2021
SUMMARY OF KEY PROVISIONS

CHAPTER III: OBLIGATIONS OF DATA FIDUCIARIES

Section 24: Purpose Limitation
A data fiduciary shall process personal data only for the purpose specified at
the time of collection. Processing for any other purpose requires fresh consent.

Section 25: Data Minimisation
Data fiduciaries shall not collect personal data beyond what is necessary for
the stated purpose. Collection of sensitive personal data requires explicit consent.

Section 29: Security Safeguards
Every data fiduciary shall implement security safeguards commensurate with the
sensitivity of the personal data being processed. The Data Protection Authority
may specify standards for different categories of data fiduciaries.

CHAPTER IV: RIGHTS OF DATA PRINCIPALS

Section 34: Right to Correction
Every data principal shall have the right to have inaccurate personal data
corrected and incomplete data completed.

Section 35: Right to Erasure
Every data principal shall have the right to erasure of personal data that
is no longer necessary for the purpose for which it was collected.

CHAPTER V: TRANSFERS OF PERSONAL DATA OUTSIDE INDIA

Section 40: Restricted Transfers
Transfer of personal data outside India shall only be permitted to countries
that provide an adequate level of protection as notified by the Central Government.

PENALTIES:
Section 57: Penalties for data breach - up to INR 15 crore or 4% of global annual
turnover, whichever is higher.
""",
        jurisdiction=["IN"],
        tags=["data_protection", "privacy", "legislation", "consent"],
        version=1,
    ),
    RawDocument(
        country_code="IN",
        state_code="NA",
        district_code="NA",
        year=2022,
        doc_type=DocType.ADVISORY,
        serial="CERT001",
        name="CERT-In Advisory: Mandatory Cybersecurity Reporting",
        date=date(2022, 4, 28),
        text="""
ADVISORY FROM CERT-IN
Indian Computer Emergency Response Team
Advisory No. CERT-In/2022/001

SUBJECT: Mandatory Reporting of Cybersecurity Incidents

All organisations in India are directed to mandatorily report cybersecurity
incidents to CERT-In within 6 hours of noticing such incidents or being brought
to notice about such incidents.

COVERED INCIDENTS:
1. Compromise of critical systems or information
2. Data breach resulting in unauthorised disclosure of personal data
3. Attacks on Internet of Things (IoT) devices and networks
4. Distributed Denial of Service (DDoS) attacks
5. Website defacement or intrusion into a website
6. Malware attacks including ransomware

DATA RETENTION:
All service providers, intermediaries, data centres, and body corporate shall
maintain logs of ICT systems for 180 days and provide the same to CERT-In
upon demand.

NON-COMPLIANCE:
Failure to report incidents within the stipulated time may result in penalties
under Section 70B of the Information Technology Act, 2000 up to INR 1 lakh
per incident.

This advisory supersedes all previous advisories on cybersecurity incident
reporting and is effective immediately.
""",
        jurisdiction=["IN"],
        tags=["cybersecurity", "incident_reporting", "cert_in", "compliance"],
        version=1,
    ),
]


async def seed() -> None:
    await create_tables()
    store = QdrantStore()
    await store.ensure_collections()

    pipeline = IngestionPipeline()
    for doc in _DOCUMENTS:
        result = await pipeline.ingest(doc)
        status = "OK" if result.success else f"FAILED: {result.error}"
        print(f"  {result.document_id}: {status} ({result.chunk_count} chunks)")


if __name__ == "__main__":
    asyncio.run(seed())
