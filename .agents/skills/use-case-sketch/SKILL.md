---
name: use-case-sketch
description: Build a Clean Architecture use-case skeleton through conversation and incremental code edits, starting from selected ports rather than implementation scans. Use when the user wants Interactor, domain and outcome contracts to evolve in real files without concrete adapters or framework integration.
---

# Use-case sketch

**Code is the conversation surface.** Discover behavior and design together for one use case; no prerequisite discovery/design documents. Support greenfield and refactoring. Write real application/domain files incrementally, with the Interactor as the main review surface.

## 1. Start from selected contracts

Establish the use case, selected port paths and target sketch directory; ask if unclear. For greenfield without ports, start from the user's requirements. Reuse confirmed decisions and already-loaded project instructions. Follow project task-tracking rules without inventing a new workflow.

**Ownership check for every addition or change:** before adding or modifying a use case, reassess its context and domain responsibility from confirmed decisions, user answers and the approved read scope below. Recheck as behavior evolves during the sketch. Existing placement is a working decision, not proof that ownership remains correct. Reuse settled answers that still fit; ask only about gaps in the existing 1–3 question loop, not a separate DDD interview:

- What business responsibility does this operation serve, and which context/domain owner should hold it?
- Do its terms, rules and model mean the same thing as in that owner's existing use cases? Matching names/fields alone are insufficient.
- Who already owns the rules, authoritative data and state changes? Should this use case invoke/evolve that owner or request an operation through another owner's contract?
- Does the confirmed change or evidence of misplaced behavior challenge the current name, responsibility or model boundary?

If ownership still fits, state the reason briefly and proceed without reopening settled questions. If it does not, propose the smallest justified correction: relocate the use case/rule, evolve the existing model under section 3, or use the proper owner's contract. Show before/after responsibilities and locations, the requirement/evidence, and affected use cases/contracts/consumers. Obtain approval before changing existing ownership or consumers, and follow Relocation for file changes. Request narrow read permission when evidence lies outside scope; mark uncertain placement provisional rather than claiming it is wrong. Do not refactor for hypothetical future features.

For confirmed business defaults, creation rules and state transitions, clarify whether the rule applies only to this use case or across all creation/update channels. Distinguish creation invariants, transition rules and lifetime invariants. Reuse settled answers in the existing 1–3 question loop.

A **Bounded Context** bounds a consistent domain language/model. Domain ownership identifies where its rules and state belong; it does not require an intermediate application grouping. A folder, use case, database or microservice does not automatically define a context. Consider existing owners before adding boundaries; a new use case does not automatically require a new context or domain model.

Before creating files, show `proposed context → use case`, its domain rule owner(s), the target path using section 3, a one-sentence rationale and unresolved assumptions. This describes responsibility, not a required domain folder per use case. Obtain confirmation unless already agreed. If evidence is insufficient, label the boundary **provisional** and ask the user to approve that working placement; approval to proceed is not proof of the boundary. Keep this lightweight: no mandatory context map, glossary, events or extra design documents.

**Default read scope:** selected input/output/dependency interfaces, their directly required DTOs, outcomes/errors and type declarations. Read relevant sections only; do not recursively follow implementation imports. If paths are unknown, ask or offer a filename-only search within a named context/use-case directory, not a repository-wide content scan.

Read legacy Interactors, Entity/VO/policy method bodies, concrete adapters, routes, wiring or tests **only with explicit permission**. Explain which file/section is needed and why before expanding scope. Reading and editing the new sketch's own relevant files is allowed; that does not authorize scanning existing implementations. Keep the sketch separate from live integration unless requested.

Contracts are promises, not proof of current behavior. If preserving behavior requires implementation evidence, ask for narrow read permission or label parity unverified; never infer it from signatures. Create the smallest supported draft and ask the first blocking question.

## 2. Sketch → ask → test → edit

