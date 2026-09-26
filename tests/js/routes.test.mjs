// Unit tests for static/js/lib/routes.js (run: node --test tests/js/*.test.mjs).
import assert from "node:assert/strict";
import { test } from "node:test";

import { parseRoute, projectPath, taskPath } from "../../taskboard/static/js/lib/routes.js";

test("views", () => {
  assert.deepEqual(parseRoute("/"), { name: "home", params: {} });
  assert.deepEqual(parseRoute("/priority"), { name: "priority", params: {} });
  assert.deepEqual(parseRoute("/people/"), { name: "people", params: {} });
});

test("projects with optional key and node", () => {
  assert.deepEqual(parseRoute("/projects"), { name: "projects", params: { key: null, node: null } });
  assert.deepEqual(parseRoute("/projects/ASQ", "?node=12"), {
    name: "projects",
    params: { key: "ASQ", node: 12 },
  });
  assert.deepEqual(parseRoute("/projects/ASQ", "?node=abc").params.node, null);
});

test("task permalinks", () => {
  assert.deepEqual(parseRoute("/t/K7Q2MX"), { name: "task", params: { key: "K7Q2MX", tab: "details" } });
  assert.deepEqual(parseRoute("/t/K7Q2MX/conversation"), {
    name: "task",
    params: { key: "K7Q2MX", tab: "conversation" },
  });
  assert.equal(parseRoute("/t/K7Q2MX/history").name, "notFound");
  assert.equal(parseRoute("/t").name, "notFound");
});

test("administration tabs", () => {
  assert.deepEqual(parseRoute("/admin"), { name: "admin", params: { tab: "users" } });
  assert.deepEqual(parseRoute("/admin/audit"), { name: "admin", params: { tab: "audit" } });
  assert.equal(parseRoute("/admin/secrets").name, "notFound");
});

test("unknown paths", () => {
  assert.equal(parseRoute("/nope").name, "notFound");
  assert.equal(parseRoute("/priority/extra").name, "notFound");
});

test("deployment under a base path", () => {
  assert.deepEqual(parseRoute("/taskboard/t/104", "", "/taskboard/"), {
    name: "task",
    params: { key: "104", tab: "details" },
  });
  assert.equal(parseRoute("/taskboard/", "", "/taskboard/").name, "home");
});

test("building paths", () => {
  assert.equal(taskPath("K7Q2MX"), "t/K7Q2MX");
  assert.equal(taskPath("T-104", "conversation"), "t/104/conversation");
  assert.equal(projectPath("ASQ"), "projects/ASQ");
  assert.equal(projectPath("ASQ", 7), "projects/ASQ?node=7");
  assert.equal(projectPath(null), "projects");
});

test("routePath inverts parseRoute", async () => {
  const { routePath } = await import("../../taskboard/static/js/lib/routes.js");
  for (const path of ["priority", "people", "projects/ASQ?node=7", "projects", "t/104/conversation", "admin/roles"]) {
    const [pathname, search = ""] = path.split("?");
    assert.equal(routePath(parseRoute(`/${pathname}`, search ? `?${search}` : "")), path);
  }
  assert.equal(routePath({ name: "notFound", params: {} }), "priority");
});
