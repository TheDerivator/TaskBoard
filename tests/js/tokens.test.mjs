// Unit tests for static/js/lib/tokens.js, the "via" wording of lib/format.js and lib/events.js, and
// the profile route (API tokens for AI agents, D-097).
import assert from "node:assert/strict";
import { test } from "node:test";

import { routeAllowed } from "../../taskboard/static/js/lib/access.js";
import { describeEvent } from "../../taskboard/static/js/lib/events.js";
import { actorName } from "../../taskboard/static/js/lib/format.js";
import { releasedText } from "../../taskboard/static/js/lib/releases.js";
import { parseRoute } from "../../taskboard/static/js/lib/routes.js";
import { DEFAULT_EXPIRY, EXPIRY_CHOICES, envCommands, expiryText, lastUsedText, scopeLabel } from "../../taskboard/static/js/lib/tokens.js";

const anna = { user_id: 1, display_name: "Anna Claes", person_id: 1, via: null };
const agent = { ...anna, via: "Claude Code" };

test("what a token did names the token", () => {
  assert.equal(actorName(anna), "Anna Claes");
  assert.equal(actorName(agent), "Anna Claes via Claude Code");
  assert.equal(actorName(null), "Someone");
  assert.equal(actorName(undefined, "System"), "System");
  const lookup = { people: new Map() };
  assert.equal(describeEvent({ kind: "created", data: {}, actor: agent }, lookup).actor, "Anna Claes via Claude Code");
  assert.match(releasedText({ released_at: "2026-09-12T10:00:00Z", released_by: agent }), /· Anna Claes via Claude Code$/);
});

test("a token's expiry and last use", () => {
  assert.equal(expiryText({ expires_at: null, expired: false }), "Never expires");
  assert.equal(expiryText({ expires_at: "2027-01-04T12:00:00Z", expired: false }), "Expires 4 Jan 2027");
  assert.equal(expiryText({ expires_at: "2026-01-04T12:00:00Z", expired: true }), "Expired 4 Jan 2026");
  assert.equal(lastUsedText({ last_used_at: null }), "Never used");
  assert.match(lastUsedText({ last_used_at: "2026-10-03T12:02:00Z" }), /^Last used 3 Oct, \d\d:02$/);
});

test("the choices for a new token", () => {
  assert.equal(scopeLabel("read"), "Read only");
  assert.equal(scopeLabel("write"), "Read and write");
  assert.ok(EXPIRY_CHOICES.some((c) => c.days === DEFAULT_EXPIRY));
  assert.equal(EXPIRY_CHOICES.at(-1).days, null); // "Never" is the user's choice to make
});

test("the commands put the token where the agent guide says to look", () => {
  const commands = envCommands("tb_abc-_9");
  assert.deepEqual(
    commands.map((c) => c.command),
    ['$env:TASKBOARD_TOKEN = "tb_abc-_9"', 'setx TASKBOARD_TOKEN "tb_abc-_9"', "export TASKBOARD_TOKEN='tb_abc-_9'"],
  );
});

test("the profile is for people who are logged in", () => {
  assert.deepEqual(parseRoute("/profile", "", "/"), { name: "profile", params: {} });
  assert.deepEqual(parseRoute("/tb/profile", "", "/tb/"), { name: "profile", params: {} });
  assert.equal(parseRoute("/profile/x", "", "/").name, "notFound");
  const permissions = { "task.view": { everywhere: true, section_ids: [] } };
  assert.equal(routeAllowed({ is_anonymous: false, permissions }, "profile"), true);
  assert.equal(routeAllowed({ is_anonymous: true, permissions }, "profile"), false);
});