- Show the relevant Interactor fragment. Include the explicit input/output path in the first and final call trees; label deferred adapters, especially the Presenter. Label proposed behavior clearly; observed code is not automatically the desired behavior.
- Ask **1–3 numbered questions** whose prerequisites are settled, then wait. Focus on decisions changing contracts or flow; look up facts within the approved read scope. Offer recommendations with reasons, not assumed approval.
- Apply answers to contracts first, using section 1's ownership check as confirmed behavior evolves; for each confirmed behavior, follow the test-first loop in section 5 before adding its logic. Keep affected types, guarantees, callers and tests consistent within the approved scope. For existing shared-contract or model-ownership changes, show affected use cases and explain how their current models and write paths will coexist, delegate or be replaced. Request permission to inspect/update consumers before claiming compatibility. Reuse settled decisions in the existing question loop; do not introduce a separate design gate. Show only changed paths, a short diff/snippet, the test result and the next question. Show the full call tree only when useful or requested; avoid repeated prose specs.
- Mark unresolved behavior locally with `UNDECIDED: <question>`. Unimplemented executable paths must fail explicitly, such as `NotImplementedError`, rather than silently pass or return fake success. Interface method stubs are contracts, not missing behavior.

Repeat until important branches are represented. Check them with short acceptance scenarios rather than restarting a separate discovery interview.

## 3. Keep the Clean Architecture shape

**Physical layout:** this sketch convention places use cases directly under `application/use_cases/<use-case>/`, without an intermediate application capability/module group or command/query wrapper. Domain ownership is independent of that flat application layout. This is a navigation convention, not a Clean Architecture requirement.

Confirm the target layout as part of placement. Existing project instructions and explicitly agreed layouts take precedence; propose migration rather than silently reorganizing live code. Approval to use this skill is not permission to move existing files. Follow Relocation for any migration, including imports, consumers and tests.

A context-first example:

```text
<source-root>/contexts/<context>/
├── domain/<domain-owner>/
│   └── entities / value_objects / policies
└── application/
    ├── <capability>_ports.py   # only for genuinely shared contracts
    └── use_cases/<use-case>/
        ├── request.py
        ├── response.py
        ├── input_boundary.py
        ├── interactor.py
        ├── ports.py           # only for use-case-specific dependencies
        ├── errors.py          # only when needed
        └── output_boundary.py # Presenter port; required in this sketch style
```

In a layer-first project, use the same `domain/<domain-owner>/` and `application/use_cases/<use-case>/` paths under the source root without the context-directory prefix. Preserve semantic context ownership even when it is not represented by a folder. These are alternatives, not two trees to scaffold; create only necessary files. A context is not necessarily a separate service. Do not generate empty adapter folders.

Adapt extensions to the project language. Types may share files, but both Input Boundary and Output Boundary contracts are required. This skill chooses explicit Presenter ports as its convention; it is not the only valid Clean Architecture style.

- **Dependency rule:** application depends on domain and inward-owned interfaces, never concrete infrastructure. Inject dependencies; Interactors do not construct production adapters.
- **Input Boundary / Interactor:** the boundary declares the use-case entry contract; the Interactor implements it and orchestrates actor/resource authorization, domain operations, port calls and outcomes. Trusted identity comes from a trusted caller, not user-supplied permissions.

  Make this use case's business workflow visible in the Interactor: obtain facts, invoke Entity/Policy behavior, branch on decisions, request persistence/effects, and map outcomes. Keep reusable invariants inside their domain owners rather than copying their implementation into the Interactor.

  Do not delegate the entire locally owned workflow to a deferred dependency merely to label it atomic. Operations genuinely owned elsewhere remain behind that owner's contract; visibility does not justify importing or duplicating another owner's rules.
- **Domain:** Entities protect state/transitions; Value Objects protect meaningful values across construction paths; policies express domain decisions over facts, especially rules not naturally owned by one object. Introduce an Aggregate only when confirmed invariants justify a consistency boundary controlled through its root. Add domain constructs for behavior, not to complete a DDD checklist; read-only queries may use read models. Separate new-object creation from rehydrating existing state: creation defaults must not reset persisted state during loading. Identify affected entry paths when introducing a shared invariant; request permission before inspecting or updating existing consumers, and do not claim all paths comply without verification.
- **Entity-first:** for behavior that creates or changes the state of a business identity, start with the Entity that owns that state and its invariants. Reuse and evolve an existing Entity before introducing another overlapping write model.

  Treat Entity-first as the agreed default, not a repeated Entity-versus-Policy question. Propose an exception only when confirmed behavior gives a clear reason; explain that reason briefly. Read-only use cases may use projections/DTOs without loading an Entity.

  An Entity owns its creation and transitions and need not be mutable. Value Objects protect meaningful values. Policies hold decisions that do not naturally belong to one Entity; do not extract a Policy merely to shorten Entity methods.

  This convention does not require one Entity per use case, one Entity per table, or one large Entity for the entire context. A table or ID field alone does not justify an Entity; the Aggregate criterion in Domain above still applies.
