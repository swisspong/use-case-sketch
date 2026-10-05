---
name: use-case-sketch-v1
description: Build a Clean Architecture use-case skeleton through conversation and incremental code edits, starting from selected ports rather than implementation scans. Use when the user wants Interactor, domain and outcome contracts to evolve in real files without concrete adapters or framework integration.
---

# Use-case sketch

**Code is the conversation surface.** Discover behavior and design together for one use case; no prerequisite discovery/design documents. Support greenfield and refactoring. Write real application/domain files incrementally, with the Interactor as the main review surface.

## 1. Start from selected contracts

Establish the use case, selected port paths and target sketch directory; ask if unclear. For greenfield without ports, start from the user's requirements. Reuse confirmed decisions and already-loaded project instructions. Follow project task-tracking rules without inventing a new workflow.

**Default read scope:** selected input/output/dependency interfaces, their directly required DTOs, outcomes/errors and type declarations. Read relevant sections only; do not recursively follow implementation imports. If paths are unknown, ask or offer a filename-only search within a named module, not a repository-wide content scan.

Read legacy Interactors, Entity/VO/policy method bodies, concrete adapters, routes, wiring or tests **only with explicit permission**. Explain which file/section is needed and why before expanding scope. Reading and editing the new sketch's own relevant files is allowed; that does not authorize scanning existing implementations. Keep the sketch separate from live integration unless requested.

Contracts are promises, not proof of current behavior. If preserving behavior requires implementation evidence, ask for narrow read permission or label parity unverified; never infer it from signatures. Create the smallest supported draft and ask the first blocking question.

## 2. Sketch → ask → edit

- Show the relevant Interactor fragment. Include the explicit input/output path in the first and final call trees; label deferred adapters, especially the Presenter. Label proposed behavior clearly; observed code is not automatically the desired behavior.
- Ask **1–3 numbered questions** whose prerequisites are settled, then wait. Focus on decisions changing contracts or flow; look up facts within the approved read scope. Offer recommendations with reasons, not assumed approval.
- Apply answers to the sketch's files and update affected types, guarantees, callers and tests within that scope. For existing shared-contract changes, flag downstream impact and request permission to inspect/update consumers before claiming compatibility. Show only changed paths, a short diff/snippet, and the next question in the user's language. Show the full call tree only when useful or requested; avoid repeated prose specs.
- Mark unresolved behavior locally with `UNDECIDED: <question>`. Unimplemented executable paths must fail explicitly, such as `NotImplementedError`, rather than silently pass or return fake success. Interface method stubs are contracts, not missing behavior.

Repeat until important branches are represented. Check them with short acceptance scenarios rather than restarting a separate discovery interview.

## 3. Keep the Clean Architecture shape

Use conventions visible in approved context; otherwise start with this shape and add only necessary files:

```text
<source-root>/
├── domain/<module>/
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
- **Domain:** Entities protect state/transitions; Value Objects protect meaningful values across construction paths; policies hold rules not belonging to one object. Add these only when justified; read-only queries may use read models.
- **Ports:** describe required capabilities, inputs/results, failure modes and guarantees. Include atomicity, ordering, concurrency, retries and partial effects where behavior requires them. A pre-check is not a uniqueness guarantee; a DB transaction cannot make remote effects atomic. Hide mechanisms behind small interfaces, not one port per table or method.
- **Data:** keep request/result types separate from framework requests, ORM models and provider DTOs. Restrict sensitive data exposure.
- **Output:** inject an application-owned Output Boundary into the Interactor. Define `present(result: UseCaseResult) -> None` (or outcome-specific methods) and make the Input Boundary's `execute` return `None`, or its async equivalent. Deliver success and expected rejection through that port, not a second returned result. For single-result use cases, emit one final outcome per normal execution and end the branch. A concrete Presenter will implement the port later; application code never imports it or receives its ViewModel. Keep display text, localization and transport status mapping outside the Interactor; send semantic codes and safe data.
- **Ownership:** use-case-specific types stay local; module ports belong in that module. Share outcomes/errors only when semantics and data genuinely match across consumers; shared data types are not ports.

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
- **System/dependency failures:** declare exceptions in port contracts and propagate to the outer handler when no use-case recovery is required. A predictable outage is still a system failure; do not add every technical failure to every result union. Preserve programming errors as exceptions, not business outcomes.
- **Recovery:** when confirmed behavior requires fallback/recovery, make that path explicit in the contract and Interactor. Catch only specific failures needing recovery, translation or cleanup; this convention reduces business `try/except`, not all exception handling.
- **Adapter translation:** document how recognized DB/provider failures will map to typed business results or dependency exceptions. Adapters may need `try/except`; their implementation remains deferred. They never call Presenters or expose raw provider/exception messages as presentation text.
- **Complete contracts:** make variants and discriminators explicit with types/enums/literals. Handle every declared branch; do not silently map unknown variants to a known business outcome. Avoid signalling the same expected condition via both return and raise in one contract.
- **Existing contracts:** do not silently break exception-based ports or factories. Propose migration and request approval to inspect affected consumers; a narrow compatibility translation may remain until migration is approved. Label the exception to this convention explicitly.

Identify `event → translation owner → Interactor action → Presenter or central handler` in code/docstrings, with a short table only when needed.

## 5. Verify and stop

Allowed: contracts, Interactor logic, domain implementation, and relevant tests/fakes. **Do not implement production repositories, provider clients, concrete controllers/presenters, routes, central handlers, DI wiring or migrations in this skill.** Mark their required responsibilities without generating empty adapter classes.

Run available syntax/type checks and tests scoped to the sketch or explicitly approved files; do not expand into legacy tests to diagnose failures without permission. A recording Output Boundary fake is allowed: assert typed business rejections reach presentation without raising, invalid domain objects are not created, and normal branches emit one outcome with correct data; verify unhandled system failures propagate rather than becoming business outcomes or false success. Report what passed, failed or was not run. Fake-based tests check use-case behavior, not real DB/provider guarantees; identify those remaining adapter tests briefly.

Before final review, verify the Interactor implements the Input Boundary, depends on and calls the Output Boundary on every expected terminal branch, and shows the deferred Presenter in the call tree. Ask for final review when important paths, invariants, port guarantees and error destinations are explicit, with no essential behavior hidden in placeholders. Report paths, verification and unresolved points concisely. Call it an **approved sketch**, not production-ready code, only after the user confirms; stop before adapter implementation. Leave incomplete sketches clearly identified when the user pauses.
