// Pure helpers for the Compare screen (09 §2.3). No React here so they are easy to test.
import type {
  ActionSpec,
  FlipCondition,
  Recommendation,
  ScenarioResult,
  ScenarioRun,
  SimRequest,
  Source,
  ZoneBar,
} from '../../api/types';
import { computeZoneBar } from '../../lib/breakeven';
import { formatPct, formatVndMillions } from '../../lib/format';
import { pctOf, viText } from '../../lib/i18n';
import type { Citation } from '../../components/CitationChip';

const t = viText.compare;

/** Wireframe order: Tiếp tục, Pause, Giảm %, Chỉ khung giờ, Pause tới khi hàng về. */
const KIND_ORDER: ActionSpec['kind'][] = ['continue', 'pause', 'reduce_budget', 'schedule_hours', 'pause_until_restock'];

export function actionKey(a: Pick<ActionSpec, 'kind' | 'pct' | 'windows_local'>): string {
  const pct = a.pct != null ? pctOf(a.pct) : '';
  const win = a.windows_local?.map(([s, e]) => `${s}-${e}`).join(',') ?? '';
  return `${a.kind}|${pct}|${win}`;
}

export function sameAction(a: ActionSpec | null | undefined, b: ActionSpec | null | undefined): boolean {
  if (!a || !b) return false;
  return actionKey(a) === actionKey(b);
}

export function orderResults(results: ScenarioResult[]): ScenarioResult[] {
  return results
    .map((r, i) => ({ r, i }))
    .sort((x, y) => KIND_ORDER.indexOf(x.r.action.kind) - KIND_ORDER.indexOf(y.r.action.kind) || x.i - y.i)
    .map(({ r }) => r);
}

export function violationLabel(code: string): string {
  return t.violation[code] ?? t.violationFallback(code);
}

/** Expected objective: mean when the API sends it, otherwise p50. */
export function expectedObjective(r: ScenarioResult): number {
  return r.objective.mean ?? r.objective.p50;
}

function lower(a: ActionSpec): string {
  return t.lowerCase(viText.action(a));
}

/** Tier-1 sentence readable in 3 seconds. null for none_meets_goal (tier 1 is replaced). */
export function headline(rec: Recommendation): string | null {
  if (rec.status === 'none_meets_goal' || !rec.best) return null;
  const best = viText.action(rec.best);
  if (rec.status === 'undetermined' && rec.runner_up) {
    const prob = rec.p_best_beats_runner_up != null ? formatPct(rec.p_best_beats_runner_up) : '—';
    return t.headline.undetermined(lower(rec.best), lower(rec.runner_up), prob);
  }
  if (rec.runner_up && rec.expected_gain_vnd != null) {
    return t.headline.recommend(best, lower(rec.runner_up), formatVndMillions(rec.expected_gain_vnd, 'long'));
  }
  return t.headline.recommendNoRunner(best);
}

/** 05 §7: best is schedule_hours / reduce_budget → "Phương án tốt hơn cả hai: …". */
export function betterThanBothLine(rec: Recommendation): string | null {
  if (!rec.best || rec.status === 'none_meets_goal') return null;
  if (rec.best.kind !== 'schedule_hours' && rec.best.kind !== 'reduce_budget') return null;
  return t.betterThanBoth(viText.action(rec.best));
}

/** Pause wins on the bar but is blocked by the flash-sale commitment. */
export function pauseBlockedLine(bar: ZoneBar | null, results: ScenarioResult[]): string | null {
  if (!bar || bar.verdict !== 'pause_better') return null;
  const pause = results.find((r) => r.action.kind === 'pause');
  return pause && !pause.feasible && pause.violations.includes('campaign_must_run') ? t.pauseBlocked : null;
}

// ---------------------------------------------------------------------------
// What-if sliders

export type WhatIf = {
  /** Leftover value V (đ/sp); null = untouched (server default). */
  leftoverValue: number | null;
  /** restock_delay_days; 0 = on schedule, negative = earlier. */
  restockDelayDays: number;
};

export const BASE_WHAT_IF: WhatIf = { leftoverValue: null, restockDelayDays: 0 };

export function isWhatIfActive(w: WhatIf): boolean {
  return w.leftoverValue !== null || w.restockDelayDays !== 0;
}

export function whatIfKey(w: WhatIf): string {
  return `${w.leftoverValue ?? ''}|${w.restockDelayDays}`;
}

