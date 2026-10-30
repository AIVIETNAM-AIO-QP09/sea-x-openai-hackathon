// TEMPORARY hand-written schema following docs/dev-plan/08-api.md, in the same
// shape openapi-typescript emits. Replace by running `npm run gen:api` once the
// backend serves OpenAPI. App code must import types via src/api/types.ts only,
// so a rename on the backend side is fixed in one place.

export interface components {
  schemas: {
    // Matches backend app/api/health.py `Health`; returned inside Envelope.
    HealthStatus: {
      status: 'ok' | 'degraded';
      db: 'ok' | 'error';
      ai: 'ok' | 'disabled';
      ai_mode: 'live' | 'record' | 'replay';
      app_env: string;
      version: string;
      message: string;
    };
    // `data_as_of`, `tool`, `href` are optional additions proposed by web M3
    // (docs/quyet-dinh/M3-web.md) so a CitationChip can say where a number came from.
    Source: {
      id: string;
      kind: string;
      label: string;
      data_as_of?: string | null;
      tool?: string | null;
      href?: string | null;
    };
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
    ZoneVerdict: 'pause_better' | 'continue_better' | 'undetermined';
    AltThreshold: { label: string; threshold: number };
    // Body of POST /scenarios/breakeven (08 §3.8, ECO-04). Also embedded as the
    // optional `ZoneBar.inputs` so the browser can redraw the bar instantly.
    BreakevenRequest: {
      units_left: number;
      hours_left: number;
      contribution_per_unit_vnd: number;
      spend_per_hour_vnd: number;
      rate_continue_per_hour: number;
      pause_rate_interval: [number, number, number];
      leftover_value_per_unit_vnd: number;
    };
    BreakevenResponse: {
      zone_bar: components['schemas']['ZoneBar'] | null;
      flip_leftover_value_vnd: number | null;
    };
    ZoneBar: {
      axis_label: string;
      threshold: number;
      interval: [number, number, number];
      verdict: components['schemas']['ZoneVerdict'];
      alt_thresholds: components['schemas']['AltThreshold'][];
      /** Proposed addition (M3-web.md): closed-form inputs behind this bar. */
      inputs?: components['schemas']['BreakevenRequest'] | null;
    };
    FlipCondition: { factor: string; flip_at: number; text: string };
    InputsRef: {
      forecast_ids: string[];
      estimate_id: string;
      param_version: number;
      goal_id: string;
      data_as_of: string;
    };
    Recommendation: {
      recommendation_id: string;
      campaign_id: string;
      status: components['schemas']['RecommendationStatus'];
      best: components['schemas']['ActionSpec'] | null;
      runner_up: components['schemas']['ActionSpec'] | null;
      p_best_beats_runner_up: number | null;
      expected_gain_vnd: number | null;
      zone_bar: components['schemas']['ZoneBar'] | null;
      flip_conditions: components['schemas']['FlipCondition'][];
      confidence: components['schemas']['Confidence'];
      reasons: string[];
      /** Proposed addition (M3-web.md): one source per reason, same order. */
      reason_sources?: (components['schemas']['Source'] | null)[];
      inputs_ref: components['schemas']['InputsRef'];
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
    SimRequest: {
      campaign_id: string;
      start: string;
      horizon_hours?: number | null;
      goal_id: string;
      actions?: components['schemas']['ActionSpec'][] | null;
      param_overrides?: Record<string, number>;
      samples?: number;
      seed?: number;
    };
    ScenarioRun: {
      scenario_id: string;
      /** Proposed addition (M3-web.md): echo of the SimRequest behind this run. */
      request?: components['schemas']['SimRequest'];
      results: components['schemas']['ScenarioResult'][];
      recommendation: components['schemas']['Recommendation'];
    };
    DecisionCreate: {
      target: { campaign_id?: string; sku?: string };
      action: components['schemas']['ActionSpec'];
      scenario_id: string;
      recommendation_id: string;
      rationale: string;
      override_of_recommendation: boolean;
    };
    DecisionCreated: { id: string; state: string; created_by: string; input_hash: string };
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