- **Overlapping write models:** before adding a model that can change business state already represented elsewhere, identify the existing owner of that state, its transitions and invariants within the approved read scope. Request narrow permission when implementation evidence is needed.

  Clarify whether the proposed model is a read projection, a component, a replacement, or a collaborator in a coordinated operation. Multiple representations are allowed; avoid independently implementing the same business rule in competing write models or individual use cases. Prefer retaining the existing model when no confirmed behavior requires change; composition or replacement are alternatives, not automatic consolidation. Replacing a model does not authorize deleting it or migrating consumers without the existing confirmation and Relocation rules.

  When confirmed behavior or ownership evidence challenges an existing model's name or responsibility, reassess its scope rather than preserving the original shape by default or creating a parallel owner. Recommend extending behavior, composing models, splitting responsibilities, or renaming/replacing the model according to confirmed invariants. Show the before/after responsibilities, affected use cases and contracts, and obtain approval before changing existing ownership or consumers.

  Update approved callers, imports and tests together and run scoped regression checks. Reuse the existing question loop and Relocation rules; do not add a separate design stage or refactor for hypothetical future needs.

  When an operation changes multiple models together, identify the authoritative rule owner and the required consistency, atomicity and concurrency contracts. Do not assume shared fields, a database table or one transaction require a single Entity. Preserve separate context models where their meanings differ.
- **Business rule ownership:** implement business decisions, defaults and state transitions as executable application/domain behavior. Use application logic for use-case-specific decisions and domain behavior for domain invariants, including those shared across entry paths. Follow the Entity-first convention for identity-bearing state changes. Keep the model minimal within that choice; fewer classes or lines alone do not justify moving Entity-owned behavior into separate Policies.

  Adapters obtain facts, translate representations and persist/enforce the inner layer's rules; they must not independently choose business defaults or transitions. Port docstrings and database defaults are not substitutes for executable inner-layer policy.

  Keep technical atomicity, uniqueness and concurrency enforcement at the persistence boundary while application/domain code owns decisions. For read-decide-write behavior, protect all mutable facts on which the decision depends through commit, or atomically validate them before accepting the transition. Checking only the target version is insufficient when actor eligibility or other decision facts can change independently.

  Choose the smallest inward-owned contract that provides these guarantees, such as a protected scope or conditional commit; do not mandate a Unit of Work for every use case. When using a scope, specify commit, rollback, exit and success-acknowledgement semantics. Neither a single port call nor a context manager proves atomicity.

  An adapter may translate a constraint failure into a declared result; do not replace atomic enforcement with a racy application pre-check.
- **Ports:** describe required capabilities, inputs/results, failure modes and guarantees. Include atomicity, ordering, concurrency, retries and partial effects where behavior requires them. A pre-check is not a uniqueness guarantee; a DB transaction cannot make remote effects atomic. Hide mechanisms behind small interfaces, not one port per table or method.
- **Data:** keep request/result types separate from framework requests, ORM models and provider DTOs. Restrict sensitive data exposure.
- **Output:** inject an application-owned Output Boundary into the Interactor. Define `present(result: UseCaseResult) -> None` (or outcome-specific methods) and make the Input Boundary's `execute` return `None`, or its async equivalent. Deliver success and expected rejection through that port, not a second returned result. For single-result use cases, emit one final outcome per normal execution and end the branch. A concrete Presenter will implement the port later; application code never imports it or receives its ViewModel. Keep display text, localization and transport status mapping outside the Interactor; send semantic codes and safe data.
- **Ownership:** keep use-case-specific ports and types beside their Interactor. Put genuinely shared application contracts/policies in clearly named files under the owning context's application layer, such as `password_ports.py` or `login_token_policy.py`, only when confirmed consumers share their meaning and obligations. Shared business invariants remain with their domain owner, not in an application helper. Reuse alone does not justify merging contexts, duplicating rules or moving types into generic `shared`/`common` files. Domain ownership need not match the application folder name. Apply section 1's ownership check when sharing or placement changes; shared data types are not ports, and outcomes/errors are shared only when semantics and data genuinely match.
- **Cross-context contracts:** folders alone do not enforce boundaries. When multiple contexts interact, identify the specific public contracts allowed across the boundary, their exposed operations/data, authoritative owner and translation responsibility. Keep internal types/modules private rather than importing another context's Interactors or domain internals. An inward dependency port is not automatically a context's public API. Each context keeps its own model; exchange explicit contract data and translate where meanings differ. Any intentionally shared domain model requires explicit agreement on semantics and joint change ownership. A port does not imply HTTP, events or a separate service; production adapters remain deferred.
- **Relocation:** show a short before/after tree, rationale and affected consumers; obtain approval before moving, renaming, merging or deleting existing files, including archived tests. Request narrow permission for consumer/import inspection beyond the current scope. Preserve behavior, update affected imports/tests together and run scoped regression checks before/after the change where available. For test reorganization, show an old-to-new mapping, preserve distinct behavioral cases and parameterized variants, and update test discovery as well as imports. Passing tests or equal test counts alone do not prove coverage was preserved. Treat pure relocation as a separate refactor, not a manufactured red/green cycle; report unverified compatibility if checks cannot run.

