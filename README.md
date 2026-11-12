# PayShield AI

### Trust Operating System for Agentic Commerce

**Let AI act. Keep humans in control.**

PayShield AI is an open-source trust and security layer designed for agentic commerce. It helps evaluate AI-driven purchasing requests before they proceed by combining transaction context, risk assessment, policy enforcement, and decision-making.

As AI agents become more capable of discovering products and making purchasing decisions, trust, transparency, and human oversight become essential.

PayShield AI addresses this challenge by introducing a governance layer between autonomous AI agents and payment systems.

---

## The Problem

AI agents are increasingly capable of researching products, comparing options, and initiating purchasing workflows.

However, autonomous purchasing introduces important questions:

- Is the purchasing request legitimate?
- Does the transaction comply with the applicable policies?
- Is the transaction potentially risky?
- Should the request proceed, require human review, or be blocked?
- Can users trace why a decision was made?

PayShield AI aims to address these challenges through a structured transaction evaluation and governance workflow.

## Our Solution

PayShield AI evaluates purchasing requests through a sequence of security and governance checks.

Instead of allowing an AI agent to make unrestricted purchasing decisions, PayShield introduces a risk engine, policy engine, and decision engine.

Every evaluated request receives one of three outcomes:

| Decision | Meaning |
|---|---|
| ALLOW | The transaction satisfies the required checks. |
| REVIEW | Additional human attention is required. |
| BLOCK | The transaction violates defined security or policy requirements. |

## Key Features

### 1. Product Discovery
Discover relevant products through the integrated product search workflow.

### 2. Product Comparison
Compare multiple products side by side. For example, evaluate three laptops using their available product information before making a purchasing decision.

### 3. AI Shopping Assistant
Interact with an AI assistant to ask questions, explore products, and evaluate purchasing requests.

### 4. Risk Assessment
Evaluate transaction context and assign a risk level:

- LOW
- MEDIUM
- HIGH

### 5. Policy Enforcement
Apply predefined policy rules to determine whether a purchasing request satisfies the required conditions.

### 6. Intelligent Decision Engine
Combine risk assessment and policy evaluation to generate an ALLOW, REVIEW, or BLOCK decision.

### 7. Receipts and Audit History
Maintain transaction records, receipts, and audit history to improve traceability and transparency.

### 8. PayPal Sandbox Integration
Explore payment-related workflows using PayPal Sandbox. The project is a prototype and does not represent a production payment-processing service.

---

## System Architecture

```text
          AI Shopping Agent
                  |
                  v
          Transaction Request
                  |
                  v
          PayShield AI Backend
                  |
          +-------+-------+
          |               |
          v               v
      Risk Engine     Policy Engine
          |               |
          +-------+-------+
                  |
                  v
           Decision Engine
                  |
          +-------+-------+
          |       |       |
          v       v       v
        ALLOW   REVIEW   BLOCK
                  |
                  v
          Transaction Records
                  |
                  v
          Receipts & Audit Logs
```

The AI assistant supports the workflow, while the backend risk and policy logic governs the final decision.

## Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | React, TypeScript, Vite |
| UI Components | shadcn/ui |
| Backend | Python, FastAPI |
| Database | SQLite |
| AI | GroqCloud, Ollama |
| Product Discovery | Channel3 integration |
| Payment Sandbox | PayPal Orders API and Payments API |
| Testing | Pytest, frontend tests, Playwright |

## How It Works

1. A user discovers products or submits a purchasing request.
2. PayShield receives the transaction context.
3. The risk engine evaluates the request.
4. The policy engine checks applicable rules.
5. The decision engine combines the evaluation results.
6. PayShield returns ALLOW, REVIEW, or BLOCK.
7. Transaction-related records and audit information support traceability.

## Project Structure

The repository is organized into backend and frontend components.

```text
PayShield-AI/
│
├── backend/
│   ├── assistant/
│   ├── payshield/
│   ├── policy/
│   └── ...
│
├── frontend/
│   ├── src/
│   ├── public/
│   └── ...
│
├── tests/
├── render.yaml
├── .env.example
├── DESIGN.md
└── PRODUCT.md
```

## Getting Started

### Prerequisites

- Python
- Node.js and npm
- Git
- A local SQLite environment
- Optional provider credentials for integrations you want to test

### 1. Clone the Repository

```bash
git clone https://github.com/prajwalyr849-sudo/PayShield-AI.git
cd PayShield-AI
```

### 2. Configure Environment Variables

Use the provided `.env.example` as a reference.

Create your local environment configuration and add the credentials required for the integrations you intend to use.

**Never commit your `.env` file, API keys, access tokens, or payment credentials.**

### 3. Install Dependencies

Install the backend dependencies using the dependency configuration included in the backend project.

Install frontend dependencies:

```bash
cd frontend
npm install
```

### 4. Run the Application

Start the backend using the project's configured FastAPI entry point.

Start the frontend development server:

```bash
cd frontend
npm run dev
```

Refer to the repository's current configuration and documentation for the exact backend startup command and required environment variables.

---

## Security and Trust Principles

PayShield AI is built around several principles:

- **Human oversight:** Risky or uncertain decisions can require human review.
- **Policy enforcement:** Purchasing requests are evaluated against defined rules.
- **Risk awareness:** Transaction context contributes to risk assessment.
- **Traceability:** Decisions can be examined through transaction records and audit history.
- **Credential protection:** Sensitive integration credentials should remain in server-side environment configuration.
- **Controlled execution:** AI-generated recommendations do not independently authorize payment execution.

## Current Project Status

PayShield AI is an open-source hackathon prototype demonstrating a governance approach for agentic commerce.

The prototype includes product discovery, product comparison, AI-assisted purchasing evaluation, risk assessment, policy decisions, transaction records, and PayPal Sandbox-related workflows.

It is not a production-ready payment processor or a guarantee against fraudulent transactions. Provider integrations and payment workflows should be independently tested before any production deployment.

## Future Improvements

Potential development directions include:

- Cryptographic verification of agent payment mandates.
- Stronger transaction-state integrity checks.
- Tamper-evident audit logging.
- Context-aware risk scoring.
- Adversarial security testing for AI agents.
- Stronger isolation of AI and payment credentials.
- Expanded interoperability with agentic commerce protocols.

## Contributing

Contributions, ideas, bug reports, and security feedback are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Make your changes.
4. Run relevant tests.
5. Submit a pull request with a clear explanation of your changes.

## License

Add the project's chosen open-source license before distributing or accepting external contributions.

---

## Project Vision

We believe autonomous AI should be powerful without becoming uncontrolled.

PayShield AI aims to make agentic commerce more transparent, accountable, and secure.

**Let AI act. Keep humans in control.**

Built with the vision of a safer future for AI-powered commerce.

**GitHub:** https://github.com/prajwalyr849-sudo/PayShield-AI
