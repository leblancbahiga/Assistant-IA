# NURU — AGENTS.md

## 1. Purpose

This repository contains **NURU**, a local-first AI assistant designed to run efficiently on constrained hardware and provide reliable document analysis, RAG, memory, tools, model orchestration and an interactive user interface.

This file defines the engineering rules that all Hermes agents working on NURU MUST follow.

The Hermes agents are external development agents operated by Hermes.

**NURU itself must not be modified to implement this agent orchestration system.**

---

## 2. Project Workspace

The canonical local NURU workspace used by the Hermes development team is:

```text
/Users/leblancbahiga/Downloads/Assistant IA
```

All development agents MUST treat this directory as the primary NURU working directory.

Before performing any operation, agents MUST verify that this directory exists and corresponds to the intended NURU repository.

Agents MUST NOT assume that another local clone is the canonical workspace.

The Git repository associated with this workspace is:

```text
leblancbahiga/Assistant-IA
```

The local workspace is the source of truth for development operations.

---
Cost-aware execution is mandatory. Agents must minimize unnecessary context, redundant repository exploration, repeated analysis and unnecessary delegation.

## 3. Agent Team

The NURU development team consists of five Hermes profiles.

### nuru-lead

Role:
- Analyze user requests.
- Decompose complex work.
- Create and manage Kanban tasks.
- Assign work to the appropriate specialist.
- Manage dependencies.
- Validate the overall workflow.
- Decide when a task is complete.

Restrictions:
- MUST NOT implement production code.
- MUST NOT bypass the required validation workflow.
- MUST NOT declare completion solely because another agent claims success.

---

### nuru-architect

Role:
- Analyze the existing NURU architecture.
- Identify affected components.
- Determine where a change belongs.
- Produce implementation plans.
- Identify dependencies, risks and architectural consequences.
- Define acceptance criteria.

Restrictions:
- MUST NOT modify production code.
- MUST NOT perform opportunistic refactoring.
- MUST NOT create a parallel architecture when an existing component can be extended safely.

---

### nuru-coder

Role:
- Implement approved technical changes.
- Modify source code within the assigned scope.
- Add or update tests.
- Execute relevant validation.
- Report all changes.

Restrictions:
- MUST NOT redesign architecture without approval.
- MUST NOT expand task scope without justification.
- MUST NOT modify unrelated files.
- MUST NOT remove existing functionality merely to simplify implementation.
- MUST NOT declare a task complete without executing the required tests.

---

### nuru-tester

Role:
- Execute tests.
- Reproduce reported bugs.
- Diagnose failures.
- Run unit, integration and regression tests.
- Run static/type/lint checks where applicable.
- Produce objective test reports.

Restrictions:
- MUST NOT fix production code.
- MUST NOT silently modify tests to make them pass.
- MUST NOT hide or downgrade failures.
- MUST distinguish between a test failure and an environment failure.

---

### nuru-reviewer

Role:
- Independently review implementations.
- Compare requirements against the implementation.
- Inspect the actual Git diff.
- Check architectural compliance.
- Identify regressions and hidden defects.
- Return PASS or FAIL with actionable findings.

Restrictions:
- MUST NOT modify production code.
- MUST NOT approve an implementation merely because tests pass.
- MUST inspect the actual changed files.
- MUST remain independent from the Coder's conclusions.

---

## 4. Fundamental Principle

The team follows:

    LEAD
      ↓
    ARCHITECT
      ↓
    CODER
      ↓
    TESTER
      ↓
    REVIEWER
      ↓
    DONE

For a non-trivial production-code change, this sequence MUST NOT be bypassed.

When a validation step fails, the task returns to the appropriate previous stage.

---

## 5. Repository First

Before modifying anything, agents MUST understand the existing repository.

The canonical workspace is:

```text
/Users/leblancbahiga/Downloads/Assistant IA
```

Agents MUST inspect the actual files rather than relying on assumptions, previous conversations, generated summaries or stale documentation.

Search the repository before creating:
- new modules;
- new services;
- new managers;
- new abstractions;
- duplicate utilities;
- alternative implementations of existing functionality.

