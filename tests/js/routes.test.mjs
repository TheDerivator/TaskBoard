// Unit tests for static/js/lib/routes.js (run: node --test tests/js/*.test.mjs).
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  boxHomePath,
  boxLinkPath,
  changePath,
  changesPath,
  cplPath,
  fmeaPath,
  knowledgePath,
  parseRoute,
  peoplePath,
  projectPath,
  routePath,
  taskPath,
} from "../../taskboard/static/js/lib/routes.js";

test("views", () => {
  assert.deepEqual(parseRoute("/"), { name: "home", params: {} });
  assert.deepEqual(parseRoute("/priority"), { name: "priority", params: {} });
  assert.deepEqual(parseRoute("/people/"), { name: "people", params: { department: null, section: null } });
});

test("team views: a department, or one of its sections", () => {
  assert.deepEqual(parseRoute("/people/STL").params, { department: "STL", section: null });
  assert.deepEqual(parseRoute("/people/STL/Quality").params, { department: "STL", section: "Quality" });
  assert.deepEqual(parseRoute("/people/R%26D/Surface%20coatings").params, {
    department: "R&D",
    section: "Surface coatings",
  });
  assert.equal(parseRoute("/people/STL/Quality/extra").name, "notFound");
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
  assert.equal(peoplePath(), "people");
  assert.equal(peoplePath("STL"), "people/STL");
  assert.equal(peoplePath("R&D", "Surface coatings"), "people/R%26D/Surface%20coatings");
});

test("routePath inverts parseRoute", async () => {
  const { routePath } = await import("../../taskboard/static/js/lib/routes.js");
  for (const path of ["priority", "people", "people/STL", "people/R%26D/Coatings", "projects/ASQ?node=7", "projects", "t/104/conversation", "admin/roles"]) {
    const [pathname, search = ""] = path.split("?");
    assert.equal(routePath(parseRoute(`/${pathname}`, search ? `?${search}` : "")), path);
  }
  assert.equal(routePath({ name: "notFound", params: {} }), "priority");
});

test("process changes: list, timeline and one change (DESIGN 'Stable links')", () => {
  assert.deepEqual(parseRoute("/changes"), {
    name: "changes",
    params: { department: null, process: null, view: "list" },
  });
  assert.deepEqual(parseRoute("/changes/STL/LM").params, { department: "STL", process: "LM", view: "list" });
  assert.deepEqual(parseRoute("/changes/stl/lm/timeline", "?range=12&box=m-level").params, {
    department: "stl",
    process: "lm",
    view: "timeline",
    range: 12,
    box: "m-level",
  });
  assert.equal(parseRoute("/changes/STL/LM/timeline", "?range=5").params.range, 6);
  assert.deepEqual(parseRoute("/changes/STL/LM/lm-07"), {
    name: "change",
    params: { department: "STL", process: "LM", key: "LM-07", tab: "details" },
  });
  assert.equal(parseRoute("/changes/STL/LM/LM-07/conversation").params.tab, "conversation");
  assert.equal(parseRoute("/changes/STL/LM/LM-07/history").name, "notFound");
  assert.equal(parseRoute("/changes/STL/LM/whatever").name, "notFound");
});

test("process knowledge: the map, FMEA and the control plan", () => {
  assert.deepEqual(parseRoute("/knowledge/STL/CC/fm-level"), {
    name: "knowledge",
    params: { department: "STL", process: "CC", box: "fm-level" },
  });
  assert.deepEqual(parseRoute("/fmea/STL/CC", "?box=fm-level&release=v3"), {
    name: "fmea",
    params: { department: "STL", process: "CC", box: "fm-level", release: "v3" },
  });
  assert.deepEqual(parseRoute("/cpl/STL/sliver-lines/fm-level", "?process=CC"), {
    name: "cpl",
    params: { department: "STL", defect: "sliver-lines", cause: "fm-level", process: "CC", release: null },
  });
  assert.deepEqual(parseRoute("/cpl").params, { department: null, defect: null, cause: null, process: null, release: null });
  assert.equal(parseRoute("/knowledge/STL/CC/fm-level/extra").name, "notFound");
});

test("process paths round-trip through parseRoute", () => {
  const paths = [
    changesPath(),
    changesPath("STL", "LM"),
    changesPath("STL", "LM", { view: "timeline" }),
    changesPath("STL", "LM", { view: "timeline", range: 12, box: "m-level" }),
    changePath("STL", "LM", "LM-07"),
    changePath("STL", "LM", "LM-07", "conversation"),
    knowledgePath("STL", "CC"),
    knowledgePath("STL", "CC", "fm-level"),
    fmeaPath("STL", "CC", { box: "fm-level", release: "v3" }),
    cplPath("R&D", "sliver-lines", "fm-level", { process: "CC" }),
  ];
  for (const path of paths) {
    const [pathname, search = ""] = path.split("?");
    assert.equal(routePath(parseRoute(`/${pathname}`, search ? `?${search}` : "")), path);
  }
  assert.equal(changesPath("STL", "LM", { view: "timeline" }), "changes/STL/LM/timeline");
  assert.equal(cplPath("R&D", "blisters"), "cpl/R%26D/blisters");
});

test("a box by its key alone opens where it lives (stable links for dashboards)", () => {
  assert.deepEqual(parseRoute("/box/fm-level"), { name: "box", params: { key: "fm-level" } });
  assert.equal(routePath(parseRoute(`/${boxLinkPath("fm-level")}`)), "box/fm-level");
  const lookup = {
    processes: new Map([[3, { code: "CC", department_id: 1 }]]),
    departments: new Map([[1, { code: "STL" }]]),
    sections: new Map([[7, { department_id: 1 }]]),
  };
  assert.equal(boxHomePath({ key: "fm-level", process_id: 3, section_id: 9 }, lookup), "knowledge/STL/CC/fm-level");
  assert.equal(boxHomePath({ key: "d-sliver", process_id: null, section_id: 7 }, lookup), "cpl/STL/d-sliver");
});
