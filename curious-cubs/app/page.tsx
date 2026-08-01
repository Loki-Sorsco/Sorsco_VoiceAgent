import Schedule from "@/components/Schedule";
import ContactForm from "@/components/ContactForm";
import { getSessions } from "@/lib/store";

export const dynamic = "force-dynamic";

const HIGHLIGHTS = [
  {
    emoji: "🎨",
    title: "Hands-on & fun",
    text: "Every session is packed with activities kids do along with the host — no passive watching.",
  },
  {
    emoji: "👩‍🏫",
    title: "Expert hosts",
    text: "Educators who know how to keep little minds curious, engaged and giggling.",
  },
  {
    emoji: "💻",
    title: "Join from home",
    text: "All you need is a laptop or tablet. Links arrive by email after you book.",
  },
  {
    emoji: "🏅",
    title: "Certificates",
    text: "Every cub gets a shiny participation certificate to stick on the fridge.",
  },
];

export default async function Home() {
  const sessions = await getSessions();

  return (
    <main>
      {/* Header */}
      <header className="sticky top-0 z-20 border-b border-navy/5 bg-cream/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <a href="#" className="font-display text-2xl font-extrabold text-coral">
            🐻 Curious Cubs
          </a>
          <nav className="flex items-center gap-2 sm:gap-6 font-bold text-navy/80">
            <a href="#schedule" className="px-2 py-1 hover:text-coral">
              Schedule
            </a>
            <a href="#why" className="hidden px-2 py-1 hover:text-coral sm:block">
              Why us
            </a>
            <a
              href="#contact"
              className="rounded-full bg-sunshine px-4 py-2 font-display shadow-pop"
            >
              Contact us
            </a>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-4 pb-16 pt-14 text-center sm:pt-20">
        <p className="mx-auto mb-4 w-fit rounded-full bg-blush px-4 py-1.5 font-bold text-coral">
          ✨ Live online webinars for kids
        </p>
        <h1 className="mx-auto max-w-3xl font-display text-4xl font-extrabold leading-tight sm:text-6xl">
          Where little minds go on <span className="text-coral">big adventures</span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg font-semibold text-navy/70">
          Art, science, stories and more — live, interactive sessions your cubs
          will beg to come back to. Pick a date from the calendar and join the fun!
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
          <a
            href="#schedule"
            className="rounded-full bg-coral px-8 py-3.5 font-display text-lg font-bold text-white shadow-pop transition-colors hover:bg-teal"
          >
            See upcoming sessions
          </a>
          <a
            href="#contact"
            className="rounded-full border-2 border-navy/15 bg-white px-8 py-3.5 font-display text-lg font-bold text-navy transition-colors hover:border-teal hover:text-teal"
          >
            Ask a question
          </a>
        </div>
      </section>

      {/* Schedule — kept in sync with the admin panel */}
      <section id="schedule" className="bg-white/60 py-16">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-center font-display text-3xl font-extrabold sm:text-4xl">
            📅 Upcoming webinars
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-center font-semibold text-navy/70">
            Fresh sessions are added by our team all the time — this calendar
            updates live.
          </p>
          <div className="mt-10">
            <Schedule initial={sessions} />
          </div>
        </div>
      </section>

      {/* Why us */}
      <section id="why" className="py-16">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-center font-display text-3xl font-extrabold sm:text-4xl">
            Why cubs love us 🧡
          </h2>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {HIGHLIGHTS.map((h) => (
              <div key={h.title} className="rounded-3xl bg-white p-6 text-center shadow-card">
                <div className="text-5xl">{h.emoji}</div>
                <h3 className="mt-3 font-display text-lg font-bold">{h.title}</h3>
                <p className="mt-2 text-sm font-semibold text-navy/70">{h.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Contact */}
      <section id="contact" className="bg-navy py-16 text-cream">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 lg:grid-cols-2 lg:items-center">
          <div>
            <h2 className="font-display text-3xl font-extrabold sm:text-4xl">
              Say hello! 👋
            </h2>
            <p className="mt-4 max-w-md text-lg font-semibold text-cream/80">
              Questions about a session, group bookings for schools, or ideas for
              a new webinar? Drop us a note — it lands straight in our inbox and
              we reply within a day.
            </p>
            <p className="mt-6 font-bold text-sunshine">✉️ dev@sorsco.in</p>
          </div>
          <div className="text-navy">
            <ContactForm />
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-navy pb-8 text-center text-sm font-semibold text-cream/60">
        <div className="mx-auto max-w-6xl border-t border-cream/10 px-4 pt-6">
          © {new Date().getFullYear()} Curious Cubs · Made with 🧡 for curious little minds
        </div>
      </footer>
    </main>
  );
}
