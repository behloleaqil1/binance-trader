import { useEffect, useRef } from "react";
import {
  ColorType, IChartApi, LineData, UTCTimestamp, createChart,
} from "lightweight-charts";
import { fmtMoney } from "../api/client";

export interface EquitySeries {
  label: string;
  color: string;                 // categorical slots 1–3 only (validated set)
  points: [number, number][];    // [ts_ms, value]
}

export function EquityChart({ series, height = 260 }: {
  series: EquitySeries[]; height?: number;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!boxRef.current) return;
    const chart = createChart(boxRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#898781",
        fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
      },
      grid: { vertLines: { color: "#2c2c2a" }, horzLines: { color: "#2c2c2a" } },
      rightPriceScale: { borderColor: "#383835" },
      timeScale: { borderColor: "#383835", timeVisible: true, secondsVisible: false },
      height, autoSize: true,
    });
    chartRef.current = chart;
    return () => { chart.remove(); chartRef.current = null; };
  }, [height]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    // simplest correct approach for ≤3 series: rebuild series on data change
    const existing = (chart as any).__series as any[] | undefined;
    existing?.forEach((s) => chart.removeSeries(s));
    const created: any[] = [];
    series.forEach((s, idx) => {
      const dedup = new Map<number, number>();
      for (const [ts, v] of s.points) dedup.set(Math.floor(ts / 1000), v);
      const data: LineData[] = [...dedup.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([t, v]) => ({ time: t as UTCTimestamp, value: v }));
      if (series.length === 1) {
        const area = chart.addAreaSeries({
          lineColor: s.color, lineWidth: 2,
          topColor: `${s.color}44`, bottomColor: `${s.color}05`,
          priceLineVisible: false, title: "",
        });
        area.setData(data);
        created.push(area);
      } else {
        const line = chart.addLineSeries({
          color: s.color, lineWidth: 2, priceLineVisible: false, title: s.label,
        });
        line.setData(data);
        created.push(line);
      }
    });
    (chart as any).__series = created;
    chart.timeScale().fitContent();
  }, [series]);

  const showLegend = series.length > 1;
  return (
    <div>
      {showLegend && (
        <div className="legend">
          {series.map((s) => (
            <span key={s.label}><span className="key" style={{ background: s.color }} />{s.label}</span>
          ))}
        </div>
      )}
      <div ref={boxRef} className="chart-box" style={{ height }} />
      <details className="data-table">
        <summary>Data table</summary>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Time</th>{series.map((s) => <th className="num" key={s.label}>{s.label || "equity"}</th>)}</tr>
            </thead>
            <tbody>
              {(series[0]?.points.slice(-12) ?? []).map(([ts], i) => (
                <tr key={ts}>
                  <td>{new Date(ts).toLocaleString("en-GB", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</td>
                  {series.map((s) => {
                    const pt = s.points.slice(-12)[i];
                    return <td className="num" key={s.label}>{pt ? fmtMoney(pt[1]) : "—"}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
