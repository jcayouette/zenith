export default function Placeholder({ title, note }: { title: string; note: string }) {
  return (
    <section className="rounded-3xl border border-dashed border-white/12 bg-panel/40 px-8 py-16">
      <h1 className="font-serif text-4xl text-ice">{title}</h1>
      <p className="mt-3 max-w-xl text-white/55">{note}</p>
      <p className="mt-6 text-sm text-white/35">Planned — see PLAN.md. Live and Settings are Phase 1.</p>
    </section>
  );
}
