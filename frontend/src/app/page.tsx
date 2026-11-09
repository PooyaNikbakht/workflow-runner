import { RunHistory } from "@/components/RunHistory";
import { StartPanel } from "@/components/StartPanel";

const STEPS = [
  {
    title: "Pick a job",
    text: "Reply to a new sales lead, or sort out a customer support ticket.",
  },
  {
    title: "Pick a sample",
    text: "The details fill in for you. They are made-up customers, and you can edit anything.",
  },
  {
    title: "Start the run",
    text: "The AI works through the steps one by one, and you watch each one finish live.",
  },
  {
    title: "Approve, edit or reject",
    text: "The AI only drafts. Its reply waits for you, and nothing is sent until you approve it.",
  },
];

export default function Home() {
  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-10 sm:px-6 sm:py-14">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
        Let AI do the busywork, with a person in charge
      </h1>
      <p className="mt-3 max-w-2xl text-muted">
        This demo shows how a business can hand repetitive work, like answering
        leads or support tickets, to AI without losing control: the AI drafts, a
        person checks, and only approved replies go out.
      </p>

      <h2 className="mt-8 text-sm font-semibold">How to try it</h2>
      <ol className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {STEPS.map((s, i) => (
          <li
            key={s.title}
            className="rounded-lg border border-line bg-surface p-4"
          >
            <span
              aria-hidden="true"
              className="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-ink"
            >
              {i + 1}
            </span>
            <p className="mt-3 font-medium">{s.title}</p>
            <p className="mt-1 text-sm text-muted">{s.text}</p>
          </li>
        ))}
      </ol>
      <p className="mt-4 max-w-2xl text-sm text-muted">
        Approved replies go to the{" "}
        <a
          href="/receiver"
          className="text-accent underline underline-offset-4"
        >
          test inbox
        </a>
        , never to a real person. Under the hood: each step is a job on a queue
        run by a separate worker, failed steps retry on their own, and the
        AI&apos;s output is checked before anyone sees it.
      </p>

      <div className="mt-8">
        <StartPanel />
      </div>
      <RunHistory />
    </div>
  );
}
