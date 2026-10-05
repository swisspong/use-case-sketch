---
name: use-case-sketch-v3
description: Build a Clean Architecture use-case skeleton through conversation and incremental code edits, starting from selected ports rather than implementation scans. Use when the user wants Interactor, domain and outcome contracts to evolve in real files without concrete adapters or framework integration.
---

# Use-case sketch

**Code is the conversation surface.** Discover behavior and design together for one use case; no prerequisite discovery/design documents. Support greenfield and refactoring. Write real application/domain files incrementally, with the Interactor as the main review surface.

## 1. Start from selected contracts

Establish the use case, selected port paths and target sketch directory; ask if unclear. For greenfield without ports, start from the user's requirements. Reuse confirmed decisions and already-loaded project instructions. Follow project task-tracking rules without inventing a new workflow.

**Boundary check before placement:** for every new use case, establish the following from confirmed decisions, user answers and the approved read scope below. Reuse settled answers; ask only about gaps, following the 1–3 question loop rather than starting a separate DDD interview:

- What business responsibility does this operation serve?
- Do its terms, rules and model mean the same thing as in the proposed owner's existing use cases? Matching names/fields alone are insufficient.
- Who owns the rules, authoritative data and state changes? Does this use case change that state itself or request an operation through another owner's contract?

A **Bounded Context** bounds a consistent domain language/model; a **module** groups code by responsibility. One context may contain several modules. A folder, use case, database or microservice does not automatically define a context. Consider existing owners before adding boundaries; do not invent a new context for every use case.

Before creating files, show `proposed context → application module → use case`, the target path, a one-sentence rationale and unresolved assumptions. Obtain confirmation unless already agreed. If evidence is insufficient, label the boundary **provisional** and ask the user to approve that working placement; approval to proceed is not proof of the boundary. Keep this lightweight: no mandatory context map, glossary, events or extra design documents.

**Default read scope:** selected input/output/dependency interfaces, their directly required DTOs, outcomes/errors and type declarations. Read relevant sections only; do not recursively follow implementation imports. If paths are unknown, ask or offer a filename-only search within a named module, not a repository-wide content scan.

Read legacy Interactors, Entity/VO/policy method bodies, concrete adapters, routes, wiring or tests **only with explicit permission**. Explain which file/section is needed and why before expanding scope. Reading and editing the new sketch's own relevant files is allowed; that does not authorize scanning existing implementations. Keep the sketch separate from live integration unless requested.

Contracts are promises, not proof of current behavior. If preserving behavior requires implementation evidence, ask for narrow read permission or label parity unverified; never infer it from signatures. Create the smallest supported draft and ask the first blocking question.

## 2. Sketch → ask → test → edit

- Show the relevant Interactor fragment. Include the explicit input/output path in the first and final call trees; label deferred adapters, especially the Presenter. Label proposed behavior clearly; observed code is not automatically the desired behavior.
- Ask **1–3 numbered questions** whose prerequisites are settled, then wait. Focus on decisions changing contracts or flow; look up facts within the approved read scope. Offer recommendations with reasons, not assumed approval.
- Apply answers to contracts first; for each confirmed behavior, follow the test-first loop in section 5 before adding its logic. Keep affected types, guarantees, callers and tests consistent within the approved scope. For existing shared-contract changes, flag downstream impact and request permission to inspect/update consumers before claiming compatibility. Show only changed paths, a short diff/snippet, the test result and the next question. Show the full call tree only when useful or requested; avoid repeated prose specs.
- Mark unresolved behavior locally with `UNDECIDED: <question>`. Unimplemented executable paths must fail explicitly, such as `NotImplementedError`, rather than silently pass or return fake success. Interface method stubs are contracts, not missing behavior.

Repeat until important branches are represented. Check them with short acceptance scenarios rather than restarting a separate discovery interview.

## 3. Keep the Clean Architecture shape

Use conventions visible in approved context; otherwise start with this shape and add only necessary files:

```text
<source-root>/
├── domain/<domain-owner>/
│   └── entities / value_objects / policies
└── application/modules/<module>/
    ├── ports/
    └── use_cases/<commands-or-queries>/<use-case>/
        ├── request.py
        ├── response.py
        ├── input_boundary.py
        ├── interactor.py
        └── output_boundary.py  # Presenter port; required in this sketch style
```

Adapt extensions to the project language. Types may share files, but both Input Boundary and Output Boundary contracts are required. This skill chooses explicit Presenter ports as its convention; it is not the only valid Clean Architecture style.

