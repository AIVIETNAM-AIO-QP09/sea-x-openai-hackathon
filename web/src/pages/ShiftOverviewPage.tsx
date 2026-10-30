import { ChevronRight, Database } from 'lucide-react';
import { useMemo } from 'react';
import { Link } from 'react-router';
import { useRecommendations, useSkus } from '../api/queries';
import type { Recommendation, SkuListItem } from '../api/types';
import { ComputeStateTag, ConfidenceBadge } from '../components/badges';
import { EmptyState, ErrorState, PageHeader, SkeletonRows } from '../components/states';
import { formatNumber, formatTime, formatUnits, formatVndMillions } from '../lib/format';
import { viText } from '../lib/i18n';

const t = viText.overview;
const ATTENTION_LIMIT = 5;

function needsAttention(item: SkuListItem): boolean {
  // 09 §2.1: open alert, or the recommendation is not plain "continue".
  return item.open_alerts > 0 || (item.recommendation != null && item.recommendation.best.kind !== 'continue');
}

function recommendationText(item: SkuListItem): string {
  const rec = item.recommendation;
  if (!rec) return '—';
  if (rec.status === 'undetermined') return viText.recommendationStatus.undetermined;
  if (rec.status === 'none_meets_goal') return viText.recommendationStatus.none_meets_goal;
  return viText.action(rec.best);
}

function displayName(item: SkuListItem): string {
  return item.variant ? `${item.name} · ${item.variant}` : item.name;
}

function AttentionCard({ item, rec }: { item: SkuListItem; rec: Recommendation | undefined }) {
  const dimmed = item.compute_state === 'computing' || item.compute_state === 'queued';
  return (
    <li className={`card flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 ${dimmed ? 'opacity-60' : ''}`}>
      <div className="min-w-56 flex-1">
        <p className="font-medium">{displayName(item)}</p>
        <p className="text-xs text-muted">
          {item.sku} · {item.campaign ? `${item.campaign.id} · ${item.campaign.status}` : t.noCampaign}
        </p>
      </div>
      <div className="min-w-48 text-sm">
        <p className="tabular-nums">{t.stockLine(formatUnits(item.stock_available), formatNumber(item.hours_of_cover.p50))}</p>
        <p className="text-xs text-muted">
          {t.deviation[item.deviation] ?? item.deviation}
          {item.open_alerts > 0 ? ` · ${t.alertCount(item.open_alerts)}` : ''}
        </p>
      </div>
      <div className="min-w-48 text-sm">
        <p className="font-medium">{recommendationText(item)}</p>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-muted">
          {item.recommendation ? <ConfidenceBadge value={item.recommendation.confidence} /> : null}
          {rec ? <span className="tabular-nums">{t.gainLine(formatVndMillions(rec.expected_gain_vnd))}</span> : null}
          <ComputeStateTag state={item.compute_state} />
        </div>
      </div>
      <Link to={`/sku/${encodeURIComponent(item.sku)}/compare`} className="btn-secondary ml-auto">
        {t.compare}
        <ChevronRight aria-hidden className="size-4" />
      </Link>
    </li>
  );
}

function SkuTable({ items }: { items: SkuListItem[] }) {
  const c = t.columns;
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-border text-xs text-muted">
          <tr>
            <th className="px-3 py-2 font-medium">{c.sku}</th>
            <th className="px-3 py-2 text-right font-medium">{c.stock}</th>
            <th className="px-3 py-2 text-right font-medium">{c.cover}</th>
            <th className="px-3 py-2 text-right font-medium">{c.soldToday}</th>
            <th className="px-3 py-2 font-medium">{c.recommendation}</th>
            <th className="px-3 py-2 font-medium">{c.confidence}</th>
            <th className="px-3 py-2 font-medium">{c.updated}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.sku} className="border-b border-border last:border-0 hover:bg-surface-2">
              <td className="px-3 py-2">
                <Link to={`/sku/${encodeURIComponent(item.sku)}`} className="font-medium hover:underline">
                  {item.sku}
                </Link>
                <div className="text-xs text-muted">{displayName(item)}</div>
              </td>
              <td className="px-3 py-2 text-right">{formatNumber(item.stock_available, 0)}</td>
              <td className="px-3 py-2 text-right">{formatNumber(item.hours_of_cover.p50)}</td>
              <td className="px-3 py-2 text-right">{formatNumber(item.sold_today_units, 0)}</td>
              <td className="px-3 py-2">{recommendationText(item)}</td>
              <td className="px-3 py-2">{item.recommendation ? <ConfidenceBadge value={item.recommendation.confidence} /> : '—'}</td>
              <td className="px-3 py-2">
                <ComputeStateTag state={item.compute_state} computedAt={item.computed_at} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ShiftOverviewPage() {
  const skus = useSkus();
  const recs = useRecommendations();
  const p = viText.pages.overview;

  const items = useMemo(
    () => [...(skus.data?.data ?? [])].sort((a, b) => b.priority_score - a.priority_score),
    [skus.data],
  );
  const attention = items.filter(needsAttention).slice(0, ATTENTION_LIMIT);
  const recById = useMemo(
    () => new Map((recs.data?.data ?? []).map((r) => [r.recommendation_id, r])),
    [recs.data],
  );
  const lastComputed = items.map((i) => i.computed_at).sort().at(-1);

  let body;
  if (skus.isPending) {
    body = <SkeletonRows rows={4} />;
  } else if (skus.isError) {
    body = <ErrorState error={skus.error} onRetry={() => void skus.refetch()} />;
  } else if (items.length === 0) {
    body = (
      <EmptyState
        icon={Database}
        title={t.emptyTitle}
        body={t.emptyBody}
        action={
          <Link to="/import" className="btn-primary">
            {t.emptyAction}
          </Link>
        }
      />
    );
  } else {
    body = (
      <div className="space-y-6">
        <section aria-labelledby="attention-heading">
          <h2 id="attention-heading" className="mb-2 font-medium">
            {t.needsAttention(attention.length)}
          </h2>
          {attention.length > 0 ? (
            <ul className="space-y-2">
              {attention.map((item) => (
                <AttentionCard
                  key={item.sku}
                  item={item}
                  rec={item.recommendation ? recById.get(item.recommendation.recommendation_id) : undefined}
                />
              ))}
            </ul>
          ) : (
            <p className="card px-4 py-3 text-muted">{t.nothingToReview(lastComputed ? formatTime(lastComputed) : '—')}</p>
          )}
        </section>
        <section aria-labelledby="all-heading">
          <h2 id="all-heading" className="mb-2 font-medium">
            {t.allSkus(items.length)}
          </h2>
          <SkuTable items={items} />
        </section>
      </div>
    );
  }

  return (
    <>
      <PageHeader title={p.title} description={p.description} />
      {body}
    </>
  );
}
