---
name: use-case-implement
description: Connect an existing Clean Architecture use-case sketch to production adapters and entry points. Use when continuing a sketch with repositories or provider clients, implementing its Presenter/controller and DI, or verifying its real persistence and integration guarantees.
---

# Use-case implement

**Make the agreed use case work through real boundaries.** Continue executable Interactor/domain code rather than rewriting it. Implement one selected vertical slice through concrete adapters, presentation and wiring, with tests that demonstrate the promised effects. Support adapter-only work when explicitly requested; label that scope instead of claiming end-to-end completion.

The handoff is existing code, contracts, tests and confirmed decisions. No prerequisite design document, new architecture layer or mandatory handoff template is required. Follow project instructions and task tracking.

## 1. Establish the slice and inspect its promises

Confirm the selected use case, target integration path and read/edit scope; reuse decisions already approved. If unclear, ask **1–3 numbered questions**, recommend a scope and wait. Start from the current files, not a remembered snapshot.

Within that scope, read the selected Input/Output Boundaries, dependency ports and required types, Interactor, relevant domain behavior and owning tests. Identify unresolved behavior, deferred technical guarantees and compatibility obligations. Existing code is evidence of current behavior, not proof that the user approved it or that production integration works.

Unlike sketch work, implementation requires concrete evidence. Identify the relevant existing adapter, schema/migration, entry-point, error-handler, configuration and composition-root files; confirm this bounded inspection scope once, then work within it. Ask before expanding into unrelated implementations or consumers. Use targeted filename searches if paths are unknown, not a repository-wide implementation scan. Read applicable local context/ADRs and discover test commands from project configuration.

Distinguish:
- **Executable inner behavior:** preserve it and its unit tests.
- **Deferred technical enforcement:** implement it behind the agreed ports.
- **Missing or undecided business behavior:** resolve the affected branch under step 2 before connecting it; never fill that gap inside an adapter.

Show a short runtime call tree with real names, implemented/deferred parts, and the proposed files to change:

```text
Entry point / Controller
└─ Input Boundary → real Interactor → real Entity / Policy
   ├─ Dependency ports → concrete adapters → DB / provider
   └─ Output Boundary → concrete Presenter → transport output
Unrecovered system exceptions → outer error handler
Composition root supplies concrete dependencies and their lifetimes
```

**Ready when:** the slice and inspection/edit scope are agreed, existing versus missing behavior is distinguished, and blocking questions are explicit. Run available scoped baseline tests before changing code; report environmental blockers separately from test failures.

## 2. Resolve gaps without restarting discovery

Reuse settled behavior. Ask only decisions that affect this slice: storage/provider choices, transport mappings, consistency, failure semantics or compatibility. Look up technical facts in approved code and authoritative documentation for the actual library/provider version before asking the user to supply them. Do not impose a new framework, Unit of Work, event bus or outbox by default.

Before adding/changing behavior, recheck context/domain ownership. If it still fits, state that briefly. If evidence challenges it, read the ownership/model-evolution rules in [use-case-sketch](../use-case-sketch/SKILL.md) sections 1 and 3. Its adapter-deferral restriction applies to sketch work, not this implementation skill. Show the smallest correction, before/after responsibilities and affected contracts/consumers; obtain approval before changing behavior, contracts or existing ownership. Refine only the affected branch, not the entire sketch interview.

If a port's guarantee cannot be implemented with the chosen technology, explain the mismatch and alternatives. Keep the guarantee blocked until the user approves a feasible mechanism or a revised contract; never silently weaken atomicity, authorization or failure semantics to make an adapter fit. Update approved callers and tests together. Request narrow consumer inspection permission before claiming compatibility.

Preserve the agreed `application/use_cases/<use-case>/` placement and domain ownership. Use the repository's existing infrastructure/presentation conventions for adapters; do not introduce capability-module folders or relocate the sketch merely to implement it. File moves, merges and deletions require a before/after mapping, impact explanation and approval; keep structural refactors separate from behavior changes.

**Ready when:** each next increment has confirmed behavior, a feasible contract and no unresolved decision essential to that increment. Independent increments may proceed while a named blocker remains elsewhere.

## 3. Choose enforcement and evidence together

For each relevant port obligation, identify **guarantee → concrete enforcement → observable test evidence** in a short review message. Cover only obligations this slice actually has, including failure/no-effect guarantees, not a generic checklist of hypothetical features.

Before implementing persistence, transaction scopes, concurrency, migrations, remote effects or security-provider adapters, read the relevant section of [GUARANTEES.md](GUARANTEES.md). Choose a test environment capable of exercising the production semantics being claimed. A mock, fake repository or different database engine does not prove real locking, uniqueness, rollback or provider behavior.

Before the first test cycle, read [tdd](../tdd/SKILL.md), [tests](../tdd/tests.md) and [mocking](../tdd/mocking.md). Confirm test seams, placement and safe environment once, reusing existing approvals. Default seams:
- Existing Input Boundary tests with real Interactor/domain for business regression.
- Dependency port implemented by the real adapter against an isolated supported DB, or the agreed provider test environment, for technical guarantees.
- Actual configured entry point through real controller/Presenter and production composition for integrated request/outcome/error mapping. Keep unrelated external systems doubled if necessary, and label them.

