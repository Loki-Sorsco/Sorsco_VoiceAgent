import { createHmac, timingSafeEqual } from "crypto";
import { cookies } from "next/headers";

// Cookie-based admin session, signed with HMAC over the admin password so no
// extra secret needs configuring.

export const ADMIN_COOKIE = "cc_admin";
const SESSION_HOURS = 24 * 7;

function adminPassword(): string {
  return process.env.ADMIN_PASSWORD || "curiouscubs@2026";
}

function sign(payload: string): string {
  return createHmac("sha256", `cc-admin:${adminPassword()}`)
    .update(payload)
    .digest("hex");
}

export function checkPassword(password: string): boolean {
  const expected = Buffer.from(adminPassword());
  const given = Buffer.from(password);
  if (expected.length !== given.length) return false;
  return timingSafeEqual(expected, given);
}

export function makeToken(): string {
  const expires = Date.now() + SESSION_HOURS * 3600 * 1000;
  const payload = String(expires);
  return `${payload}.${sign(payload)}`;
}

export function verifyToken(token: string | undefined): boolean {
  if (!token) return false;
  const [payload, sig] = token.split(".");
  if (!payload || !sig) return false;
  const expected = sign(payload);
  if (sig.length !== expected.length) return false;
  if (!timingSafeEqual(Buffer.from(sig), Buffer.from(expected))) return false;
  return Number(payload) > Date.now();
}

export function isAdminRequest(): boolean {
  return verifyToken(cookies().get(ADMIN_COOKIE)?.value);
}
