from dataclasses import dataclass
from typing import Iterator, List

MEETING_SUMMARY_LABEL = "Meeting summary:"
ESTIMATION_LABEL = "Generated estimation:"
EXAMPLE_HEADER_TEMPLATE = "--- Example {index} ---"


@dataclass(frozen=True)
class EstimationExample:
    meeting_summary: str
    estimation: str


class EstimationExamplesCollection:
    def __init__(self, examples: List[EstimationExample]) -> None:
        self._examples = examples

    def __iter__(self) -> Iterator[EstimationExample]:
        return iter(self._examples)

    def __len__(self) -> int:
        return len(self._examples)

    def as_context(self) -> str:
        blocks = [self._format_example(index, example) for index, example in enumerate(self._examples, start=1)]
        return "\n\n".join(blocks)

    def _format_example(self, index: int, example: EstimationExample) -> str:
        return (
            f"{EXAMPLE_HEADER_TEMPLATE.format(index=index)}\n"
            f"{MEETING_SUMMARY_LABEL}\n{example.meeting_summary}\n\n"
            f"{ESTIMATION_LABEL}\n{example.estimation.strip()}"
        )


ESTIMATION_EXAMPLES = EstimationExamplesCollection([
    EstimationExample(
        meeting_summary=(
            "The client needs a web platform for inventory management. "
            "They want to track stock levels across multiple warehouses, receive low-stock alerts, "
            "manage suppliers, and generate reports. The system must support different user roles "
            "(admin, warehouse operator, read-only viewer) and integrate with their existing ERP via REST API."
        ),
        estimation="""
## Estimate: Inventory Management Platform

### Task breakdown:
1. UI/UX Design (wireframes + high-fidelity screens): 40 hours
2. Backend API — CRUD for products, warehouses, and stock movements: 60 hours
3. Authentication and role-based access control: 20 hours
4. Low-stock alert engine and notification service: 15 hours
5. Supplier management module: 20 hours
6. Dashboard with real-time metrics and charts: 30 hours
7. ERP integration (REST API client + data mapping): 25 hours
8. Reporting module (PDF/CSV exports): 20 hours
9. Testing and QA (unit + integration + UAT): 30 hours
10. Deployment setup (Docker + CI/CD pipeline): 15 hours

**Total estimated: 275 hours**
**Recommended team: 2 full-stack developers + 1 UX designer (part-time) + 1 QA engineer (part-time)**
**Estimated duration: 10–12 weeks**
""",
    ),
    EstimationExample(
        meeting_summary=(
            "The client is a healthcare clinic that wants a patient appointment booking system. "
            "Patients should be able to register, search for available doctors by specialty, book or cancel appointments, "
            "and receive email/SMS reminders. Doctors need a calendar view of their schedule. "
            "The admin team needs to manage doctor availability and generate monthly occupancy reports. "
            "HIPAA-compliant data handling is required."
        ),
        estimation="""
## Estimate: Patient Appointment Booking System

### Task breakdown:
1. UI/UX Design (patient portal + doctor dashboard + admin panel): 50 hours
2. Patient registration, login, and profile management: 20 hours
3. Doctor search and filtering by specialty/availability: 25 hours
4. Appointment booking and cancellation flow: 30 hours
5. Email and SMS reminder service (SendGrid + Twilio): 20 hours
6. Doctor calendar and schedule management: 35 hours
7. Admin panel — doctor availability and user management: 25 hours
8. Monthly occupancy reporting: 20 hours
9. HIPAA-compliant data handling (encryption at rest/transit, audit logs): 30 hours
10. Testing and QA (unit + integration + security + UAT): 40 hours
11. Deployment setup and infrastructure (AWS + CI/CD): 20 hours

**Total estimated: 315 hours**
**Recommended team: 2 full-stack developers + 1 UX designer (part-time) + 1 QA/security engineer (part-time)**
**Estimated duration: 12–14 weeks**
""",
    ),
])


def get_examples_context() -> str:
    return ESTIMATION_EXAMPLES.as_context()