Show this runtime path with real names in the sketch's call tree (arrows are calls, not imports):

```text
Caller / Controller [deferred]
└─ Input Boundary → Interactor
   ├─ Entity / Value Object / Policy [as needed]
   ├─ Dependency ports → production adapters [deferred]
   └─ Output Boundary.present(outcome)
      └─ Presenter [deferred] → ViewModel / transport output [deferred]
System exceptions without recovery → outer error handler [deferred]
```

## 4. Outcomes for business decisions; exceptions for system failures

This is the sketch's convention, not a requirement of Uncle Bob's architecture:

- **Expected business decisions:** return typed results from ports and domain operations, including invalid input, conflicts and denials. Input-facing Entity/Value Object factories return a valid object or typed rejection; never create an invalid object or use exceptions for ordinary input rejection. Keep domain result types in domain, independent of application outcomes. The Interactor branches on these results, maps them to use-case outcomes and sends them through the Output Boundary.
- **System/dependency failures:** name the application-owned exception types for known failures in each relevant port contract, with their meaning and translation owner; “failures propagate” alone is insufficient. Reuse suitable exceptions rather than creating one per method. Adapters translate known technology failures; unexpected errors propagate, not become business rejections. Without use-case recovery, exceptions reach the outer handler. A predictable outage is still a system failure, not another variant in every result union.
- **Recovery:** when confirmed behavior requires fallback/recovery, make that path explicit in the contract and Interactor. Catch only specific failures needing recovery, translation or cleanup; this convention reduces business `try/except`, not all exception handling.
- **Adapter translation:** document how recognized DB/provider failures will map to typed business results or dependency exceptions. Adapters may need `try/except`; their implementation remains deferred. They never call Presenters or expose raw provider/exception messages as presentation text.
- **Complete contracts:** make variants and discriminators explicit with types/enums/literals. Handle every declared branch; do not silently map unknown variants to a known business outcome. Avoid signalling the same expected condition via both return and raise in one contract.
- **Existing contracts:** do not silently break exception-based ports or factories. Propose migration and request approval to inspect affected consumers; a narrow compatibility translation may remain until migration is approved. Label the exception to this convention explicitly.

Identify `event → translation owner → Interactor action → Presenter or central handler` in code/docstrings, with a short table only when needed.

## 5. Contracts first, then test-first behavior

