"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ContactSubmission, WebinarSession } from "@/lib/types";

// ─────────────────────────────────────────────────────────────
// Curious Cubs Admin — manage the webinar calendar shown on the
// website and read contact-form enquiries.
// ─────────────────────────────────────────────────────────────

type Tab = "calendar" | "enquiries";

const EMPTY_FORM = {
  title: "",
  date: "",
  time: "17:00",
  durationMins: 60,
  ageGroup: "",
  host: "",
  seats: 25,
  description: "",
  registrationLink: "",
};

type FormState = typeof EMPTY_FORM;

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function ymd(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

function formatTime(time: string): string {
  const [h, m] = time.split(":").map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

export default function AdminPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");

  const [tab, setTab] = useState<Tab>("calendar");
  const [sessions, setSessions] = useState<WebinarSession[]>([]);
  const [contacts, setContacts] = useState<ContactSubmission[]>([]);
  const [storage, setStorage] = useState<"redis" | "file">("redis");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");

  const now = new Date();
  const [viewYear, setViewYear] = useState(now.getFullYear());
  const [viewMonth, setViewMonth] = useState(now.getMonth());

  const [editing, setEditing] = useState<string | "new" | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState("");

  const loadSessions = useCallback(async () => {
    const res = await fetch("/api/admin/sessions", { cache: "no-store" });
    if (res.status === 401) {
      setAuthed(false);
      return;
    }
    const data = await res.json();
    setSessions(data.sessions ?? []);
    setStorage(data.storage ?? "redis");
    setAuthed(true);
  }, []);

  const loadContacts = useCallback(async () => {
    const res = await fetch("/api/admin/contacts", { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      setContacts(data.contacts ?? []);
    }
  }, []);

  useEffect(() => {
    loadSessions().catch(() => setAuthed(false));
  }, [loadSessions]);

  useEffect(() => {
    if (authed && tab === "enquiries") loadContacts().catch(() => {});
  }, [authed, tab, loadContacts]);

  function flash(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(""), 2500);
  }

  async function onLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginError("");
    const res = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (res.ok) {
      setPassword("");
      await loadSessions();
    } else {
      const data = await res.json().catch(() => ({}));
      setLoginError(data.error || "Login failed");
    }
  }

  async function onLogout() {
    await fetch("/api/admin/logout", { method: "POST" });
    setAuthed(false);
    setSessions([]);
    setContacts([]);
  }

  function openNew(date?: string) {
    setForm({ ...EMPTY_FORM, date: date || ymd(new Date()) });
    setFormError("");
    setEditing("new");
  }

  function openEdit(s: WebinarSession) {
    setForm({
      title: s.title,
      date: s.date,
      time: s.time,
      durationMins: s.durationMins,
      ageGroup: s.ageGroup,
      host: s.host,
      seats: s.seats,
      description: s.description,
      registrationLink: s.registrationLink,
    });
    setFormError("");
    setEditing(s.id);
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFormError("");
    const url =
      editing === "new" ? "/api/admin/sessions" : `/api/admin/sessions/${editing}`;
    const res = await fetch(url, {
      method: editing === "new" ? "POST" : "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    setBusy(false);
    if (res.ok) {
      setEditing(null);
      await loadSessions();
      flash(editing === "new" ? "Session added — live on the website ✅" : "Session updated ✅");
    } else {
      const data = await res.json().catch(() => ({}));
      setFormError(data.error || "Could not save the session.");
    }
  }

  async function onDelete(id: string) {
    if (!confirm("Delete this session? It will disappear from the website immediately.")) return;
    setBusy(true);
    const res = await fetch(`/api/admin/sessions/${id}`, { method: "DELETE" });
    setBusy(false);
    if (res.ok) {
      setEditing(null);
      await loadSessions();
      flash("Session deleted 🗑️");
    }
  }

  const byDate = useMemo(() => {
    const map = new Map<string, WebinarSession[]>();
    for (const s of sessions) {
      const list = map.get(s.date) ?? [];
      list.push(s);
      map.set(s.date, list);
    }
    return map;
  }, [sessions]);

  // ── Render ─────────────────────────────────────────────────

  if (authed === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-cream">
        <p className="font-display text-xl font-bold text-navy/60">Loading…</p>
      </div>
    );
  }

  if (!authed) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-navy px-4">
        <form
          onSubmit={onLogin}
          className="w-full max-w-sm rounded-3xl bg-white p-8 shadow-card"
        >
          <div className="text-center text-5xl">🐻</div>
          <h1 className="mt-3 text-center font-display text-2xl font-extrabold text-navy">
            Curious Cubs Admin
          </h1>
          <p className="mt-1 text-center text-sm font-semibold text-navy/60">
            Sign in to manage the webinar calendar
          </p>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Admin password"
            autoFocus
            className="mt-6 w-full rounded-2xl border-2 border-navy/10 bg-cream px-4 py-3 font-semibold text-navy focus:border-teal focus:outline-none"
          />
          {loginError && (
            <p className="mt-3 rounded-xl bg-blush px-4 py-2 text-sm font-bold text-coral">
              {loginError}
            </p>
          )}
          <button
            type="submit"
            className="mt-5 w-full rounded-full bg-coral py-3 font-display text-lg font-bold text-white shadow-pop hover:bg-teal"
          >
            Sign in
          </button>
        </form>
      </div>
    );
  }

  const firstDay = new Date(viewYear, viewMonth, 1).getDay();
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const todayStr = ymd(new Date());
  const cells: (string | null)[] = [
    ...Array.from({ length: firstDay }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) =>
      ymd(new Date(viewYear, viewMonth, i + 1))
    ),
  ];

  function shiftMonth(delta: number) {
    const d = new Date(viewYear, viewMonth + delta, 1);
    setViewYear(d.getFullYear());
    setViewMonth(d.getMonth());
  }

  const inputCls =
    "w-full rounded-xl border-2 border-navy/10 bg-cream px-3 py-2 font-semibold text-navy focus:border-teal focus:outline-none";
  const labelCls = "block text-sm font-display font-bold text-navy";

  return (
    <div className="min-h-screen bg-cream pb-16">
      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-navy/10 bg-navy text-cream">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <span className="font-display text-xl font-extrabold">
            🐻 Curious Cubs · Admin
          </span>
          <div className="flex items-center gap-2">
            <a
              href="/"
              target="_blank"
              className="rounded-full border border-cream/30 px-4 py-1.5 text-sm font-bold hover:bg-cream/10"
            >
              View website ↗
            </a>
            <button
              onClick={onLogout}
              className="rounded-full bg-coral px-4 py-1.5 text-sm font-display font-bold shadow-pop"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pt-6">
        {storage === "file" && process.env.NODE_ENV === "production" && (
          <div className="mb-4 rounded-2xl bg-sunshine/30 px-4 py-3 text-sm font-bold text-navy">
            ⚠️ No database connected — changes may be lost on redeploy. Add the
            free Upstash Redis integration in Vercel for permanent storage.
          </div>
        )}

        {/* Tabs */}
        <div className="mb-6 flex gap-2">
          {(
            [
              ["calendar", "📅 Calendar"],
              ["enquiries", `💌 Enquiries${contacts.length ? ` (${contacts.length})` : ""}`],
            ] as [Tab, string][]
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`rounded-full px-5 py-2 font-display font-bold transition-colors ${
                tab === key
                  ? "bg-navy text-cream shadow-pop"
                  : "bg-white text-navy/70 hover:text-navy"
              }`}
            >
              {label}
            </button>
          ))}
          {tab === "calendar" && (
            <button
              onClick={() => openNew()}
              className="ml-auto rounded-full bg-coral px-5 py-2 font-display font-bold text-white shadow-pop hover:bg-teal"
            >
              + New session
            </button>
          )}
        </div>

        {tab === "calendar" && (
          <>
            {/* Month navigation */}
            <div className="mb-4 flex items-center justify-between rounded-2xl bg-white px-4 py-3 shadow-card">
              <button
                onClick={() => shiftMonth(-1)}
                className="rounded-full bg-cream px-4 py-1.5 font-display font-bold hover:bg-blush"
              >
                ← Prev
              </button>
              <h2 className="font-display text-xl font-extrabold">
                {MONTHS[viewMonth]} {viewYear}
              </h2>
              <button
                onClick={() => shiftMonth(1)}
                className="rounded-full bg-cream px-4 py-1.5 font-display font-bold hover:bg-blush"
              >
                Next →
              </button>
            </div>

            {/* Month grid */}
            <div className="overflow-x-auto rounded-3xl bg-white p-4 shadow-card">
              <div className="grid min-w-[640px] grid-cols-7 gap-2">
                {WEEKDAYS.map((d) => (
                  <div key={d} className="pb-1 text-center text-sm font-display font-bold text-navy/50">
                    {d}
                  </div>
                ))}
                {cells.map((date, i) =>
                  date === null ? (
                    <div key={`pad-${i}`} />
                  ) : (
                    <button
                      key={date}
                      onClick={() => openNew(date)}
                      title="Click to add a session on this day"
                      className={`min-h-[92px] rounded-2xl border-2 p-1.5 text-left align-top transition-colors ${
                        date === todayStr
                          ? "border-teal bg-teal/5"
                          : "border-navy/5 hover:border-coral/40"
                      }`}
                    >
                      <span
                        className={`text-sm font-bold ${
                          date === todayStr ? "text-teal" : "text-navy/60"
                        }`}
                      >
                        {Number(date.slice(8))}
                      </span>
                      <div className="mt-1 space-y-1">
                        {(byDate.get(date) ?? []).map((s) => (
                          <span
                            key={s.id}
                            role="button"
                            tabIndex={0}
                            onClick={(e) => {
                              e.stopPropagation();
                              openEdit(s);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.stopPropagation();
                                openEdit(s);
                              }
                            }}
                            className="block truncate rounded-lg bg-coral px-1.5 py-0.5 text-xs font-bold text-white hover:bg-teal"
                          >
                            {formatTime(s.time)} {s.title}
                          </span>
                        ))}
                      </div>
                    </button>
                  )
                )}
              </div>
            </div>

            {/* All sessions list */}
            <h3 className="mt-8 font-display text-lg font-extrabold">
              All sessions ({sessions.length})
            </h3>
            <div className="mt-3 space-y-2">
              {sessions.length === 0 && (
                <p className="rounded-2xl bg-white p-6 text-center font-semibold text-navy/60 shadow-card">
                  No sessions yet — click <b>+ New session</b> or any calendar
                  day to add one. It appears on the website instantly.
                </p>
              )}
              {sessions.map((s) => (
                <div
                  key={s.id}
                  className="flex flex-wrap items-center gap-3 rounded-2xl bg-white px-4 py-3 shadow-card"
                >
                  <div className="min-w-[110px] font-display font-bold text-coral">
                    {s.date}
                  </div>
                  <div className="min-w-[70px] font-semibold text-navy/70">
                    {formatTime(s.time)}
                  </div>
                  <div className="flex-1 font-bold">{s.title}</div>
                  {s.ageGroup && (
                    <span className="rounded-full bg-blush px-3 py-0.5 text-xs font-bold text-coral">
                      {s.ageGroup}
                    </span>
                  )}
                  <button
                    onClick={() => openEdit(s)}
                    className="rounded-full bg-cream px-4 py-1.5 text-sm font-display font-bold hover:bg-blush"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => onDelete(s.id)}
                    className="rounded-full bg-blush px-4 py-1.5 text-sm font-display font-bold text-coral hover:bg-coral hover:text-white"
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        {tab === "enquiries" && (
          <div className="space-y-3">
            {contacts.length === 0 && (
              <p className="rounded-2xl bg-white p-6 text-center font-semibold text-navy/60 shadow-card">
                No enquiries yet. Contact-form submissions from the website show
                up here (and are emailed to {`dev@sorsco.in`} when Resend is
                configured).
              </p>
            )}
            {contacts.map((c) => (
              <div key={c.id} className="rounded-2xl bg-white p-4 shadow-card">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display font-bold">{c.name}</span>
                  <a href={`mailto:${c.email}`} className="text-sm font-semibold text-teal">
                    {c.email}
                  </a>
                  {c.phone && (
                    <span className="text-sm font-semibold text-navy/60">· {c.phone}</span>
                  )}
                  <span className="ml-auto text-xs font-semibold text-navy/50">
                    {new Date(c.createdAt).toLocaleString("en-IN")}
                  </span>
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                      c.emailed ? "bg-teal/10 text-teal" : "bg-sunshine/40 text-navy"
                    }`}
                  >
                    {c.emailed ? "Emailed ✓" : "Not emailed"}
                  </span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm font-semibold text-navy/80">
                  {c.message}
                </p>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Session editor modal */}
      {editing !== null && (
        <div
          className="fixed inset-0 z-30 flex items-center justify-center bg-navy/60 p-4"
          onClick={() => setEditing(null)}
        >
          <form
            onSubmit={onSave}
            onClick={(e) => e.stopPropagation()}
            className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-3xl bg-white p-6 shadow-card"
          >
            <h2 className="font-display text-xl font-extrabold">
              {editing === "new" ? "New webinar session" : "Edit session"}
            </h2>
            <div className="mt-4 space-y-3">
              <label className={labelCls}>
                Title *
                <input
                  className={inputCls}
                  required
                  maxLength={200}
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="Little Picassos: Finger Painting Fun"
                />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className={labelCls}>
                  Date *
                  <input
                    type="date"
                    className={inputCls}
                    required
                    value={form.date}
                    onChange={(e) => setForm({ ...form, date: e.target.value })}
                  />
                </label>
                <label className={labelCls}>
                  Time *
                  <input
                    type="time"
                    className={inputCls}
                    required
                    value={form.time}
                    onChange={(e) => setForm({ ...form, time: e.target.value })}
                  />
                </label>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <label className={labelCls}>
                  Duration (mins)
                  <input
                    type="number"
                    min={5}
                    className={inputCls}
                    value={form.durationMins}
                    onChange={(e) =>
                      setForm({ ...form, durationMins: Number(e.target.value) })
                    }
                  />
                </label>
                <label className={labelCls}>
                  Age group
                  <input
                    className={inputCls}
                    value={form.ageGroup}
                    onChange={(e) => setForm({ ...form, ageGroup: e.target.value })}
                    placeholder="4–8 yrs"
                  />
                </label>
                <label className={labelCls}>
                  Seats
                  <input
                    type="number"
                    min={0}
                    className={inputCls}
                    value={form.seats}
                    onChange={(e) => setForm({ ...form, seats: Number(e.target.value) })}
                  />
                </label>
              </div>
              <label className={labelCls}>
                Host
                <input
                  className={inputCls}
                  value={form.host}
                  onChange={(e) => setForm({ ...form, host: e.target.value })}
                  placeholder="Ms. Ananya"
                />
              </label>
              <label className={labelCls}>
                Description
                <textarea
                  rows={3}
                  className={inputCls}
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="What will the cubs do in this session?"
                />
              </label>
              <label className={labelCls}>
                Registration link (optional)
                <input
                  type="url"
                  className={inputCls}
                  value={form.registrationLink}
                  onChange={(e) =>
                    setForm({ ...form, registrationLink: e.target.value })
                  }
                  placeholder="https://forms.gle/…"
                />
              </label>
            </div>
            {formError && (
              <p className="mt-3 rounded-xl bg-blush px-4 py-2 text-sm font-bold text-coral">
                {formError}
              </p>
            )}
            <div className="mt-5 flex items-center gap-2">
              <button
                type="submit"
                disabled={busy}
                className="rounded-full bg-coral px-6 py-2.5 font-display font-bold text-white shadow-pop hover:bg-teal disabled:opacity-60"
              >
                {busy ? "Saving…" : editing === "new" ? "Add session" : "Save changes"}
              </button>
              <button
                type="button"
                onClick={() => setEditing(null)}
                className="rounded-full bg-cream px-6 py-2.5 font-display font-bold"
              >
                Cancel
              </button>
              {editing !== "new" && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => onDelete(editing)}
                  className="ml-auto rounded-full bg-blush px-5 py-2.5 font-display font-bold text-coral hover:bg-coral hover:text-white"
                >
                  Delete
                </button>
              )}
            </div>
          </form>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className="fixed bottom-6 left-1/2 z-40 -translate-x-1/2 rounded-full bg-navy px-6 py-3 font-display font-bold text-cream shadow-card">
          {toast}
        </div>
      )}
    </div>
  );
}
