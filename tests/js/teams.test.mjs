// Unit tests for static/js/lib/teams.js: finding a team from its URL, its label, members and path.
import assert from "node:assert/strict";
import { test } from "node:test";

import { EVERYONE, findTeam, teamLabel, teamMembers, teamPath } from "../../taskboard/static/js/lib/teams.js";

const quality = { id: 1, department_id: 1, name: "Quality" };
const process = { id: 2, department_id: 1, name: "Process" };
const coatings = { id: 3, department_id: 2, name: "Surface coatings" };
const STL = { id: 1, code: "STL", name: "STL", sections: [quality, process] };
const RD = { id: 2, code: "R&D", name: "Research", sections: [coatings] };
const departments = [STL, RD];

const people = [
  { id: 1, name: "Anna Claes", section_id: 1, department_id: 1 },
  { id: 2, name: "Bram Peeters", section_id: 2, department_id: 1 },
  { id: 3, name: "Chloé Martens", section_id: 1, department_id: 1 },
  { id: 4, name: "Gert Smet", section_id: 3, department_id: 2 },
];

test("no department in the URL is everyone", () => {
  assert.equal(findTeam(departments, {}), EVERYONE);
  assert.equal(findTeam(departments, { department: null, section: null }), EVERYONE);
});

test("a department, or one of its sections", () => {
  assert.deepEqual(findTeam(departments, { department: "STL" }), { department: STL, section: null });
  assert.deepEqual(findTeam(departments, { department: "STL", section: "Quality" }), {
    department: STL,
    section: quality,
  });
  assert.deepEqual(findTeam(departments, { department: "R&D", section: "Surface coatings" }), {
    department: RD,
    section: coatings,
  });
});

test("links are forgiving about case", () => {
  assert.deepEqual(findTeam(departments, { department: "stl", section: "QUALITY" }), {
    department: STL,
    section: quality,
  });
});

test("an exact spelling wins over a match that ignores case", () => {
  const upper = { id: 7, department_id: 9, name: "QA" };
  const lower = { id: 8, department_id: 9, name: "qa" };
  const lab = { id: 9, code: "LAB", name: "Lab", sections: [upper, lower] };
  assert.equal(findTeam([lab], { department: "LAB", section: "qa" }).section, lower);
  assert.equal(findTeam([lab], { department: "LAB", section: "QA" }).section, upper);
});

test("unknown departments and sections are no team at all", () => {
  assert.equal(findTeam(departments, { department: "XYZ" }), null);
  assert.equal(findTeam(departments, { department: "STL", section: "Coatings" }), null); // another department's
  assert.equal(findTeam([], { department: "STL" }), null);
});

test("labels", () => {
  assert.equal(teamLabel(EVERYONE), "Everyone");
  assert.equal(teamLabel({ department: STL, section: null }), "STL");
  assert.equal(teamLabel({ department: STL, section: quality }), "STL · Quality");
});

test("members of a section, of a department, or everyone, in the original order", () => {
  const names = (list) => list.map((p) => p.name);
  assert.deepEqual(names(teamMembers(people, { department: STL, section: quality })), ["Anna Claes", "Chloé Martens"]);
  assert.deepEqual(names(teamMembers(people, { department: STL, section: null })), [
    "Anna Claes",
    "Bram Peeters",
    "Chloé Martens",
  ]);
  assert.deepEqual(names(teamMembers(people, { department: RD, section: null })), ["Gert Smet"]);
  assert.equal(teamMembers(people, EVERYONE), people);
});

test("paths use the organization's own spelling", () => {
  assert.equal(teamPath(EVERYONE), "people");
  assert.equal(teamPath({ department: STL, section: null }), "people/STL");
  assert.equal(teamPath(findTeam(departments, { department: "r&d", section: "surface COATINGS" })), "people/R%26D/Surface%20coatings");
});
