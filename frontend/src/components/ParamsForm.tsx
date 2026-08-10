import type { ParamSpec } from "../api/types";

/** Schema-driven form: renders whatever param_specs the backend declares,
 *  so new strategy parameters appear in the UI with zero frontend changes. */
export function ParamsForm({ specs, values, onChange }: {
  specs: ParamSpec[];
  values: Record<string, unknown>;
  onChange: (name: string, value: unknown) => void;
}) {
  return (
    <div className="field-row">
      {specs.map((p) => {
        const v = values[p.name] ?? p.default;
        if (p.type === "bool") {
          return (
            <label key={p.name} className="check-row" title={p.help}>
              <input type="checkbox" checked={!!v}
                     onChange={(e) => onChange(p.name, e.target.checked)} />
              {p.label}
            </label>
          );
        }
        if (p.type === "select") {
          return (
            <label key={p.name} className="field" title={p.help}>
              <span>{p.label}</span>
              <select value={String(v)} onChange={(e) => onChange(p.name, e.target.value)}>
                {p.choices.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              {p.help && <small>{p.help}</small>}
            </label>
          );
        }
        if (p.type === "time") {
          return (
            <label key={p.name} className="field" title={p.help}>
              <span>{p.label}</span>
              <input type="time" value={String(v)}
                     onChange={(e) => onChange(p.name, e.target.value)} />
              {p.help && <small>{p.help}</small>}
            </label>
          );
        }
        return (
          <label key={p.name} className="field" title={p.help}>
            <span>{p.label}</span>
            <input
              type="number"
              value={v === null || v === undefined ? "" : Number(v)}
              min={p.min ?? undefined}
              max={p.max ?? undefined}
              step={p.step ?? (p.type === "int" ? 1 : "any")}
              onChange={(e) => {
                const raw = e.target.value;
                if (raw === "") return onChange(p.name, p.default);
                onChange(p.name, p.type === "int" ? parseInt(raw, 10) : parseFloat(raw));
              }}
            />
            {p.help && <small>{p.help}</small>}
          </label>
        );
      })}
    </div>
  );
}