/** Parameter keys from the 05 §3 catalogue. */
export function paramOverrides(w: WhatIf): Record<string, number> {
  const out: Record<string, number> = {};
  if (w.leftoverValue !== null) out.leftover_value_per_unit = w.leftoverValue;
  if (w.restockDelayDays !== 0) out.restock_delay_days = w.restockDelayDays;
  return out;
}

function nextHourIso(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  if (d.getUTCMinutes() !== 0 || d.getUTCSeconds() !== 0) {
    d.setUTCMinutes(0, 0, 0);
    d.setUTCHours(d.getUTCHours() + 1);
  }
  return d.toISOString();
}

/** SimRequest for a slider re-run; reuses the run's own request when the API echoes it. */
export function buildSimRequest(run: ScenarioRun | undefined, rec: Recommendation, w: WhatIf, samples: number): SimRequest {
  const base: SimRequest = run?.request ?? {
    campaign_id: rec.campaign_id,
    start: nextHourIso(rec.inputs_ref.data_as_of),
    horizon_hours: null,
    goal_id: rec.inputs_ref.goal_id,
  };
  return {
    ...base,
    actions: null,
    param_overrides: { ...(base.param_overrides ?? {}), ...paramOverrides(w) },
    samples,
    seed: base.seed ?? 20261111,
  };
}

export type LocalBar = { bar: ZoneBar | null; estimated: boolean };

/**
 * Instant browser estimate of the bar for the current leftover value (09 §2.3:
 * < 100 ms), using the closed form when the API supplies `zone_bar.inputs`.
 */
export function localZoneBar(rec: Recommendation, w: WhatIf): LocalBar {
  const base = rec.zone_bar;
  const inputs = base?.inputs;
  if (w.leftoverValue === null || !inputs) return { bar: base, estimated: false };
  const baselineV = inputs.leftover_value_per_unit_vnd;
  if (w.leftoverValue === baselineV) return { bar: base, estimated: false };
  const alts = [...new Set([baselineV, 20_000])];
  const res = computeZoneBar({ ...inputs, leftover_value_per_unit_vnd: w.leftoverValue }, alts);
  return { bar: res.zone_bar, estimated: true };
}

function crossed(value: number, baseline: number, flipAt: number): boolean {
  return flipAt >= baseline ? value >= flipAt : value <= flipAt;
}

/** Flip conditions (05 §8) that the current what-if values have reached. */
export function flipHits(rec: Recommendation, w: WhatIf): FlipCondition[] {
  const baselineV = rec.zone_bar?.inputs?.leftover_value_per_unit_vnd ?? 0;
  return rec.flip_conditions.filter((fc) => {
    if (fc.factor === 'leftover_value_per_unit') return w.leftoverValue !== null && crossed(w.leftoverValue, baselineV, fc.flip_at);
    if (fc.factor === 'restock_delay_days') return w.restockDelayDays !== 0 && crossed(w.restockDelayDays, 0, fc.flip_at);
    return false;
  });
}

// ---------------------------------------------------------------------------
// Citations

export function citationFromSource(src: Source, fallbackComputedAt?: string): Citation {
  return {
    label: src.label,
    kind: src.kind,
    id: src.id,
    tool: src.tool ?? null,
    dataAsOf: src.data_as_of ?? null,
    computedAt: fallbackComputedAt ?? null,
    href: src.href ?? null,
  };
}

/** Source for reason i, falling back to the scenario run behind the recommendation. */
export function reasonCitation(rec: Recommendation, i: number, computedAt?: string): Citation {
  const src = rec.reason_sources?.[i];
  if (src) return citationFromSource(src, computedAt);
  const id = rec.scenario_id ?? rec.recommendation_id;
  return {
    label: `${viText.citation.kind.scenario} ${id}`,
    kind: 'scenario',
    id,
    dataAsOf: rec.inputs_ref.data_as_of,
    computedAt: computedAt ?? null,
    href: '#tier-3',
  };
}

/**
 * Splits a reason around its key number so the number itself opens the source.
 * Prefers a clock time or a number with a unit ("13:00", "9.280đ", "18–31 sp/giờ")
 * over a bare one, so "giá 11.11" is not mistaken for the figure.
 */
export function splitFirstNumber(text: string): { before: string; number: string; after: string } | null {
  const m =
    /\d{1,2}:\d{2}|\d[\d.,]*(?:–\d[\d.,]*)?(?:đ\/sp|đ| ?sp\/giờ| ?sp|%| lần)/.exec(text) ?? /\d[\d.,]*/.exec(text);
  if (!m) return null;
  return { before: text.slice(0, m.index), number: m[0], after: text.slice(m.index + m[0].length) };
}
