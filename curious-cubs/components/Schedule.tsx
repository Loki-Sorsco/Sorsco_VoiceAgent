"use client";

import { useEffect, useState } from "react";
import type { WebinarSession } from "@/lib/types";

const REFRESH_MS = 30_000;

function formatDate(date: string): string {
  const d = new Date(`${date}T00:00:00`);
  return d.toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatTime(time: string): string {
  const [h, m] = time.split(":").map(Number);
  const d = new Date();
  d.setHours(h, m, 0, 0);
  return d.toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" });
}

const CARD_EMOJIS = ["🎨", "🔬", "📚", "🎭", "🧩", "🎵", "🌱", "🚀"];

export default function Schedule({ initial }: { initial: WebinarSession[] }) {
  const [sessions, setSessions] = useState<WebinarSession[]>(initial);

  // Keep the schedule in sync with the admin panel without a reload.
  useEffect(() => {
    const tick = async () => {
      try {
        const res = await fetch("/api/sessions", { cache: "no-store" });
        if (res.ok) {
          const data = await res.json();
          setSessions(data.sessions ?? []);
        }
      } catch {
        // offline / transient — keep showing what we have
      }
    };
    const id = setInterval(tick, REFRESH_MS);
    return () => clearInterval(id);
  }, []);

  const today = new Date().toISOString().slice(0, 10);
  const upcoming = sessions.filter((s) => s.date >= today);

  if (upcoming.length === 0) {
    return (
      <div className="rounded-3xl bg-white p-10 text-center shadow-card">
        <div className="mb-3 text-5xl">🗓️</div>
        <p className="font-display text-xl font-bold">
          New sessions are being planned!
        </p>
        <p className="mt-2 text-navy/70">
          Check back soon, or drop us a message below and we&apos;ll let you know
          when the next webinar goes live.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
      {upcoming.map((s, i) => (
        <article
          key={s.id}
          className="flex flex-col rounded-3xl bg-white p-6 shadow-card transition-transform hover:-translate-y-1"
        >
          <div className="mb-4 flex items-center justify-between">
            <span className="text-4xl">{CARD_EMOJIS[i % CARD_EMOJIS.length]}</span>
            {s.ageGroup && (
              <span className="rounded-full bg-blush px-3 py-1 text-sm font-bold text-coral">
                Ages {s.ageGroup}
              </span>
            )}
          </div>
          <h3 className="font-display text-xl font-bold">{s.title}</h3>
          {s.description && (
            <p className="mt-2 flex-1 text-sm text-navy/70">{s.description}</p>
          )}
          <div className="mt-4 space-y-1 text-sm font-semibold text-navy/80">
            <p>📅 {formatDate(s.date)}</p>
            <p>
              ⏰ {formatTime(s.time)} · {s.durationMins} mins
            </p>
            {s.host && <p>🧑‍🏫 {s.host}</p>}
            {s.seats > 0 && <p>🪑 {s.seats} seats</p>}
          </div>
          <a
            href={s.registrationLink || "#contact"}
            target={s.registrationLink ? "_blank" : undefined}
            rel={s.registrationLink ? "noopener noreferrer" : undefined}
            className="mt-5 rounded-full bg-coral px-5 py-2.5 text-center font-display font-bold text-white shadow-pop transition-colors hover:bg-teal"
          >
            Book a spot
          </a>
        </article>
      ))}
    </div>
  );
}
