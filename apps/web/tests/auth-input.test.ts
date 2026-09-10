import { test } from "node:test";
import assert from "node:assert/strict";
import { signInInput, signUpInput } from "../src/lib/auth-input";

test("registration rejects weak passwords and invalid identity fields", () => {
  assert.equal(signUpInput.safeParse({ name: "A", email: "invalid", password: "short" }).success, false);
  assert.equal(signUpInput.safeParse({ name: "Ada", email: "ada@example.test", password: "short" }).success, false);
  assert.equal(signInInput.safeParse({ email: "ada@example.test", password: "x".repeat(129) }).success, false);
});
test("valid input normalizes email and name without modifying the password", () => {
  const input = signUpInput.parse({ name: " Ada ", email: "ADA@example.test", password: "a long passphrase " });
  assert.equal(input.email, "ada@example.test");
  assert.equal(input.name, "Ada");
  assert.equal(input.password, "a long passphrase ");
});
