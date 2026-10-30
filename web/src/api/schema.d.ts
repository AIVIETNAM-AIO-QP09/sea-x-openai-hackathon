// TEMPORARY hand-written schema following docs/dev-plan/08-api.md, in the same
// shape openapi-typescript emits. Replace by running `npm run gen:api` once the
// backend serves OpenAPI. App code must import types via src/api/types.ts only,
// so a rename on the backend side is fixed in one place.

export interface components {
  schemas: {
    HealthStatus: {
      status: 'ok' | 'degraded';
      db: 'ok' | 'error';
      ai: 'ok' | 'disabled' | 'error';
    };
    Source: { id: string; kind: string; label: string };
    Meta: {
      data_as_of?: string;
      computed_at?: string;
      compute_state?: components['schemas']['ComputeState'];
      confidence?: components['schemas']['Confidence'];
      sources?: components['schemas']['Source'][];
      cache_hit?: boolean;
    };
    ComputeState: 'fresh' | 'queued' | 'computing' | 'stale' | 'failed';
    Confidence: 'verified' | 'reference' | 'scenario';
    ApiErrorBody: {
      error: { code: string; message: string; details?: Record<string, unknown> };
    };
    Quantiles: { p10?: number; p50: number; p90?: number; mean?: number };
    ActionKind: 'continue' | 'pause' | 'reduce_budget' | 'schedule_hours' | 'pause_until_restock';
    ActionSpec: {
      kind: components['schemas']['ActionKind'];
      pct?: number | null;
      windows_local?: [number, number][] | null;
    };
    FreshnessSource: {
      source: string;
      as_of: string;
      status: 'fresh' | 'stale' | 'partial' | 'missing';
      lag_minutes?: number;
      threshold_minutes?: number;
      missing_skus?: number;
    };
    Freshness: { now: string; sources: components['schemas']['FreshnessSource'][] };
    SkuListItem: {
      sku: string;
      name: string;
      variant: string;
      stock_available: number;
      hours_of_cover: components['schemas']['Quantiles'];
      sold_today_units: number;
      deviation: 'on_track' | 'below_forecast' | 'above_forecast';
      campaign: { id: string; status: string } | null;
      recommendation: {
        recommendation_id: string;
        status: components['schemas']['RecommendationStatus'];
        best: components['schemas']['ActionSpec'];
        confidence: components['schemas']['Confidence'];
      } | null;
      open_alerts: number;
      priority_score: number;
      compute_state: components['schemas']['ComputeState'];
      computed_at: string;
    };
    RecommendationStatus: 'recommend' | 'undetermined' | 'none_meets_goal';
    ZoneBar: {
      axis_label: string;
      threshold: number;
      interval: [number, number, number];
      verdict: 'pause_better' | 'continue_better' | 'undetermined';
      alt_thresholds: { label: string; threshold: number }[];
    };
    FlipCondition: { factor: string; flip_at: number; text: string };
    Recommendation: {
      recommendation_id: string;
      campaign_id: string;
      status: components['schemas']['RecommendationStatus'];
      best: components['schemas']['ActionSpec'];
      runner_up: components['schemas']['ActionSpec'] | null;
      p_best_beats_runner_up: number;
      expected_gain_vnd: number;
      zone_bar: components['schemas']['ZoneBar'];
      flip_conditions: components['schemas']['FlipCondition'][];
      confidence: components['schemas']['Confidence'];
      reasons: string[];
      inputs_ref: {
        forecast_ids: string[];
        estimate_id: string;
        param_version: number;
        goal_id: string;
        data_as_of: string;
      };
      scenario_id?: string;
      created_at?: string;
      superseded_by?: string | null;
    };
    ScenarioResult: {
      action: components['schemas']['ActionSpec'];
      feasible: boolean;
      violations: string[];
      objective: components['schemas']['Quantiles'];
      contribution?: components['schemas']['Quantiles'];
      spend?: components['schemas']['Quantiles'];
      units_sold?: components['schemas']['Quantiles'];
      leftover_units?: components['schemas']['Quantiles'];
      leftover_value?: components['schemas']['Quantiles'];
      stockout_hour_p50?: string | null;
      per_sku?: unknown[];
    };
    ScenarioRun: {
      scenario_id: string;
      results: components['schemas']['ScenarioResult'][];
      recommendation: components['schemas']['Recommendation'];
    };
    Alert: {
      id: string;
      kind: string;
      severity: 'high' | 'medium' | 'low';
      target: { sku?: string; product?: string; campaign_id?: string };
      title: string;
      impact_vnd: number;
      raised_at: string;
      status: 'open' | 'acked' | 'snoozed' | 'resolved';
      group_key: string;
      investigation: unknown | null;
    };
    LiveStatus: {
      enabled: boolean;
      day: string;
      orders_until: string;
      ads_until: string;
      last_tick_at: string;
      replay_running: boolean;
    };
  };
}

export type paths = Record<string, never>;
