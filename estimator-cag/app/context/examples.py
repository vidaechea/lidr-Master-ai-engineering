import json
from dataclasses import dataclass

from app.schemas.estimation import ExampleFormat

MEETING_SUMMARY_LABEL = "Meeting summary:"
ESTIMATION_LABEL = "Generated estimation:"
EXAMPLE_HEADER_TEMPLATE = "--- Example {index} ---"


@dataclass
class EstimationExample:
    title: str
    meeting_summary: str
    breakdown: list[tuple[str, int, int]]
    total_hours: int
    total_cost: int
    team: list[str]
    duration_weeks: int
    estimation_markdown: str


def _format_single_example(index: int, example: EstimationExample) -> str:
    return (
        f"{EXAMPLE_HEADER_TEMPLATE.format(index=index)}\n"
        f"{MEETING_SUMMARY_LABEL}\n{example.meeting_summary}\n\n"
        f"{ESTIMATION_LABEL}\n{example.estimation_markdown.strip()}"
    )


def select_examples(n: int) -> list[EstimationExample]:
    """Return the first *n* examples from ESTIMATION_EXAMPLES."""
    return ESTIMATION_EXAMPLES[:n]


def format_examples_for_prompt(
    examples: list[EstimationExample],
    fmt: ExampleFormat = ExampleFormat.MARKDOWN,
) -> str:
    if fmt == ExampleFormat.MARKDOWN:
        blocks = [_format_single_example(i, ex) for i, ex in enumerate(examples, start=1)]
        return "\n\n".join(blocks)

    if fmt == ExampleFormat.JSON:
        payload = [
            {
                "index": i,
                "title": ex.title,
                "meeting_summary": ex.meeting_summary,
                "breakdown": [
                    {"task": task, "hours": hours, "cost_eur": cost}
                    for task, hours, cost in ex.breakdown
                ],
                "total_hours": ex.total_hours,
                "total_cost_eur": ex.total_cost,
                "team": ex.team,
                "duration_weeks": ex.duration_weeks,
            }
            for i, ex in enumerate(examples, start=1)
        ]
        return json.dumps(payload, ensure_ascii=False, indent=2)

    if fmt == ExampleFormat.NARRATIVE:
        blocks: list[str] = []
        for i, ex in enumerate(examples, start=1):
            team_str = ", ".join(ex.team)
            tasks_str = "; ".join(
                f"{task} ({hours}h, {cost} EUR)"
                for task, hours, cost in ex.breakdown
            )
            block = (
                f"Example {i} — {ex.title}. "
                f"Client request: {ex.meeting_summary} "
                f"The work was broken down as follows: {tasks_str}. "
                f"Total effort: {ex.total_hours} hours over {ex.duration_weeks} weeks, "
                f"costing {ex.total_cost} EUR. "
                f"Recommended team: {team_str}."
            )
            blocks.append(block)
        return "\n\n".join(blocks)

    raise ValueError(f"Unsupported format: {fmt}")


