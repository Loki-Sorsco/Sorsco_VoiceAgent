import type { ContactSubmission } from "./types";

// Sends contact submissions via Resend (https://resend.com). Returns true if
// the email was actually sent. Without RESEND_API_KEY we skip sending — the
// submission is still stored and visible in the admin panel.

export async function sendContactEmail(
  c: Omit<ContactSubmission, "emailed">
): Promise<boolean> {
  const apiKey = process.env.RESEND_API_KEY;
  const to = process.env.CONTACT_TO_EMAIL || "dev@sorsco.in";
  const from = process.env.CONTACT_FROM_EMAIL || "Curious Cubs <onboarding@resend.dev>";
  if (!apiKey) {
    console.warn("[contact] RESEND_API_KEY not set — submission stored but not emailed");
    return false;
  }

  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const html = `
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto">
      <h2 style="color:#155263">New enquiry from the Curious Cubs website</h2>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:8px;border:1px solid #eee;font-weight:bold;width:120px">Name</td><td style="padding:8px;border:1px solid #eee">${esc(c.name)}</td></tr>
        <tr><td style="padding:8px;border:1px solid #eee;font-weight:bold">Email</td><td style="padding:8px;border:1px solid #eee">${esc(c.email)}</td></tr>
        <tr><td style="padding:8px;border:1px solid #eee;font-weight:bold">Phone</td><td style="padding:8px;border:1px solid #eee">${esc(c.phone || "—")}</td></tr>
        <tr><td style="padding:8px;border:1px solid #eee;font-weight:bold">Message</td><td style="padding:8px;border:1px solid #eee;white-space:pre-wrap">${esc(c.message)}</td></tr>
      </table>
      <p style="color:#888;font-size:12px">Received ${c.createdAt}</p>
    </div>`;

  try {
    const res = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from,
        to: [to],
        reply_to: c.email,
        subject: `New enquiry from ${c.name} — Curious Cubs`,
        html,
      }),
    });
    if (!res.ok) {
      console.error("[contact] Resend error:", res.status, await res.text());
      return false;
    }
    return true;
  } catch (err) {
    console.error("[contact] Failed to send email:", err);
    return false;
  }
}