- **Dependency rule:** application depends on domain and inward-owned interfaces, never concrete infrastructure. Inject dependencies; Interactors do not construct production adapters.
- **Input Boundary / Interactor:** the boundary declares the use-case entry contract; the Interactor implements it and orchestrates actor/resource authorization, domain operations, port calls and outcomes. Trusted identity comes from a trusted caller, not user-supplied permissions.
- **Domain:** Entities protect state/transitions; Value Objects protect meaningful values across construction paths; policies hold rules not belonging to one object. Introduce an Aggregate only when confirmed invariants justify a consistency boundary controlled through its root. Add domain constructs for behavior, not to complete a DDD checklist; read-only queries may use read models.
- **Ports:** describe required capabilities, inputs/results, failure modes and guarantees. Include atomicity, ordering, concurrency, retries and partial effects where behavior requires them. A pre-check is not a uniqueness guarantee; a DB transaction cannot make remote effects atomic. Hide mechanisms behind small interfaces, not one port per table or method.
- **Data:** keep request/result types separate from framework requests, ORM models and provider DTOs. Restrict sensitive data exposure.
- **Output:** inject an application-owned Output Boundary into the Interactor. Define `present(result: UseCaseResult) -> None` (or outcome-specific methods) and make the Input Boundary's `execute` return `None`, or its async equivalent. Deliver success and expected rejection through that port, not a second returned result. For single-result use cases, emit one final outcome per normal execution and end the branch. A concrete Presenter will implement the port later; application code never imports it or receives its ViewModel. Keep display text, localization and transport status mapping outside the Interactor; send semantic codes and safe data.
- **Ownership:** use-case-specific types stay local; module ports belong in that module. When reuse crosses modules or new behavior challenges the agreed placement, revisit the boundary check using approved contracts/type declarations, not implementation scans. Recommend retaining ownership, relocating genuinely shared concepts or regrouping modules based on business meaning. Reuse alone does not justify merging contexts/modules or moving types into `shared`; domain ownership need not match the application folder name. Share outcomes/errors only when semantics and data genuinely match; shared data types are not ports.
- **Cross-context contracts:** agree the exposed operation/data, authoritative owner and translation responsibility before sketching the interaction. Each context keeps its own model; exchange explicit contract data and translate where meanings differ rather than directly reusing another context's Entity/VO. Any intentionally shared domain model requires explicit agreement on semantics and joint change ownership. A port does not imply HTTP, events or a separate service; production adapters remain deferred.
- **Relocation:** show a short before/after tree, rationale and affected consumers; obtain approval before moving or renaming existing files. Request narrow permission for consumer/import inspection beyond the current scope. Preserve behavior, update affected imports/tests together and run scoped regression checks before/after the move where available. Treat pure relocation as a separate refactor, not a manufactured red/green cycle; report unverified compatibility if checks cannot run.

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

Before the first cycle, read [tdd](../tdd/SKILL.md) and its testing/mocking references. Confirm the test seams with the user once, revisiting only when they change. Default proposal: invoke the Input Boundary through the real Interactor, use real domain objects, and observe the emitted outcome through a recording/mock Output Boundary.

- Draft interfaces, DTOs and nonfunctional skeletons before tests if needed; no test is required merely to create a file or type. Expected behavior comes from confirmed examples, not reverse-engineering assertions from the implementation.
- For each agreed behavior: write **one test → run and observe red → add minimal logic → run green**, then run relevant scoped regression tests. Red must reflect the missing behavior, not a broken environment or unrelated import. Do not batch all tests first or fill the whole Interactor before testing.
- Use port `Mock`/`AsyncMock` with `spec`/`autospec` and explicit typed results or declared exceptions; handwritten fakes are optional. Keep domain logic real. In addition to final outcomes, verify business/security-significant port arguments using independent expected values or argument-sensitive stubs. A canned mock result must not hide a wrong identity, credential or resource. Follow [port-test guidance](../tdd/tests.md#port-contract-assertions); avoid asserting every call or incidental order.
- Exercise consequential failures across dependencies, not only the last port: verify propagation or agreed recovery, forbidden downstream effects, and no false success. Add one case per distinct obligation; avoid a Cartesian product of equivalent failures.
- For logic already present, add behavior tests without deleting code to manufacture red. Label these as tests of existing logic, then use test-first for subsequent changes. If execution is unavailable, report unverified tests and the blocker; do not claim an observed red/green cycle or silently switch to implementation-first.

## 6. Verify and stop

Allowed: contracts, Interactor logic, domain implementation, and scoped unit tests using mocks/fakes. **Do not implement production repositories, provider clients, concrete controllers/presenters, routes, central handlers, DI wiring or migrations in this skill.** Mark their required responsibilities without generating empty adapter classes.

Run checks/tests only within the sketch or explicitly approved scope; ask before investigating legacy tests. Check that tests would catch wrong business-critical port arguments as well as wrong final outcomes; mutation probes are optional, not a required new stage. Verify invalid domain objects cannot be created, normal branches emit one final outcome, and dependency failures follow their declared contracts. Report what passed, failed or was not run. Mock/fake tests verify application/domain behavior, not real DB/provider guarantees; briefly identify remaining adapter tests.

Before final review, verify context/module/type ownership matches the agreed placement and provisional assumptions remain visible, the Interactor implements the Input Boundary, depends on and calls the Output Boundary on every expected terminal branch, and shows the deferred Presenter in the call tree. Ask for final review when important paths, invariants, port guarantees and error destinations are explicit, with no essential behavior hidden in placeholders. Report paths, verification and unresolved points concisely. Call it an **approved sketch**, not production-ready code, only after the user confirms; stop before adapter implementation. Leave incomplete sketches clearly identified when the user pauses.