Existing NURU architecture takes precedence over assumptions.

---

## 6. Existing Architecture

NURU contains existing subsystems including, but not limited to:

- agent system;
- kernel/core services;
- RAG;
- memory;
- routing;
- model/providers;
- tools;
- research/web functionality;
- UI;
- configuration;
- learning/tracking;
- recovery and verification mechanisms.

Relevant existing code must be inspected before introducing replacements.

In particular, the repository already contains agent-related infrastructure.

Do NOT create a second agent framework merely because Hermes is being used externally.

Hermes agents are the development team.

They are NOT NURU runtime components.

---

## 7. Architecture Rules

### 7.1 Extend before replacing

Prefer:

    existing component
          ↓
    controlled extension

over:

    existing component
          ↓
       rewrite
          ↓
    parallel replacement

A rewrite requires explicit architectural justification.

### 7.2 No duplicate systems

Do not create competing implementations of:

- routing;
- memory;
- RAG;
- model selection;
- tool execution;
- event handling;
- configuration;
- agent orchestration;
- logging;
- persistence.

If an existing implementation is inadequate, document why before replacing it.

### 7.3 Kernel integrity

The kernel/core architecture must remain coherent.

New functionality must have:
- a clear ownership boundary;
- a defined lifecycle;
- explicit dependencies;
- predictable initialization;
- predictable shutdown;
- test coverage.

Avoid importing high-level UI or feature modules into low-level core infrastructure.

---

## 8. RAG Rules

RAG changes are considered high-risk.

Any modification affecting:

- document extraction;
- chunking;
- embeddings;
- indexing;
- retrieval;
- scoring;
- reranking;
- context gating;
- context assembly;
- citation/source tracking;

must be tested end-to-end.

Never assume that successful indexing means successful retrieval.

Never assume that a vector score alone proves retrieval correctness.

The complete pipeline must be considered:

    document
       ↓
    extraction
       ↓
    chunking
       ↓
    embedding
       ↓
    indexing
       ↓
    retrieval
       ↓
    scoring
       ↓
    context selection
       ↓
    LLM

A change at one stage must be checked for downstream effects.

---

## 9. Memory Rules

Memory-related changes must consider:

- persistence;
- retrieval;
- embedding;
- asynchronous execution;
- duplication;
- cleanup;
- lifecycle;
- failure recovery.

Async operations MUST be correctly awaited.

No coroutine may be silently created and discarded.

Memory operations must not introduce unbounded growth.

---

## 10. Async Rules

NURU uses asynchronous operations in several subsystems.

Agents MUST verify:

- every async function is awaited where required;
- synchronous blocking operations are not introduced into async paths without justification;
- tasks are properly cancelled;
- exceptions from background tasks are observable;
- no orphaned tasks remain after shutdown.

Do not solve an async problem by blindly wrapping it in synchronous execution.

---

## 11. Performance Rules

NURU must remain usable on constrained local hardware.

Performance-sensitive changes must consider:

- RAM;
- CPU;
- model loading;
- embedding cost;
- RAG latency;
- router latency;
- startup time;
- context size;
- subprocess count;
- concurrency;
- cache growth.

Avoid:
- loading multiple unnecessary model instances;
- loading entire documents when only a portion is required;
- unbounded caches;
- unnecessary subprocesses;
- blocking operations on the UI thread;
- unnecessary LLM calls.

### Router target

The routing path should remain extremely lightweight.

Target:

    routing decision < 5 ms

LLM-based classification should not be used when deterministic or lightweight routing is sufficient.

---

## 12. Scope Control

Every implementation task MUST define its scope.

The Coder should know:

- objective;
- allowed files;
- expected files;
- architectural constraints;
- acceptance criteria;
- required tests.

Do not modify unrelated files.

Do not perform unrelated cleanup.

Do not combine:
- feature implementation;
- large refactoring;
- dependency upgrades;
- formatting migrations;

unless explicitly required.

Small, reviewable changes are preferred.

---

## 13. Dependency Changes

Do not add or upgrade dependencies casually.

Before changing dependencies, determine:

