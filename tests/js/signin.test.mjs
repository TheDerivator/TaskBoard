// Unit tests for static/js/lib/signin.js: when Windows sign-in is tried, and what is said when it fails.
import assert from "node:assert/strict";
import { test } from "node:test";

import { isWindowsRefusal, shouldTryWindowsSignIn, windowsSignInMessage } from "../../taskboard/static/js/lib/signin.js";

const visitor = (windows) => ({ is_anonymous: true, login: { password: true, providers: [], windows } });

test("the page signs in by itself only when the server asks for it", () => {
  assert.equal(shouldTryWindowsSignIn(visitor({ automatic: true }), false), true);
  assert.equal(shouldTryWindowsSignIn(visitor({ automatic: false }), false), false); // only the button
  assert.equal(shouldTryWindowsSignIn(visitor(null), false), false); // Windows sign-in is off
  assert.equal(shouldTryWindowsSignIn(visitor(undefined), false), false); // an older server
});

test("once per tab, and never for someone who is signed in", () => {
  assert.equal(shouldTryWindowsSignIn(visitor({ automatic: true }), true), false);
  const admin = { ...visitor({ automatic: true }), is_anonymous: false };
  assert.equal(shouldTryWindowsSignIn(admin, false), false);
  assert.equal(shouldTryWindowsSignIn(null, false), false);
});

test("an unanswered challenge is not worth a message, a refused person is", () => {
  const unanswered = { status: 401, code: "windows_sign_in_required", message: "sign in with your Windows account" };
  const noAccount = { status: 401, code: "invalid_credentials", message: "no account has been set up for you" };
  const suspended = { status: 403, code: "permission_denied", message: "this account is suspended" };
  assert.equal(isWindowsRefusal(unanswered), false);
  assert.equal(isWindowsRefusal(noAccount), true);
  assert.equal(isWindowsRefusal(suspended), true);
  assert.equal(isWindowsRefusal({ status: 0, code: "network", message: "The server cannot be reached." }), false);
  assert.equal(isWindowsRefusal({ status: 500, code: "http_500" }), false);
});

test("whoever pressed the button is told what happened", () => {
  const unanswered = { status: 401, code: "windows_sign_in_required", message: "sign in with your Windows account" };
  assert.match(windowsSignInMessage(unanswered), /did not work in this browser/);
  assert.equal(windowsSignInMessage({ status: 403, code: "permission_denied", message: "this account is suspended" }), "this account is suspended");
});
