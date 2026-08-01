"use client";

import { useState } from "react";

type Status = "idle" | "sending" | "sent" | "error";

export default function ContactForm() {
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const fd = new FormData(form);
    setStatus("sending");
    setError("");
    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: fd.get("name"),
          email: fd.get("email"),
          phone: fd.get("phone"),
          message: fd.get("message"),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data.error || "Something went wrong. Please try again.");
        setStatus("error");
        return;
      }
      form.reset();
      setStatus("sent");
    } catch {
      setError("Network error. Please try again.");
      setStatus("error");
    }
  }

  if (status === "sent") {
    return (
      <div className="rounded-3xl bg-white p-10 text-center shadow-card">
        <div className="mb-3 text-5xl">💌</div>
        <p className="font-display text-2xl font-bold text-teal">
          Message sent!
        </p>
        <p className="mt-2 text-navy/70">
          Thanks for reaching out — we&apos;ll get back to you within a day.
        </p>
        <button
          onClick={() => setStatus("idle")}
          className="mt-6 rounded-full bg-sunshine px-6 py-2.5 font-display font-bold text-navy shadow-pop"
        >
          Send another message
        </button>
      </div>
    );
  }

  const input =
    "w-full rounded-2xl border-2 border-navy/10 bg-cream px-4 py-3 font-semibold text-navy placeholder:text-navy/40 focus:border-teal focus:outline-none";

  return (
    <form onSubmit={onSubmit} className="rounded-3xl bg-white p-6 shadow-card sm:p-8">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block font-display font-bold">Your name *</span>
          <input name="name" required maxLength={200} placeholder="Priya Sharma" className={input} />
        </label>
        <label className="block">
          <span className="mb-1 block font-display font-bold">Email *</span>
          <input name="email" type="email" required maxLength={200} placeholder="you@example.com" className={input} />
        </label>
      </div>
      <label className="mt-4 block">
        <span className="mb-1 block font-display font-bold">Phone (optional)</span>
        <input name="phone" maxLength={50} placeholder="+91 98765 43210" className={input} />
      </label>
      <label className="mt-4 block">
        <span className="mb-1 block font-display font-bold">Message *</span>
        <textarea
          name="message"
          required
          maxLength={5000}
          rows={4}
          placeholder="Hi! I'd like to know more about the upcoming webinars…"
          className={input}
        />
      </label>
      {error && (
        <p className="mt-3 rounded-xl bg-blush px-4 py-2 font-semibold text-coral">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={status === "sending"}
        className="mt-6 w-full rounded-full bg-coral px-6 py-3.5 font-display text-lg font-bold text-white shadow-pop transition-colors hover:bg-teal disabled:opacity-60"
      >
        {status === "sending" ? "Sending…" : "Send message ✉️"}
      </button>
    </form>
  );
}
