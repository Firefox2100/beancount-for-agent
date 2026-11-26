import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, configFromEnv, createClient, describeChange } from "../src/index.js";

/** A fetch stub that records requests and answers from a route table. */
function stub(routes) {
  const calls = [];
  const fakeFetch = async (url, init) => {
    const u = new URL(url);
    calls.push({ method: init.method, path: u.pathname, query: u.search, headers: init.headers, body: init.body });
    const answer = routes[`${init.method} ${u.pathname}`];
    if (!answer) return new Response(JSON.stringify({ detail: "no route" }), { status: 404 });
    return new Response(JSON.stringify(answer.body), { status: answer.status ?? 200 });
  };
  return { calls, fakeFetch };
}

test("config reads the environment and drops a blank token", () => {
  assert.deepEqual(configFromEnv({ BEANCOUNT_MCP_URL: "http://x:9/", BEANCOUNT_MCP_AUTH_TOKEN: " s3 " }), {
    baseUrl: "http://x:9",
    token: "s3",
  });
  assert.deepEqual(configFromEnv({ BEANCOUNT_MCP_AUTH_TOKEN: "" }), { baseUrl: "http://127.0.0.1:8000" });
});

test("requests carry the token and identification", async () => {
  const { calls, fakeFetch } = stub({ "GET /ledgers": { body: [{ id: "main" }] } });
  const client = createClient({ baseUrl: "http://s", token: "t", clientId: "claude-code", fetch: fakeFetch });
  assert.deepEqual(await client.ledgers(), [{ id: "main" }]);
  assert.equal(calls[0].headers.authorization, "Bearer t");
  assert.equal(calls[0].headers["x-actor"], "user");
  assert.equal(calls[0].headers["x-client-id"], "claude-code");
});

test("approve sends a JSON body, which the service requires", async () => {
  const { calls, fakeFetch } = stub({ "POST /ledgers/main/changes/c1/approve": { body: { id: "c1", status: "approved" } } });
  const client = createClient({ baseUrl: "http://s", fetch: fakeFetch });
  await client.approve("main", "c1");
  assert.equal(calls[0].body, '{"note":null}');
  assert.equal(calls[0].headers["content-type"], "application/json");
  assert.equal(calls[0].headers.authorization, undefined);
});

test("errors keep the status and the service's reason", async () => {
  const { fakeFetch } = stub({ "POST /ledgers/main/changes/c1/approve": { status: 409, body: { detail: "changed since" } } });
  const client = createClient({ baseUrl: "http://s", fetch: fakeFetch });
  await assert.rejects(client.approve("main", "c1"), (error) => {
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 409);
    assert.equal(error.detail, "changed since");
    return true;
  });
});

test("allPending gathers every ledger, oldest first", async () => {
  const { fakeFetch } = stub({
    "GET /ledgers": { body: [{ id: "a" }, { id: "b" }] },
    "GET /ledgers/a/changes": { body: [{ id: "2", created_at: "2026-02-01" }] },
    "GET /ledgers/b/changes": { body: [{ id: "1", created_at: "2026-01-01" }] },
  });
  const client = createClient({ baseUrl: "http://s", fetch: fakeFetch });
  assert.deepEqual((await client.allPending()).map((c) => c.id), ["1", "2"]);
});

test("describeChange shows the exact postings", () => {
  const text = describeChange({
    id: "c1",
    ledger_id: "main",
    status: "pending",
    note: "lunch",
    caller: { actor: "agent", client_id: "mcp", session_id: null },
    operation: {
      kind: "add_transaction",
      transaction: {
        date: "2026-03-01",
        payee: null,
        narration: "Lunch",
        postings: [
          { account: "Expenses:Food", units: { number: "12.50", currency: "USD" } },
          { account: "Assets:Cash", units: { number: "-12.50", currency: "USD" } },
        ],
      },
    },
  });
  assert.match(text, /from agent\/mcp/);
  assert.match(text, /add: 2026-03-01 Lunch/);
  assert.match(text, /Expenses:Food {2}12.50 USD/);
});
