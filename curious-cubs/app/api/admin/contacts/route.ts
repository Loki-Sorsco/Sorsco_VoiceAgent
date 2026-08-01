import { NextResponse } from "next/server";
import { isAdminRequest } from "@/lib/auth";
import { getContacts } from "@/lib/store";

export const dynamic = "force-dynamic";

export async function GET() {
  if (!isAdminRequest()) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const contacts = await getContacts();
  return NextResponse.json({ contacts });
}