1. Why the dependency is required.
2. Whether an existing dependency already provides the functionality.
3. Compatibility with the current Python/runtime environment.
4. Impact on startup and memory.
5. Impact on the M1/8 GB target environment.
6. Whether the dependency is actively maintained.

Dependency changes require explicit testing.

---

## 14. Error Handling

Errors must be observable and actionable.

Do not:

- use broad silent exception handling;
- swallow exceptions;
- return fake success values;
- hide failures from the user or orchestrator;
- convert an operational failure into an apparent success.

Prefer structured errors containing:

- operation;
- component;
- error type;
- message;
- relevant context;
- correlation/task identifier when available.

---
Cost-aware execution is mandatory. Agents must minimize unnecessary context, redundant repository exploration, repeated analysis and unnecessary delegation.
---

## 15. Logging and Observability

Important operations should be observable.

For significant workflows, logs should allow an engineer to determine:

- what happened;
- where it happened;
- when it happened;
- which task triggered it;
- whether it succeeded;
- why it failed.

Avoid excessive logging of:
- secrets;
- credentials;
- tokens;
- private user content.

---

## 16. Testing Requirements

A production-code change is not complete until appropriate tests have been executed.

Depending on scope, this can include:

### Unit tests

Verify isolated behavior.

### Integration tests

Verify interaction between components.

### Regression tests

Verify that the reported bug cannot silently return.

### Static checks

Where configured:

- lint;
- type checking;
- syntax/compile checks;
- import checks.

### Smoke tests

Verify that NURU starts and the affected subsystem remains operational.

---

## 17. Bug-Fixing Protocol

For a reported bug:

    1. Reproduce
    2. Identify root cause
    3. Define regression test
    4. Design fix
    5. Implement fix
    6. Run regression test
    7. Run relevant existing tests
    8. Review diff
    9. Verify no regression
    10. Close task

Do not implement a speculative fix before establishing the failure mechanism when reproduction is possible.

---

## 18. Reviewer Protocol

The Reviewer must evaluate four independent dimensions:

### Requirement

Does the implementation actually solve the requested problem?

### Architecture

Does it fit the existing NURU architecture?

### Implementation

Is the code correct, maintainable and appropriately scoped?

### Evidence

Do tests and validation actually support the claim that it works?

A passing test suite is evidence, not proof of correctness.

The Reviewer must inspect the Git diff.

---

## 19. Tester Protocol

The Tester reports facts, not opinions.

Every test report should distinguish:

    PASS
    FAIL
    BLOCKED
    NOT RUN

If a test cannot run because of an environment problem, report:

    BLOCKED — ENVIRONMENT

Do not report:

    PASS

when the test was not actually executed.

The Tester must not change production code to make a test pass.

---

## 20. Git Rules

The Git repository is located at:

```text
/Users/leblancbahiga/Downloads/Assistant IA
```

Never work directly on `main` for an implementation task.

Use a **single version branch per development cycle** (décision utilisateur 2026-08-08 — éviter la multiplication de branches par tâche et les merges GitHub coûteux):

    main
      ↓
    feature/v<version>   (ex. feature/v18.1 — une seule branche pour tous les chantiers de la version)

All tasks of the same version commit on the same `feature/v<version>` branch; one merge to `main` at the end of the version. Kanban-level task isolation and per-task review remain unchanged — only branch management differs.

If the version branch does not exist yet, create it once (`git checkout -b feature/v18.1`); otherwise `git switch feature/v18.1` and pull latest before starting.

Before modifying code:

- inspect Git status;
- preserve unrelated user changes;
- understand the current branch;
- avoid destructive commands.

Never:
- force-push;
- reset unrelated work;
- delete user changes;
- rewrite history;

unless explicitly authorized.

Every implementation should produce a reviewable diff.

---

## 21. Kanban Rules

The Hermes Kanban board is the source of truth for multi-agent development work.

Tasks should represent concrete, verifiable units of work.

Prefer:

    Analyze RAG context gate
    Implement context gate change
    Add regression tests
    Review context gate implementation

over:

    Fix all RAG problems

