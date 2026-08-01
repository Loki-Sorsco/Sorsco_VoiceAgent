import { NextResponse } from "next/server";
import { getSessions } from "@/lib/store";

export const dynamic = "force-dynamic";

// Public: upcoming webinar sessions, consumed by the website.
export async function GET() {
  const sessions = await getSessions();
  return NextResponse.json({ sessions });
}
