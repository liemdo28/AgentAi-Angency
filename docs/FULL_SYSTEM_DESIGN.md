# Full System Design

## Goal

Move the repo from `Agency OS v1` to an `Autonomous Agency` where the system does not only route work, but also plans work, executes deliverables, scores quality, learns from history, and ingests operating data.

## North-star architecture

```text
Inbound signals
  -> Email / form / CRM / file ingestion
  -> Task intake + normalization
  -> Task planner
  -> Department execution graph
  -> Leader scoring + feedback loop
  -> Memory + analytics + dashboards
  -> Human escalation only when threshold is not met
```

## Core layers

### 1. Task layer

This is the missing business layer above handoffs.

Entity model:

- `Task`: the business objective, such as "Launch Tet campaign"
- `Task step`: one department-to-department handoff inside the task
- `Artifact`: structured output produced by one step and consumed by later steps
- `Review event`: score, breakdown, feedback, retry count, reviewer mode

What the repo now has:

- A multi-step planner in `src/tasks/planner.py`
- Task templates for launch, optimization, retention, and reporting
- Step-by-step progression in `src/agents/task_progress.py`

What should come next:

- Persist tasks and steps in a DB
- Support client, project, and priority metadata
- Add deadline, budget, owner, and escalation policy per task

### 2. AI execution layer

Each department needs a real execution contract:

- Inputs it consumes
- Tools it may use
- Outputs it must return
- Quality threshold it must pass

Current repo state:

- Each department has a specialist prompt and execution node
- The graph now supports artifact carry-over between steps
- The system degrades safely when no provider is configured

Next level:

- Tool permissions per department
- Retrieval over historical campaigns and playbooks
- Provider routing by cost, latency, and task criticality
- Human-in-the-loop checkpoints for high-risk outputs

### 3. Scoring and feedback loop

The quality loop should be a first-class subsystem, not just `approve/block`.

Required design:

- Score every step with a rubric and threshold
- Store breakdown by criterion
- Retry only the failing step, not the whole task
- Escalate after retry budget is exhausted
- Track score trends by department, task type, and client

Current repo state:

- `leader_reviewer.py` now supports per-step thresholds and review history
- A failed review loops back to the specialist with feedback
- Heuristic review keeps the system operable offline

Next level:

- Department-specific rubric weights in config
- Secondary reviewer or adversarial review for critical deliverables
- Auto-generated improvement plans from repeated score failures

### 4. Ingestion layer

This is still mostly design-level and should be the next big backend build.

Required flow:

```text
Email / chat / form / shared drive
  -> listener
  -> parser
  -> attachment storage
  -> entity extraction
  -> task creation
  -> graph execution
```

Recommended components:

- Email listener for Gmail/IMAP/Graph API
- File parser for PDF, DOCX, CSV, image OCR
- Intake normalizer that converts raw messages into `Task + initial artifacts`
- Deduplication and idempotency keys

### 5. Memory layer

To behave like a long-running agency, the system needs memory across runs.

Memory domains:

- Client memory: tone, approvals, constraints, brand rules
- Project memory: briefs, revisions, performance, stakeholder notes
- Department memory: reusable playbooks and learnings
- Tool memory: historical search, benchmarks, model outputs, evaluations

Recommended storage split:

- Relational DB for tasks, steps, users, projects, reviews
- Object storage for files and generated artifacts
- Vector store for reusable context and campaign learnings

### 6. Control plane and observability

An owner-grade system needs visibility.

Dashboard capabilities:

- Active tasks by stage
- Score distribution by department
- Retry and escalation rates
- SLA misses
- Artifact lineage
- Cost per task and per department

Operational controls:

- Pause/resume tasks
- Re-run a single step
- Override a route
- Force human approval

## Proposed runtime model

### Phase A: local operating system

- Multi-step tasks
- Step quality thresholds
- Local persistence
- CLI and lightweight API

### Phase B: supervised autonomous agency

- Real LLM and tool integrations
- Ingestion from email/files
- Dashboard and queue management
- Human review queues

### Phase C: scalable product

- Multi-client isolation
- Projects and tenants
- Role-based access
- Cost controls, evaluation suite, analytics warehouse

## Immediate roadmap

### 1-2 weeks

- Persist tasks and review history
- Add FastAPI endpoints for task creation and task inspection
- Add tests for task planning, retry flow, and fallback behavior
- Clean legacy repo issues and remove tracked/generated garbage

### 2-4 weeks

- Connect OpenAI/Anthropic tools for real execution
- Add search, file reading, and structured analysis tools per department
- Build ingestion pipeline for email and attachments

### 4+ weeks

- Add dashboard
- Add client/project model
- Add memory + vector retrieval
- Add evaluation harness and production monitoring

## Design principle

The system should always answer these five questions:

1. What business task are we trying to finish?
2. Which step is currently executing?
3. What artifact was produced and by whom?
4. Did the output pass the quality bar?
5. If not, did we retry, reroute, or escalate?

If those five are observable, the repo is evolving from a workflow demo into a real agency system.
