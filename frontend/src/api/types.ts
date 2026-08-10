export interface StatusPayload {
  status: "STOPPED" | "RUNNING" | "PAUSED" | "DAILY_HALT" | "KILLED";
  status_reason: string;
  testnet: boolean;
  has_keys: boolean;
  started_at: string | null;
  equity: number;
  day_start_equity: number;
  peak_equity: number;
  active_symbols: string[];
  invalid_symbols: string[];
  scanner: ScannedSymbol[];
  market_stream_age_secs: number | null;
}

export interface ScannedSymbol {
  symbol: string;
  change_pct: number;
  quote_volume: number;
  price: number;
}

export interface Account {
  equity: number;
  day_start_equity: number;
  day_pnl: number;
  realized_pnl_today: number;
  unrealized_pnl: number;
  peak_equity: number;
  balances: Record<string, { free: number; locked: number }>;
  prices: Record<string, number>;
}

export interface Position {
  id: number;
  symbol: string;
  strategy: string;
  qty: number;
  avg_entry: number;
  mark: number;
  value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  sl: number | null;
  tp: number | null;
  protected: boolean;
  trailing: boolean;
  grid_level: number | null;
  opened_at: string;
  entry_reason: string;
}

export interface Trade {
  id: number;
  symbol: string;
  strategy: string;
  qty: number;
  entry_price: number;
  exit_price: number;
  pnl: number;
  pnl_pct: number;
  fees: number;
  entry_reason: string;
  exit_reason: string;
  opened_at: string | null;
  closed_at: string | null;
}

export interface ParamSpec {
  name: string;
  label: string;
  type: "int" | "float" | "bool" | "select" | "time";
  default: unknown;
  min: number | null;
  max: number | null;
  step: number | null;
  choices: string[];
  help: string;
}

export interface StrategyInfo {
  id: string;
  name: string;
  description: string;
  kind: "candle" | "grid" | "schedule";
  enabled: boolean;
  params: Record<string, unknown>;
  symbols: string[];
  use_scanner: boolean;
  note: string;
  param_specs: ParamSpec[];
  effective_symbols: string[];
  adaptive?: {
    n: number;
    win_rate_pct: number;
    profit_factor: number | null;
    consecutive_losses: number;
    size_multiplier: number;
    paused: boolean;
    reason: string;
  };
}

export interface RiskUsage {
  daily_loss: { used_pct: number; limit_pct: number };
  drawdown: { used_pct: number; limit_pct: number; kill_switch_enabled: boolean };
  open_positions: { used: number; limit: number };
  total_exposure: { used_pct: number; limit_pct: number };
  per_asset: { symbol: string; used_pct: number; limit_pct: number }[];
}

export interface BacktestSummary {
  id: number;
  created_at: string;
  label: string;
  status: "RUNNING" | "DONE" | "ERROR";
  error: string;
  strategy_id: string;
  symbol: string;
  timeframe: string;
  start: string;
  end: string;
  initial_equity: number;
  fee_bps: number;
  slippage_bps: number;
  params: Record<string, unknown>;
  metrics: Record<string, any>;
}

export interface BacktestDetail extends BacktestSummary {
  risk: Record<string, unknown>;
  equity_curve: [number, number][];
  trades: any[];
}

export interface WsEvent {
  type: string;
  ts?: string;
  data: any;
}
