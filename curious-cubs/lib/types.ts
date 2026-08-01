export type WebinarSession = {
  id: string;
  title: string;
  date: string; // YYYY-MM-DD
  time: string; // HH:MM (24h)
  durationMins: number;
  ageGroup: string;
  host: string;
  seats: number;
  description: string;
  registrationLink: string;
  createdAt: string;
  updatedAt: string;
};

export type ContactSubmission = {
  id: string;
  name: string;
  email: string;
  phone: string;
  message: string;
  emailed: boolean;
  createdAt: string;
};

export type SessionInput = Omit<WebinarSession, "id" | "createdAt" | "updatedAt">;

export function validateSessionInput(body: unknown): SessionInput | null {
  if (typeof body !== "object" || body === null) return null;
  const b = body as Record<string, unknown>;
  const title = typeof b.title === "string" ? b.title.trim() : "";
  const date = typeof b.date === "string" ? b.date.trim() : "";
  const time = typeof b.time === "string" ? b.time.trim() : "";
  if (!title || !/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time)) {
    return null;
  }
  return {
    title,
    date,
    time,
    durationMins: Number(b.durationMins) > 0 ? Math.floor(Number(b.durationMins)) : 60,
    ageGroup: typeof b.ageGroup === "string" ? b.ageGroup.trim() : "",
    host: typeof b.host === "string" ? b.host.trim() : "",
    seats: Number(b.seats) >= 0 ? Math.floor(Number(b.seats)) : 0,
    description: typeof b.description === "string" ? b.description.trim() : "",
    registrationLink: typeof b.registrationLink === "string" ? b.registrationLink.trim() : "",
  };
}