For an adapter under test, exercise its public port rather than mocking that port or asserting private implementation details. Observe persisted effects through agreed read contracts or an explicitly agreed persistence test seam; do not add production APIs solely for test inspection. Derive expected identities/state/effects independently from the contract.

Follow the repository's test layout. If none exists, propose behavior-named suites under `tests/integration/contexts/<context>/` for adapters and integrated paths, with existing application/domain suites remaining unit tests. Omit context folders where the approved layout does. Extend owning suites; shared contract cases are useful only when consumers share the same obligations. No empty test trees or one-file-per-class requirement.

**Ready when:** the next guarantee has an agreed enforcement mechanism, test seam and safe runnable environment, or an explicit blocker. If execution is unavailable, report it; do not claim a red/green cycle or switch silently to implementation-first.

## 4. Implement one tested increment at a time

For each confirmed missing behavior: **one test → observe relevant red → minimal implementation → green**, then scoped regression. A broken environment is not the required red. For behavior already implemented, add missing regression coverage without deleting code to manufacture failure. Do not write all adapters before testing or duplicate the sketch's business rules.

Keep responsibilities at their boundaries:

| Boundary | Implementation responsibility |
|---|---|
| Interactor / domain | Preserve visible orchestration, Entity-owned state transitions, shared invariants and declared outcomes. Application depends only inward; inject concrete dependencies from outside. |
| Persistence adapter | Load facts, rehydrate without resetting persisted state, persist the exact approved transition, enforce constraints/consistency, and translate known storage failures. ORM/session types stay outside inner contracts. |
| Provider adapter | Translate explicit contract data through the supported API; honor timeout, retry and partial-effect semantics. Respect another context's authoritative rules instead of importing its internals or writing its private storage. |
| Controller / entry point | Parse transport shape, obtain trusted caller identity from the trusted authentication path, invoke the Input Boundary and deliver presentation output. Client-supplied roles/actor claims are not trusted identity. Business eligibility and resource authorization remain in their agreed inner owner. |
| Presenter | Implement the Output Boundary; map every declared expected outcome to safe transport/view data. Keep formatting, localization and status mapping here. Do not expose secrets or raw provider exceptions. |
| Outer error handler | Handle unrecovered system errors using the project's safe response/logging policy. Never turn them into business rejection or success merely to avoid an error response. |
| Composition root | Bind real adapters and configure resource/Presenter lifetimes, cleanup and settings. Interactors never construct them. Keep per-execution output/state isolated across concurrent requests. |

Preserve `execute(...) -> None` (or async equivalent): outcomes go through the Output Boundary, not a second Interactor return value. The controller may obtain the Presenter-produced response through an outer-layer interface. A Presenter failure after commit does not undo persisted or remote effects; respect the contract's outcome timing and uncertainty.

Translate only recognized constraint/provider cases into the declared typed results or named dependency exceptions. Unexpected failures propagate to the outer handler; use safe diagnostics rather than raw error text in responses. Adapters do not call Presenters or decide locally owned business outcomes on behalf of the Interactor.

After each increment, show changed paths, a small relevant diff/snippet, observed tests and any new decision. Continue within the agreed scope without requesting approval for every mechanical edit; pause for unresolved behavior, scope expansion or consequential contract/ownership changes.

**Increment complete when:** its observed tests pass, the promised effect/rejection is demonstrated, and scoped regressions pass or have clearly identified blockers.

## 5. Connect and verify the selected path

Replace deferred dependencies in the selected composition with real implementations and exercise the actual configured entry point. Check success, consequential expected rejection and system-failure paths, including safe mapping, forbidden effects after denial and no false success after uncertain failure. Adapter-only scope may stop at its port but must leave entry-point wiring explicitly deferred.

Run relevant application/domain regression, adapter integration, entry-point tests and project checks available within scope. Include applicable concurrency/failure evidence from step 3; green unit counts alone are insufficient. Verify DI/resource lifetimes and cleanup on success and failure, and isolation between concurrent request Presenters. Ensure the integration path does not accidentally still use a fake adapter.

For schema/configuration changes, test the approved migration and application configuration in the isolated environment, including existing-data compatibility where relevant. Keep credentials out of files/logs and use project secret/config conventions. Writing migration/configuration code does not authorize applying it to shared or production environments, deploying, provisioning paid resources or calling effectful live APIs; obtain separate explicit permission for those operations.

**Slice complete when:** each in-scope guarantee has passing evidence at the appropriate boundary, all declared transport outcomes/errors are mapped, approved consumers remain compatible, and no essential path relies on placeholders or test doubles mislabeled as real integration. If an essential guarantee remains unverified, report the slice as incomplete or implemented-but-unverified, not ready for production.

## 6. Report the handoff

Finish with changed paths, the final implemented/deferred call tree, tests actually run and their results, and any compatibility or operational risks. Separate:
- Implemented behavior and guarantees demonstrated in the named environment.
- Doubled dependencies, skipped/blocked tests and guarantees still unverified.
- Migrations/configuration prepared versus actually applied, and deployment/cutover work not performed.

Keep this concise; use the project's tracker for durable follow-up work rather than creating new planning documents. Completion of this skill is not deployment approval or a blanket claim of production readiness.
