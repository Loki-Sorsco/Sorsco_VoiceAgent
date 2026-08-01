import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { isAdminRequest } from "@/lib/auth";
import { getSessions, saveSessions, storageMode } from "@/lib/store";
import { validateSessionInput } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!isAdminRequest()) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const sessions = await getSessions();
  return NextResponse.json({ sessions, storage: storageMode() });
}

export async function POST(req: NextRequest) {
  if (!isAdminRequest()) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }
  const input = validateSessionInput(body);
  if (!input) {
    return NextResponse.json(
      { error: "Title, date (YYYY-MM-DD) and time (HH:MM) are required." },
      { status: 400 }
    );
  }
  const now = new Date().toISOString();
  const session = { ...input, id: randomUUID(), createdAt: now, updatedAt: now };
  const sessions = await getSessions();
  sessions.push(session);
  await saveSessions(sessions);
  return NextResponse.json({ session }, { status: 201 });
}
