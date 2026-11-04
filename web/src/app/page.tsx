import { ApiStatus } from "./api-status";

export default function Home() {
  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-card border border-border bg-surface p-6">
        <h1 className="text-2xl font-semibold text-accent">Sukat</h1>
        <p className="mt-1 text-sm text-muted">Phase 0 setup check</p>
        <div className="mt-4">
          <ApiStatus />
        </div>
      </div>
    </main>
  );
}
