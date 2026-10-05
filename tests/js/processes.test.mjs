// Unit tests for static/js/lib/processes.js and lib/access.js: which processes and views a visitor gets.
import assert from "node:assert/strict";
import { test } from "node:test";

import { homeRoute, routeAllowed } from "../../taskboard/static/js/lib/access.js";
import {
  defaultProcess,
  findProcessRoute,
  moduleProcesses,
  processDepartments,
} from "../../taskboard/static/js/lib/processes.js";

const DEPARTMENTS = [
  { id: 1, code: "STL", sections: [{ id: 11, name: "Quality" }, { id: 12, name: "Process" }] },
  { id: 2, code: "R&D", sections: [{ id: 21, name: "Coatings" }] },
  { id: 3, code: "HR", sections: [] },
];
const PROCESSES = [
  { id: 1, code: "CV", name: "Convertor", section_id: 12, department_id: 1 },
  { id: 2, code: "LM", name: "Ladle metallurgy", section_id: 12, department_id: 1 },
  { id: 3, code: "CC", name: "Continuous casting", section_id: 12, department_id: 1 },
  { id: 4, code: "PC", name: "Paint coating", section_id: 21, department_id: 2 },
];
const reach = (everywhere, sectionIds = []) => ({ everywhere, section_ids: sectionIds });
const nowhere = reach(false);
function me(permissions) {
  const all = ["task.view", "change.view", "change.edit", "knowledge.view"];
  return { permissions: Object.fromEntries(all.map((p) => [p, permissions[p] ?? nowhere])) };
}

test("a module shows the processes whose owning section grants its view right", () => {
  const visitor = me({ "change.view": reach(false, [21]), "knowledge.view": reach(true) });
  assert.deepEqual(moduleProcesses(PROCESSES, visitor, "change.view").map((p) => p.code), ["PC"]);
  assert.equal(moduleProcesses(PROCESSES, visitor, "knowledge.view").length, 4);
  assert.deepEqual(moduleProcesses(PROCESSES, me({}), "knowledge.view"), []);
});

test("only departments with processes are offered", () => {
  assert.deepEqual(processDepartments(DEPARTMENTS, PROCESSES).map((d) => d.code), ["STL", "R&D"]);
  assert.deepEqual(processDepartments(DEPARTMENTS, PROCESSES.slice(0, 1)).map((d) => d.code), ["STL"]);
});

test("a URL names a process by its code, ignoring case; the process decides the department", () => {
  const found = findProcessRoute(DEPARTMENTS, PROCESSES, { department: "stl", process: "lm" });
  assert.equal(found.process.code, "LM");
  assert.equal(found.department.code, "STL");
  // A wrong department is only a spelling mistake: process codes are unique.
  assert.equal(findProcessRoute(DEPARTMENTS, PROCESSES, { department: "R&D", process: "CC" }).department.code, "STL");
  assert.equal(findProcessRoute(DEPARTMENTS, PROCESSES, { department: "STL", process: "XX" }), null);
});

test("a URL may name only a department, or nothing", () => {
  assert.deepEqual(findProcessRoute(DEPARTMENTS, PROCESSES, {}), { department: null, process: null });
  assert.equal(findProcessRoute(DEPARTMENTS, PROCESSES, { department: "r&d" }).department.code, "R&D");
  assert.equal(findProcessRoute(DEPARTMENTS, PROCESSES, { department: "XYZ" }), null);
});

test("without a process in the URL: the one used last, else the department's first", () => {
  assert.equal(defaultProcess(PROCESSES).code, "CV");
  assert.equal(defaultProcess(PROCESSES, { remembered: "CC" }).code, "CC");
  assert.equal(defaultProcess(PROCESSES, { remembered: "gone" }).code, "CV");
  assert.equal(defaultProcess(PROCESSES, { remembered: "CC", departmentId: 2 }).code, "PC");
  assert.equal(defaultProcess([], { remembered: "CC" }), null);
});

test("each view needs its module's view right; home is the first module the visitor may use", () => {
  const knowledgeOnly = me({ "knowledge.view": reach(false, [12]) });
  assert.ok(routeAllowed(knowledgeOnly, "knowledge") && routeAllowed(knowledgeOnly, "cpl"));
  assert.ok(!routeAllowed(knowledgeOnly, "priority") && !routeAllowed(knowledgeOnly, "change"));
  assert.ok(routeAllowed(knowledgeOnly, "notFound"));
  assert.equal(homeRoute(knowledgeOnly), "knowledge");
  assert.equal(homeRoute(me({ "change.view": reach(true), "knowledge.view": reach(true) })), "changes");
  assert.equal(homeRoute(me({ "task.view": reach(true) })), "priority");
  assert.ok(!routeAllowed(me({}), "admin"));
});