Before the first cycle, read [tdd](../tdd/SKILL.md) and its testing/mocking references. Confirm test seams and [placement](#test-placement) with the user once, revisiting only when they change. Default proposal: invoke the Input Boundary through the real Interactor, use real domain objects, and observe the emitted outcome through a recording/mock Output Boundary.

- Draft interfaces, DTOs and nonfunctional skeletons before tests if needed; no test is required merely to create a file or type. Expected behavior comes from confirmed examples, not reverse-engineering assertions from the implementation.
- For each agreed behavior: write **one test → run and observe red → add minimal logic → run green**, then run relevant scoped regression tests. Red must reflect the missing behavior, not a broken environment or unrelated import. Do not batch all tests first or fill the whole Interactor before testing.
- Use port `Mock`/`AsyncMock` with `spec`/`autospec` and explicit typed results or declared exceptions; handwritten fakes are optional. Keep domain logic real. In addition to final outcomes, verify business/security-significant port arguments using independent expected values or argument-sensitive stubs. A canned mock result must not hide a wrong identity, credential or resource. Follow [port-test guidance](../tdd/tests.md#port-contract-assertions); avoid asserting every call or incidental order.
- Test locally owned business decisions through the real Interactor and Entity/Policy behavior at agreed seams. Mock external facts and I/O acknowledgements, not the entire local business workflow. Verify the resulting state/decision reaches the dependency port and rejections prevent forbidden effects.

  For scoped operations, verify decision execution within the scope and outcome timing against the agreed commit/exit contract. Adapter/integration tests remain responsible for actual persistence and atomic enforcement; unit mocks do not prove those guarantees.
- Exercise consequential failures across dependencies, not only the last port: verify propagation or agreed recovery, forbidden downstream effects, and no false success. Add one case per distinct obligation; avoid a Cartesian product of equivalent failures.
- For logic already present, add behavior tests without deleting code to manufacture red. Label these as tests of existing logic, then use test-first for subsequent changes. If execution is unavailable, report unverified tests and the blocker; do not claim an observed red/green cycle or silently switch to implementation-first.

### Test placement

Follow the repository's agreed test layout. If none exists, propose:

```text
tests/unit/contexts/<context>/test_<use_case>.py
```

Adapt to the language and approved context layout; omit context folders when the project does not use them. Keep domain-rule suites under a domain-owned path, such as `tests/unit/contexts/<context>/domain/`; no application capability-group directory is required. Existing tests move only under the Relocation rule.

- Organize tests by behavior and ownership, not development history. Avoid naming new suites `_tdd` or `_regression`; existing names alone do not authorize a rename.
- Extend the owning use-case suite before creating another file. Split by behavior only when it improves navigation. Ask for narrow read/edit permission if that suite is outside the approved scope.
- Use a shared parameterized suite when multiple use cases genuinely share the same contract obligations. Name its scope explicitly and avoid duplicating equivalent cases in use-case-specific suites; retain distinct behavior for each consumer.
- Sketch tests exercising real application/domain logic with mocked dependency ports belong in unit suites. Add adapter/integration suites when those implementations are in scope; do not scaffold empty folders or require one test file per class.

## 6. Verify and stop

Allowed: contracts, Interactor logic, domain implementation, and scoped unit tests using mocks/fakes. **Do not implement production repositories, provider clients, concrete controllers/presenters, routes, central handlers, DI wiring or migrations in this skill.** Mark their required responsibilities without generating empty adapter classes.

Run checks/tests only within the sketch or explicitly approved scope; ask before investigating legacy tests. Check that tests would catch wrong business-critical port arguments as well as wrong final outcomes; mutation probes are optional, not a required new stage. Verify invalid domain objects cannot be created, normal branches emit one final outcome, and dependency failures follow their declared contracts. Report what passed, failed or was not run. Mock/fake tests verify application/domain behavior, not real DB/provider guarantees; briefly identify remaining adapter tests.

Before completion, identify where each confirmed business default or invariant is executable and tested. A rule left only in a port docstring, mock response or deferred adapter is not implemented business behavior; report it as an explicit gap.

Trace each confirmed, locally owned business branch from the Interactor through its real domain decisions to effects and outcomes. Report orchestration left inside a deferred dependency as an implementation gap, even when its domain rules have separate unit tests. Distinguish that gap from intentionally deferred technical enforcement or another owner's contract.

For overlapping write models, verify that rule ownership and model relationships are explicit, affected consumers within the approved scope follow the chosen design, and scoped regression checks cover their shared obligations. Report uninspected consumers and deferred persistence guarantees as unverified; unit tests do not prove atomic enforcement.

Before final review, verify context/domain/type ownership fits the final confirmed behavior, not merely the original placement; approved ownership corrections and consumer updates are complete or explicitly deferred, and provisional assumptions remain visible. Verify the Interactor implements the Input Boundary, depends on and calls the Output Boundary on every expected terminal branch, and shows the deferred Presenter in the call tree. Ask for final review when important paths, invariants, port guarantees and error destinations are explicit, with no essential behavior hidden in placeholders. Report paths, verification and unresolved points concisely. Call it an **approved sketch**, not production-ready code, only after the user confirms; stop before adapter implementation. Leave incomplete sketches clearly identified when the user pauses.
