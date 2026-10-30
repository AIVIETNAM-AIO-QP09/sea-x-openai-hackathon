// Text and scale helpers for ZoneBar (kept out of the component file for fast refresh).
import type { ZoneBar as ZoneBarData } from '../api/types';
import { formatNumber } from './format';
import { viText } from './i18n';

const t = viText.zoneBar;

function fmt(v: number): string {
  return formatNumber(v, 1);
}

export function verdictSentence(bar: Pick<ZoneBarData, 'verdict' | 'threshold'>): string {
  switch (bar.verdict) {
    case 'undetermined':
      return t.verdict.undetermined(fmt(bar.threshold));
    case 'pause_better':
      return t.verdict.pause_better;
    case 'continue_better':
      return t.verdict.continue_better;
  }
}

export function zoneBarAriaLabel(bar: ZoneBarData): string {
  const [p10, p50, p90] = bar.interval;
  const parts = [verdictSentence(bar), t.summary(fmt(p10), fmt(p50), fmt(p90), fmt(bar.threshold))];
  for (const alt of bar.alt_thresholds) parts.push(t.altSummary(alt.label, fmt(alt.threshold)));
  return parts.join(' ');
}

export function niceStep(span: number): number {
  const raw = span / 5;
  const mag = 10 ** Math.floor(Math.log10(raw));
  for (const m of [1, 2, 2.5, 5, 10]) {
    if (m * mag >= raw) return m * mag;
  }
  return 10 * mag;
}

export function defaultDomain(bar: ZoneBarData): [number, number] {
  const max = Math.max(bar.interval[2], bar.threshold, ...bar.alt_thresholds.map((a) => a.threshold));
  return [0, max > 0 ? max * 1.4 : 1];
}

