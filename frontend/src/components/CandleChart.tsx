import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickData, ColorType, IChartApi, IPriceLine, ISeriesApi, LineStyle,
  UTCTimestamp, createChart,
} from "lightweight-charts";
import { api } from "../api/client";
import { useStore } from "../store/useStore";
import type { Position } from "../api/types";

interface Kline { open_time: number; open: number; high: number; low: number; close: number; volume: number; }

const CHART_OPTS = {
  layout: {
    background: { type: ColorType.Solid, color: "transparent" },
    textColor: "#898781",
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif",
  },
  grid: { vertLines: { color: "#2c2c2a" }, horzLines: { color: "#2c2c2a" } },
  rightPriceScale: { borderColor: "#383835" },
  timeScale: { borderColor: "#383835", timeVisible: true, secondsVisible: false },
} as const;

/* Up-candles are HOLLOW, down solid — direction never rides on hue alone
   (green/red is the classic deutan confusion pair). */
const CANDLE_OPTS = {
  upColor: "rgba(0,0,0,0)", borderUpColor: "#0ca30c", wickUpColor: "#0ca30c",
  downColor: "#d03b3b", borderDownColor: "#d03b3b", wickDownColor: "#d03b3b",
  borderVisible: true,
} as const;

function emaSeries(closes: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = [];
  let prev: number | null = null;
  closes.forEach((c, i) => {
    prev = prev === null ? c : c * k + prev * (1 - k);
    out.push(i < period - 1 ? null : prev);
  });
  return out;
}

function bollinger(closes: number[], period = 20, mult = 2) {
  const mid: (number | null)[] = [], up: (number | null)[] = [], lo: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) { mid.push(null); up.push(null); lo.push(null); continue; }
    const w = closes.slice(i - period + 1, i + 1);
    const m = w.reduce((a, b) => a + b, 0) / period;
    const sd = Math.sqrt(w.reduce((a, b) => a + (b - m) ** 2, 0) / period);
    mid.push(m); up.push(m + mult * sd); lo.push(m - mult * sd);
  }
  return { mid, up, lo };
}

