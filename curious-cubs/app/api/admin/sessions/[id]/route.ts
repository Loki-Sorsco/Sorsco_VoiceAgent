import { NextRequest, NextResponse } from "next/server";
import { isAdminRequest } from "@/lib/auth";
import { getSessions, saveSessions } from "@/lib/store";
import { validateSessionInput } from "@/lib/types";

export const dynamic = "force-dynamic";

type Params = { params: { id: string } };

export async function PUT(req: NextRequest, { params }: Params) {
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
  const sessions = await getSessions();
  const idx = sessions.findIndex((s) => s.id === params.id);
  if (idx === -1) {
    return NextResponse.json({ error: "Session not found" }, { status: 404 });
  }
  sessions[idx] = {
    ...sessions[idx],
    ...input,
    updatedAt: new Date().toISOString(),
  };
  await saveSessions(sessions);
  return NextResponse.json({ session: sessions[idx] });
}

export async function DELETE(_req: NextRequest, { params }: Params) {
  if (!isAdminRequest()) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const sessions = await getSessions();
  const next = sessions.filter((s) => s.id !== params.id);
  if (next.length === sessions.length) {
    return NextResponse.json({ error: "Session not found" }, { status: 404 });
  }
  await saveSessions(next);
  return NextResponse.json({ ok: true });
}
