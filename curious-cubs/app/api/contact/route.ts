import { NextRequest, NextResponse } from "next/server";
import { randomUUID } from "crypto";
import { addContact } from "@/lib/store";
import { sendContactEmail } from "@/lib/email";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const name = typeof body.name === "string" ? body.name.trim() : "";
  const email = typeof body.email === "string" ? body.email.trim() : "";
  const phone = typeof body.phone === "string" ? body.phone.trim() : "";
  const message = typeof body.message === "string" ? body.message.trim() : "";

  if (!name || !message || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return NextResponse.json(
      { error: "Please fill in your name, a valid email and a message." },
      { status: 400 }
    );
  }
  if (name.length > 200 || email.length > 200 || phone.length > 50 || message.length > 5000) {
    return NextResponse.json({ error: "Input too long." }, { status: 400 });
  }

  const base = {
    id: randomUUID(),
    name,
    email,
    phone,
    message,
    createdAt: new Date().toISOString(),
  };

  const emailed = await sendContactEmail(base);
  await addContact({ ...base, emailed });

  return NextResponse.json({ ok: true, emailed });
}
