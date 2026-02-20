import { Timeline } from "@/components/timeline";

export default function Home() {
  return (
    <main className="min-h-screen bg-white">
      {/* Top nav */}
      <header className="sticky top-0 z-40 border-b border-neutral-100 bg-white/90 backdrop-blur-sm">
        <div className="mx-auto max-w-2xl px-4 h-14 flex items-center gap-3">
          <span className="text-base font-semibold text-neutral-900">
            Climbing Competition Tracker
          </span>
        </div>
      </header>

      {/* Timeline */}
      <div className="mx-auto max-w-2xl px-4 py-8">
        <Timeline />
      </div>
    </main>
  );
}
