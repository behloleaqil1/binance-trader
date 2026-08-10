import { useState } from "react";
import { useStore } from "../store/useStore";

const FILTERS = ["all", "trade", "signal", "order", "risk", "error"] as const;

export function SignalsFeed() {
  const feed = useStore((s) => s.feed);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const items = feed.filter((f) => filter === "all" || f.kind === filter);
  return (
    <div>
      <div className="chips" style={{ marginBottom: 8 }}>
        {FILTERS.map((f) => (
          <button key={f} className="chip" onClick={() => setFilter(f)}
                  style={filter === f ? { borderColor: "var(--s1)", color: "var(--ink)" } : {}}>
            {f}
          </button>
        ))}
      </div>
      {!items.length && <div className="empty">Nothing yet — events stream in live while the bot runs</div>}
      <div className="feed">
        {items.map((f) => (
          <div key={f.id} className={`feed-item ${f.dim ? "hold" : ""}`}>
            <span className="when">{new Date(f.ts).toLocaleTimeString("en-GB")}</span>
            {f.text}
          </div>
        ))}
      </div>
    </div>
  );
}
