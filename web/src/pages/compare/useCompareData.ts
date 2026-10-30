// Resolves which recommendation the Compare screen shows, from either route
// (09 §1): /sku/:sku/compare or /campaign/:id/compare, with an optional ?rec= override.
import { useParams, useSearchParams } from 'react-router';
import { useRecommendation, useRecommendations, useScenario, useSkus } from '../../api/queries';
import type { SkuListItem } from '../../api/types';

export type CompareTarget = {
  sku?: string;
  campaignId?: string;
  skuItem?: SkuListItem;
  recommendationId?: string;
  /** Lookup lists still loading. */
  resolving: boolean;
  resolveError: unknown;
  retryResolve: () => void;
};

export function useCompareTarget(): CompareTarget & { campaignSkus: SkuListItem[] } {
  const { sku, id } = useParams();
  const [search] = useSearchParams();
  const recParam = search.get('rec') ?? undefined;

  const skus = useSkus();
  const recs = useRecommendations();

  const skuItem = sku ? skus.data?.data.find((s) => s.sku === sku) : undefined;
  let recommendationId = recParam;
  if (!recommendationId && sku) recommendationId = skuItem?.recommendation?.recommendation_id;
  if (!recommendationId && id) recommendationId = recs.data?.data.find((r) => r.campaign_id === id)?.recommendation_id;

  const campaignId = id ?? skuItem?.campaign?.id;
  const needsSkus = Boolean(sku) && !recParam;
  const needsRecs = Boolean(id) && !recParam;
  const resolving = (needsSkus && skus.isPending) || (needsRecs && recs.isPending);
  const resolveError = (needsSkus && skus.error) || (needsRecs && recs.error) || null;

  const campaignSkus = campaignId ? (skus.data?.data ?? []).filter((s) => s.campaign?.id === campaignId) : [];

  return {
    sku,
    campaignId,
    skuItem,
    recommendationId,
    resolving,
    resolveError,
    retryResolve: () => {
      void skus.refetch();
      void recs.refetch();
    },
    campaignSkus,
  };
}

export function useCompareData() {
  const target = useCompareTarget();
  const rec = useRecommendation(target.recommendationId);
  const scenarioId = rec.data?.data.scenario_id;
  const scenario = useScenario(scenarioId);
  return { target, rec, scenario };
}
