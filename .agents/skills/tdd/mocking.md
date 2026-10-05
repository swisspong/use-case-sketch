# When to Mock

Use test doubles at **agreed system/output ports**:

- External APIs, databases, file systems, time/randomness
- Output Boundary: record emitted outcomes while the concrete Presenter is deferred

A port owned by your application may represent a system dependency you do not instantiate in a unit test. Mocking that interface is appropriate; mocking internal business logic is not. Use real Interactors, Entities, Value Objects and policies.

For sketches, mocks can stand in for deferred adapters without handwritten fake classes. Prefer `spec`/`autospec` and explicit return values/exceptions; use `AsyncMock` for async methods. Validate meaningful arguments as described in [port-contract assertions](tests.md#port-contract-assertions). Real DB/provider guarantees still need later adapter/integration tests.

## Designing for Mockability

At system boundaries, design interfaces that are easy to mock:

**1. Use dependency injection**

Pass external dependencies in rather than creating them internally:

```typescript
// Easy to mock
function processPayment(order, paymentClient) {
  return paymentClient.charge(order.total);
}

// Hard to mock
function processPayment(order) {
  const client = new StripeClient(process.env.STRIPE_KEY);
  return client.charge(order.total);
}
```

**2. Prefer SDK-style interfaces over generic fetchers**

Create specific functions for each external operation instead of one generic function with conditional logic:

```typescript
// GOOD: Each function is independently mockable
const api = {
  getUser: (id) => fetch(`/users/${id}`),
  getOrders: (userId) => fetch(`/users/${userId}/orders`),
  createOrder: (data) => fetch('/orders', { method: 'POST', body: data }),
};

// BAD: Mocking requires conditional logic inside the mock
const api = {
  fetch: (endpoint, options) => fetch(endpoint, options),
};
```

The SDK approach means:
- Each mock returns one specific shape
- No conditional logic in test setup
- Easier to see which endpoints a test exercises
- Type safety per endpoint