ESTIMATION_EXAMPLES: list[EstimationExample] = [
    EstimationExample(
        title="Inventory Management Platform",
        meeting_summary=(
            "The client needs a web platform for inventory management. "
            "They want to track stock levels across multiple warehouses, receive low-stock alerts, "
            "manage suppliers, and generate reports. The system must support different user roles "
            "(admin, warehouse operator, read-only viewer) and integrate with their existing ERP via REST API."
        ),
        breakdown=[
            ("UI/UX design (wireframes + high-fidelity screens)", 40, 2500),
            ("Backend API — CRUD for products, warehouses, and stock movements", 60, 3750),
            ("Authentication and role-based access control", 20, 1250),
            ("Low-stock alert engine and notification service", 15, 937),
            ("Supplier management module", 20, 1250),
            ("Dashboard with real-time metrics and charts", 30, 1875),
            ("ERP integration (REST API client + data mapping)", 25, 1562),
            ("Reporting module (PDF/CSV exports)", 20, 1250),
            ("Testing and QA (unit + integration + UAT)", 30, 1875),
            ("Deployment setup (Docker + CI/CD pipeline)", 15, 937),
        ],
        total_hours=275,
        total_cost=17186,
        team=[
            "2 Full-Stack Developers",
            "1 UX Designer (part-time)",
            "1 QA Engineer (part-time)",
        ],
        duration_weeks=11,
        estimation_markdown="""\
## Estimate: Inventory Management Platform

### Task Breakdown

| Task | Hours | Cost (EUR) |
|------|------:|------------|
| UI/UX design (wireframes + high-fidelity screens) | 40 | 2,500 |
| Backend API — CRUD for products, warehouses, and stock movements | 60 | 3,750 |
| Authentication and role-based access control | 20 | 1,250 |
| Low-stock alert engine and notification service | 15 | 937 |
| Supplier management module | 20 | 1,250 |
| Dashboard with real-time metrics and charts | 30 | 1,875 |
| ERP integration (REST API client + data mapping) | 25 | 1,562 |
| Reporting module (PDF/CSV exports) | 20 | 1,250 |
| Testing and QA (unit + integration + UAT) | 30 | 1,875 |
| Deployment setup (Docker + CI/CD pipeline) | 15 | 937 |

### Totals

- **Total hours:** 275
- **Total cost:** 17,186 EUR

### Recommended Team

- 2 Full-Stack Developers
- 1 UX Designer (part-time)
- 1 QA Engineer (part-time)

### Estimated Duration

**11 weeks** with a two-person development team and part-time specialist support.""",
    ),
    EstimationExample(
        title="Patient Appointment Booking System",
        meeting_summary=(
            "The client is a healthcare clinic that wants a patient appointment booking system. "
            "Patients should be able to register, search for available doctors by specialty, book or cancel appointments, "
            "and receive email/SMS reminders. Doctors need a calendar view of their schedule. "
            "The admin team needs to manage doctor availability and generate monthly occupancy reports. "
            "HIPAA-compliant data handling is required."
        ),
        breakdown=[
            ("UI/UX design (patient portal + doctor dashboard + admin panel)", 50, 3125),
            ("Patient registration, login, and profile management", 20, 1250),
            ("Doctor search and filtering by specialty/availability", 25, 1562),
            ("Appointment booking and cancellation flow", 30, 1875),
            ("Email and SMS reminder service (SendGrid + Twilio)", 20, 1250),
            ("Doctor calendar and schedule management", 35, 2187),
            ("Admin panel — doctor availability and user management", 25, 1562),
            ("Monthly occupancy reporting", 20, 1250),
            ("HIPAA-compliant data handling (encryption at rest/transit, audit logs)", 30, 1875),
            ("Testing and QA (unit + integration + security + UAT)", 40, 2500),
            ("Deployment setup and infrastructure (AWS + CI/CD)", 20, 1250),
        ],
        total_hours=315,
        total_cost=19686,
        team=[
            "2 Full-Stack Developers",
            "1 UX Designer (part-time)",
            "1 QA/Security Engineer (part-time)",
        ],
        duration_weeks=13,
        estimation_markdown="""\
## Estimate: Patient Appointment Booking System

### Task Breakdown

| Task | Hours | Cost (EUR) |
|------|------:|------------|
| UI/UX design (patient portal + doctor dashboard + admin panel) | 50 | 3,125 |
| Patient registration, login, and profile management | 20 | 1,250 |
| Doctor search and filtering by specialty/availability | 25 | 1,562 |
| Appointment booking and cancellation flow | 30 | 1,875 |
| Email and SMS reminder service (SendGrid + Twilio) | 20 | 1,250 |
| Doctor calendar and schedule management | 35 | 2,187 |
| Admin panel — doctor availability and user management | 25 | 1,562 |
| Monthly occupancy reporting | 20 | 1,250 |
| HIPAA-compliant data handling (encryption at rest/transit, audit logs) | 30 | 1,875 |
| Testing and QA (unit + integration + security + UAT) | 40 | 2,500 |
| Deployment setup and infrastructure (AWS + CI/CD) | 20 | 1,250 |

### Totals

- **Total hours:** 315
- **Total cost:** 19,686 EUR

### Recommended Team

- 2 Full-Stack Developers
- 1 UX Designer (part-time)
- 1 QA/Security Engineer (part-time)

### Estimated Duration

**13 weeks** with a two-person development team and part-time specialist support.""",
    ),
    EstimationExample(
        title="SaaS Subscription Platform",
        meeting_summary=(
            "A startup wants to build a SaaS subscription platform where businesses can offer tiered plans "
            "(free, pro, enterprise) to their customers. The platform must handle plan upgrades and downgrades, "
            "metered usage billing, Stripe payment processing, feature flagging per plan, "
            "an admin revenue dashboard with MRR/churn metrics, and automated email lifecycle campaigns "
            "(onboarding, renewal reminders, churn win-back). A public REST API with webhooks is required "
            "so customers can integrate billing events into their own systems."
        ),
        breakdown=[
            ("UI/UX design (marketing site + app dashboard + billing portal)", 45, 2812),
            ("User authentication — OAuth2, MFA, and SSO (Google/GitHub)", 25, 1562),
            ("Subscription plan engine — tiers, upgrades, downgrades, and trials", 30, 1875),
            ("Stripe payment gateway integration (cards, SEPA, invoices)", 30, 1875),
            ("Feature flagging and plan entitlement service", 20, 1250),
            ("Usage tracking and metered billing (API calls, seats)", 25, 1562),
            ("Admin dashboard — user management and revenue analytics (MRR, churn)", 35, 2187),
            ("Email lifecycle campaigns (SendGrid — onboarding, renewal, win-back)", 20, 1250),
            ("Public REST API and outbound webhooks for billing events", 25, 1562),
            ("Testing and QA (unit + integration + Stripe payment flows)", 35, 2187),
            ("Deployment and infrastructure (AWS ECS + CI/CD + staging)", 20, 1250),
        ],
        total_hours=310,
        total_cost=19375,
        team=[
            "2 Full-Stack Developers",
            "1 UX Designer (part-time)",
            "1 QA Engineer (part-time)",
        ],
        duration_weeks=12,
        estimation_markdown="""\
## Estimate: SaaS Subscription Platform

### Task Breakdown

| Task | Hours | Cost (EUR) |
|------|------:|------------|
| UI/UX design (marketing site + app dashboard + billing portal) | 45 | 2,812 |
| User authentication — OAuth2, MFA, and SSO (Google/GitHub) | 25 | 1,562 |
| Subscription plan engine — tiers, upgrades, downgrades, and trials | 30 | 1,875 |
| Stripe payment gateway integration (cards, SEPA, invoices) | 30 | 1,875 |
| Feature flagging and plan entitlement service | 20 | 1,250 |
| Usage tracking and metered billing (API calls, seats) | 25 | 1,562 |
| Admin dashboard — user management and revenue analytics (MRR, churn) | 35 | 2,187 |
| Email lifecycle campaigns (SendGrid — onboarding, renewal, win-back) | 20 | 1,250 |
| Public REST API and outbound webhooks for billing events | 25 | 1,562 |
| Testing and QA (unit + integration + Stripe payment flows) | 35 | 2,187 |
| Deployment and infrastructure (AWS ECS + CI/CD + staging) | 20 | 1,250 |

### Totals

- **Total hours:** 310
- **Total cost:** 19,375 EUR

### Recommended Team

- 2 Full-Stack Developers
- 1 UX Designer (part-time)
- 1 QA Engineer (part-time)

### Estimated Duration

**12 weeks** with a two-person development team and part-time specialist support.""",
    ),
    EstimationExample(
        title="AI Chatbot Integration Platform",
        meeting_summary=(
            "The client wants to build a white-label AI chatbot platform that businesses can embed on their websites. "
            "The platform must support knowledge base ingestion (PDF, URLs, plain text), use Retrieval-Augmented Generation "
            "(RAG) with a vector database, and abstract multiple LLM providers (OpenAI, Anthropic). "
            "Each chatbot must maintain conversation history and context across sessions. "
            "An admin console is needed to configure chatbot personas, view analytics (resolution rate, handoff rate), "
            "and manage escalation-to-human-agent workflows. Rate limiting, content moderation, and abuse detection "
            "are required before production launch."
        ),
        breakdown=[
            ("UI/UX design (embeddable chat widget + admin console)", 40, 2500),
            ("Embeddable chatbot widget (vanilla JS + React host app)", 35, 2187),
            ("LLM provider abstraction layer (OpenAI + Anthropic with fallback)", 30, 1875),
            ("Knowledge base ingestion pipeline (PDF, URL, plain text to chunks)", 35, 2187),
            ("Vector database integration (pgvector/Pinecone) and RAG retrieval", 30, 1875),
            ("Conversation history and multi-turn context management", 20, 1250),
            ("Admin console — chatbot configuration, personas, and analytics", 30, 1875),
            ("Escalation-to-human-agent workflow and handoff API", 20, 1250),
            ("Rate limiting, abuse detection, and LLM content moderation", 20, 1250),
            ("Testing and QA (unit + integration + prompt regression suite)", 35, 2187),
            ("Deployment and infrastructure (Docker + Kubernetes + auto-scaling)", 25, 1562),
        ],
        total_hours=320,
        total_cost=20000,
        team=[
            "2 Full-Stack Developers",
            "1 ML / AI Engineer",
            "1 QA Engineer (part-time)",
        ],
        duration_weeks=13,
        estimation_markdown="""\
## Estimate: AI Chatbot Integration Platform

### Task Breakdown

| Task | Hours | Cost (EUR) |
|------|------:|------------|
| UI/UX design (embeddable chat widget + admin console) | 40 | 2,500 |
| Embeddable chatbot widget (vanilla JS + React host app) | 35 | 2,187 |
| LLM provider abstraction layer (OpenAI + Anthropic with fallback) | 30 | 1,875 |
| Knowledge base ingestion pipeline (PDF, URL, plain text to chunks) | 35 | 2,187 |
| Vector database integration (pgvector/Pinecone) and RAG retrieval | 30 | 1,875 |
| Conversation history and multi-turn context management | 20 | 1,250 |
| Admin console — chatbot configuration, personas, and analytics | 30 | 1,875 |
| Escalation-to-human-agent workflow and handoff API | 20 | 1,250 |
| Rate limiting, abuse detection, and LLM content moderation | 20 | 1,250 |
| Testing and QA (unit + integration + prompt regression suite) | 35 | 2,187 |
| Deployment and infrastructure (Docker + Kubernetes + auto-scaling) | 25 | 1,562 |

### Totals

- **Total hours:** 320
- **Total cost:** 20,000 EUR

### Recommended Team

- 2 Full-Stack Developers
- 1 ML / AI Engineer
- 1 QA Engineer (part-time)

### Estimated Duration

**13 weeks** with a three-person core team and part-time QA support.""",
    ),
    EstimationExample(
        title="Multi-tenant Billing System",
        meeting_summary=(
            "A B2B software company needs a multi-tenant billing system to serve hundreds of independent tenants, "
            "each with their own subscription plans, add-ons, usage-based charges, and invoicing preferences. "
            "The system must support multi-currency processing (EUR, USD, GBP) via Stripe and PayPal, "
            "automated proration on mid-cycle plan changes, VAT/GST tax calculation per jurisdiction (TaxJar), "
            "dunning management for failed payments with configurable retry logic, "
            "PDF invoice generation and delivery, and strict tenant data isolation via row-level security. "
            "A super-admin dashboard must expose MRR, ARR, churn, and revenue-by-tenant analytics. "
            "A full audit log of all billing events is required for compliance."
        ),
        breakdown=[
            ("UI/UX design (tenant billing portal + super-admin dashboard)", 50, 3125),
            ("Tenant provisioning and onboarding API (with plan assignment)", 30, 1875),
            ("Multi-currency payment processing — Stripe + PayPal integration", 35, 2187),
            ("Subscription plan engine — tiers, add-ons, discounts, and coupons", 35, 2187),
            ("Usage-based metering and mid-cycle proration logic", 40, 2500),
            ("PDF invoice generation and email delivery (WeasyPrint + SendGrid)", 25, 1562),
            ("Tax calculation and compliance — VAT/GST per jurisdiction (TaxJar)", 30, 1875),
            ("Dunning management — failed payment detection and retry scheduling", 20, 1250),
            ("Revenue analytics dashboard — MRR, ARR, churn, and tenant breakdown", 30, 1875),
            ("Tenant data isolation — row-level security and scoped API tokens", 25, 1562),
            ("Testing and QA (unit + integration + billing edge cases + load tests)", 40, 2500),
            ("Deployment and infrastructure — multi-region AWS + CI/CD", 25, 1562),
        ],
        total_hours=385,
        total_cost=24062,
        team=[
            "2 Backend Developers",
            "1 Full-Stack Developer",
            "1 UX Designer (part-time)",
            "1 QA Engineer (part-time)",
        ],
        duration_weeks=15,
        estimation_markdown="""\
## Estimate: Multi-tenant Billing System

### Task Breakdown

| Task | Hours | Cost (EUR) |
|------|------:|------------|
| UI/UX design (tenant billing portal + super-admin dashboard) | 50 | 3,125 |
| Tenant provisioning and onboarding API (with plan assignment) | 30 | 1,875 |
| Multi-currency payment processing — Stripe + PayPal integration | 35 | 2,187 |
| Subscription plan engine — tiers, add-ons, discounts, and coupons | 35 | 2,187 |
| Usage-based metering and mid-cycle proration logic | 40 | 2,500 |
| PDF invoice generation and email delivery (WeasyPrint + SendGrid) | 25 | 1,562 |
| Tax calculation and compliance — VAT/GST per jurisdiction (TaxJar) | 30 | 1,875 |
| Dunning management — failed payment detection and retry scheduling | 20 | 1,250 |
| Revenue analytics dashboard — MRR, ARR, churn, and tenant breakdown | 30 | 1,875 |
| Tenant data isolation — row-level security and scoped API tokens | 25 | 1,562 |
| Testing and QA (unit + integration + billing edge cases + load tests) | 40 | 2,500 |
| Deployment and infrastructure — multi-region AWS + CI/CD | 25 | 1,562 |

### Totals

- **Total hours:** 385
- **Total cost:** 24,062 EUR

### Recommended Team

- 2 Backend Developers
- 1 Full-Stack Developer
- 1 UX Designer (part-time)
- 1 QA Engineer (part-time)

### Estimated Duration

**15 weeks** with a three-person development team and part-time specialist support.""",
    ),
]
