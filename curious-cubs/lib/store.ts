import { Redis } from "@upstash/redis";
import { promises as fs } from "fs";
import path from "path";
import type { WebinarSession, ContactSubmission } from "./types";

// Storage layer: Upstash Redis (or Vercel KV) when configured, otherwise a
// local JSON file. The file fallback keeps local dev zero-config; on Vercel
// without Redis it lands in /tmp, which works but does not survive
// redeploys — the admin panel shows a warning in that case.

const SESSIONS_KEY = "cc:sessions";
const CONTACTS_KEY = "cc:contacts";

type Db = { sessions: WebinarSession[]; contacts: ContactSubmission[] };

function redisClient(): Redis | null {
  const url = process.env.UPSTASH_REDIS_REST_URL || process.env.KV_REST_API_URL;
  const token = process.env.UPSTASH_REDIS_REST_TOKEN || process.env.KV_REST_API_TOKEN;
  if (!url || !token) return null;
  return new Redis({ url, token });
}

export function storageMode(): "redis" | "file" {
  return redisClient() ? "redis" : "file";
}

function dbFile(): string {
  const dir =
    process.env.VERCEL === "1"
      ? path.join("/tmp", "curious-cubs-data")
      : path.join(process.cwd(), ".data");
  return path.join(dir, "db.json");
}

async function readFileDb(): Promise<Db> {
  try {
    const raw = await fs.readFile(dbFile(), "utf8");
    const parsed = JSON.parse(raw);
    return {
      sessions: Array.isArray(parsed.sessions) ? parsed.sessions : [],
      contacts: Array.isArray(parsed.contacts) ? parsed.contacts : [],
    };
  } catch {
    return { sessions: [], contacts: [] };
  }
}

async function writeFileDb(db: Db): Promise<void> {
  const file = dbFile();
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, JSON.stringify(db, null, 2), "utf8");
}

export async function getSessions(): Promise<WebinarSession[]> {
  const redis = redisClient();
  let sessions: WebinarSession[];
  if (redis) {
    sessions = (await redis.get<WebinarSession[]>(SESSIONS_KEY)) ?? [];
  } else {
    sessions = (await readFileDb()).sessions;
  }
  return sessions.sort((a, b) =>
    `${a.date}T${a.time}`.localeCompare(`${b.date}T${b.time}`)
  );
}

export async function saveSessions(sessions: WebinarSession[]): Promise<void> {
  const redis = redisClient();
  if (redis) {
    await redis.set(SESSIONS_KEY, sessions);
  } else {
    const db = await readFileDb();
    db.sessions = sessions;
    await writeFileDb(db);
  }
}

export async function getContacts(): Promise<ContactSubmission[]> {
  const redis = redisClient();
  let contacts: ContactSubmission[];
  if (redis) {
    contacts = (await redis.get<ContactSubmission[]>(CONTACTS_KEY)) ?? [];
  } else {
    contacts = (await readFileDb()).contacts;
  }
  return contacts.sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export async function addContact(contact: ContactSubmission): Promise<void> {
  const redis = redisClient();
  if (redis) {
    const contacts = (await redis.get<ContactSubmission[]>(CONTACTS_KEY)) ?? [];
    contacts.push(contact);
    await redis.set(CONTACTS_KEY, contacts);
  } else {
    const db = await readFileDb();
    db.contacts.push(contact);
    await writeFileDb(db);
  }
}