Use explicit dependencies between tasks.

A downstream task must not be marked READY when its required predecessor is incomplete.

Blocked tasks must state the reason for blocking.

Completed tasks must contain enough information for another agent to understand what was actually done.

---

## 22. Human Escalation

Agents must stop and request human clarification when:

- requirements are materially ambiguous;
- two architectural approaches have significant consequences;
- a destructive operation is required;
- credentials or secrets are involved;
- a change could invalidate major parts of the architecture;
- existing behavior conflicts with the requested behavior;
- the task requires an assumption that cannot be verified from the repository.

Do not guess when the cost of being wrong is high.

---

## 23. Communication Between Agents

Agent communication must be concise and evidence-based.

When handing off work, provide:

    TASK
    CONTEXT
    CURRENT STATE
    REQUIRED ACTION
    CONSTRAINTS
    ACCEPTANCE CRITERIA
    TEST REQUIREMENTS
    FILES / COMPONENTS
    BLOCKERS

When returning work, provide:

    STATUS
    CHANGES
    FILES MODIFIED
    TESTS RUN
    TEST RESULTS
    RISKS
    REMAINING ISSUES
    RECOMMENDED NEXT ACTION

Do not communicate only:

    "Done."

or:

    "It should work."

---

## 24. Definition of Done

A task is DONE only when all applicable conditions are satisfied:

[ ] Requirement understood

[ ] Scope defined

[ ] Architecture reviewed when required

[ ] Implementation completed

[ ] Tests added or updated where appropriate

[ ] Relevant tests executed

[ ] No unresolved test failures

[ ] Git diff inspected

[ ] Reviewer returned PASS

[ ] No critical or high-severity unresolved findings

[ ] No unrelated modifications

[ ] Documentation updated when necessary

[ ] Performance impact considered when relevant

---

## 25. What Agents Must Never Do

Never:

- invent repository structure;
- invent APIs that were not verified;
- claim tests passed without running them;
- claim a bug is fixed without reproducing or validating it when reproduction is possible;
- silently modify unrelated code;
- introduce duplicate architecture;
- remove functionality without authorization;
- bypass the Reviewer;
- allow the Lead to implement production code;
- allow the Reviewer to implement corrections;
- allow the Tester to modify production code;
- expose secrets;
- commit credentials;
- ignore existing architectural constraints.

---

## 26. Core Engineering Philosophy

NURU development follows these principles:

    Correctness over speed.
    Evidence over assumptions.
    Small changes over broad rewrites.
    Tests over claims.
    Architecture over convenience.
    Explicit dependencies over hidden coupling.
    Reproducibility over speculation.
    Observability over silent failure.
    Simplicity over unnecessary abstraction.

The objective is not merely to make NURU work.

The objective is to make NURU:

- reliable;
- testable;
- maintainable;
- observable;
- performant;
- architecturally coherent;
- resistant to regressions.

---
## TEAM GOVERNANCE

1. Kanban ownership
Only nuru-lead creates, assigns, prioritizes, chains and closes production tasks.
Other agents report discovered work to nuru-lead.

2. Completion authority
Coder reports IMPLEMENTED.
Tester reports PASS/FAIL/BLOCKED.
Reviewer reports PASS/FAIL.
Only nuru-lead closes the Kanban task.

3. Correction cycles
nuru-lead maintains the correction-cycle count.
Default maximum: two unsuccessful correction cycles.
After two failures, stop and escalate.

4. Cost-aware execution
Use the minimum sufficient context, smallest valid workflow and targeted
investigation/testing. Expand scope only when evidence requires it.
Never sacrifice reliability for token savings.

5. Source-of-truth hierarchy

SOUL.md  → agent identity and behavior
AGENTS.md → team/project operating rules
V18.md    → architectural decisions
Repository → actual implementation state
Runtime/tests → actual observed behavior
---
## 27. Final Rule

When uncertain:

    READ FIRST.
    UNDERSTAND.
    PLAN.
    IMPLEMENT ONLY WITHIN SCOPE.
    TEST.
    REVIEW.
    VERIFY.
    THEN DECLARE DONE.
