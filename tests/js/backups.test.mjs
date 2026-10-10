// Unit tests for static/js/lib/backups.js: sizes, why a backup is kept, the state of the backups
// (Administration › Backups, D-100).
import assert from "node:assert/strict";
import { test } from "node:test";

import { KEPT_AS, backupStatus, formatSize } from "../../taskboard/static/js/lib/backups.js";

const TAKEN = new Date(2026, 9, 10, 2, 0).toISOString(); // 10 October, 02:00 on this machine
const NEWEST = { name: "taskboard-backup-20261010-000000.zip", taken_at: TAKEN, size: 1536, kept_as: ["newest"] };

function overview(changes) {
  return { problem: null, backups: [NEWEST], total_size: 3 * 1024 * 1024, overdue: false, ...changes };
}

test("sizes as Windows Explorer shows them", () => {
  assert.equal(formatSize(0), "0 B");
  assert.equal(formatSize(1023), "1023 B");
  assert.equal(formatSize(1536), "1.5 KB");
  assert.equal(formatSize(12 * 1024 * 1024), "12 MB");
  assert.equal(formatSize(2.4 * 1024 ** 3), "2.4 GB");
});

test("why a backup is kept", () => {
  assert.deepEqual(Object.keys(KEPT_AS), ["newest", "weekly", "monthly"]);
  assert.equal(KEPT_AS.weekly, "First of the week");
});

test("the state of the backups", () => {
  const ok = backupStatus(overview());
  assert.equal(ok.ok, true);
  assert.equal(ok.text, "Newest backup: 10 Oct 2026, 02:00. 1 backup, 3.0 MB in all.");

  const late = backupStatus(overview({ overdue: true }));
  assert.equal(late.ok, false);
  assert.match(late.text, /more than two days ago\. Check the scheduled task/);

  assert.deepEqual(backupStatus(overview({ backups: [], overdue: true })), {
    ok: false,
    text: "No backups yet. Check the scheduled task that makes them.",
  });
  const problem = "The folder cannot be read: Access is denied.";
  assert.deepEqual(backupStatus(overview({ problem, backups: [] })), { ok: false, text: problem });
});