export function CandleChart({ symbol, tf, positions }: {
  symbol: string; tf: string; positions?: Position[];
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const overlayRefs = useRef<ISeriesApi<"Line">[]>([]);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const dataRef = useRef<Kline[]>([]);
  const [showEma, setShowEma] = useState(true);
  const [showBb, setShowBb] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lastCandle = useStore((s) => s.lastCandle);

  /* create chart once */
  useEffect(() => {
    if (!boxRef.current) return;
    const chart = createChart(boxRef.current, { ...CHART_OPTS, height: 340, autoSize: true });
    chartRef.current = chart;
    candlesRef.current = chart.addCandlestickSeries(CANDLE_OPTS);
    return () => {
      chart.remove();
      chartRef.current = null;
      candlesRef.current = null;
      // Series refs die with the chart — a remount must not try to remove
      // them from the NEW chart instance (throws "Value is undefined").
      overlayRefs.current = [];
      priceLinesRef.current = [];
    };
  }, []);

  const redrawOverlays = () => {
    const chart = chartRef.current;
    if (!chart) return;
    overlayRefs.current.forEach((s) => {
      try { chart.removeSeries(s); } catch { /* stale ref from a removed chart */ }
    });
    overlayRefs.current = [];
    const rows = dataRef.current;
    if (!rows.length) return;
    const closes = rows.map((r) => r.close);
    const times = rows.map((r) => (r.open_time / 1000) as UTCTimestamp);
    const addLine = (vals: (number | null)[], color: string, width: 1 | 2, title: string, style?: LineStyle) => {
      const s = chart.addLineSeries({
        color, lineWidth: width, priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false, title, lineStyle: style,
      });
      s.setData(vals.map((v, i) => v === null ? null : { time: times[i], value: v })
        .filter(Boolean) as { time: UTCTimestamp; value: number }[]);
      overlayRefs.current.push(s);
    };
    if (showEma) {
      addLine(emaSeries(closes, 20), "#3987e5", 2, "EMA 20");
      addLine(emaSeries(closes, 50), "#d95926", 2, "EMA 50");
    }
    if (showBb) {
      const { mid, up, lo } = bollinger(closes);
      addLine(mid, "#898781", 1, "BB mid", LineStyle.Dotted);
      addLine(up, "#898781", 1, "BB up", LineStyle.Dotted);
      addLine(lo, "#898781", 1, "BB low", LineStyle.Dotted);
    }
  };

  /* (re)load history when symbol/tf changes */
  useEffect(() => {
    let dead = false;
    setError(null);
    api<Kline[]>(`/klines?symbol=${symbol}&tf=${tf}&limit=300`)
      .then((rows) => {
        if (dead || !candlesRef.current) return;
        dataRef.current = rows;
        candlesRef.current.setData(rows.map((r) => ({
          time: (r.open_time / 1000) as UTCTimestamp,
          open: r.open, high: r.high, low: r.low, close: r.close,
        }) as CandlestickData));
        chartRef.current?.timeScale().fitContent();
        redrawOverlays();
      })
      .catch((e: Error) => !dead && setError(e.message));
    return () => { dead = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, tf]);

  useEffect(() => { redrawOverlays(); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [showEma, showBb]);

  /* live candle updates from the engine's stream */
  useEffect(() => {
    if (!lastCandle || lastCandle.symbol !== symbol || lastCandle.tf !== tf) return;
    const rows = dataRef.current;
    const row: Kline = { open_time: lastCandle.t, open: lastCandle.o, high: lastCandle.h,
                         low: lastCandle.l, close: lastCandle.c, volume: lastCandle.v };
    if (rows.length && rows[rows.length - 1].open_time === row.open_time) rows[rows.length - 1] = row;
    else rows.push(row);
    candlesRef.current?.update({
      time: (row.open_time / 1000) as UTCTimestamp,
      open: row.open, high: row.high, low: row.low, close: row.close,
    });
    redrawOverlays();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastCandle]);

  /* SL/TP price lines for open positions on this symbol */
  const symPositions = useMemo(
    () => (positions ?? []).filter((p) => p.symbol === symbol), [positions, symbol]);
  useEffect(() => {
    const series = candlesRef.current;
    if (!series) return;
    priceLinesRef.current.forEach((pl) => series.removePriceLine(pl));
    priceLinesRef.current = [];
    for (const p of symPositions) {
      if (p.sl) priceLinesRef.current.push(series.createPriceLine({
        price: p.sl, color: "#d03b3b", lineStyle: LineStyle.Dashed, lineWidth: 1,
        title: `SL ${p.strategy}` }));
      if (p.tp) priceLinesRef.current.push(series.createPriceLine({
        price: p.tp, color: "#0ca30c", lineStyle: LineStyle.Dashed, lineWidth: 1,
        title: `TP ${p.strategy}` }));
      priceLinesRef.current.push(series.createPriceLine({
        price: p.avg_entry, color: "#898781", lineStyle: LineStyle.Dotted, lineWidth: 1,
        title: "entry" }));
    }
  }, [symPositions]);

  return (
    <div>
      <div className="chart-controls">
        <label className="check-row" style={{ margin: 0 }}>
          <input type="checkbox" checked={showEma} onChange={(e) => setShowEma(e.target.checked)} />
          EMA 20/50
        </label>
        <label className="check-row" style={{ margin: 0 }}>
          <input type="checkbox" checked={showBb} onChange={(e) => setShowBb(e.target.checked)} />
          Bollinger 20·2
        </label>
        {showEma && (
          <span className="legend" style={{ margin: 0 }}>
            <span><span className="key" style={{ background: "#3987e5" }} />EMA 20</span>
            <span><span className="key" style={{ background: "#d95926" }} />EMA 50</span>
          </span>
        )}
      </div>
      {error && <div className="banner banner-info">chart data unavailable: {error}</div>}
      <div ref={boxRef} className="chart-box" style={{ height: 340 }} />
    </div>
  );
}
