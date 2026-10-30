import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../lib/queryKeys';
import { api } from './client';
import type {
  Alert,
  Envelope,
  Freshness,
  HealthStatus,
  Page,
  Recommendation,
  ScenarioRun,
  SkuListItem,
} from './types';

function qs(params: Record<string, string>): string {
  const s = new URLSearchParams(params).toString();
  return s ? `?${s}` : '';
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => api.get<Envelope<HealthStatus>>('/health', signal),
  });
}

export function useFreshness() {
  return useQuery({
    queryKey: queryKeys.freshness,
    queryFn: ({ signal }) => api.get<Envelope<Freshness>>('/freshness', signal),
    refetchInterval: 60_000,
  });
}

export function useSkus(filters: Record<string, string> = { sort: 'priority' }) {
  return useQuery({
    queryKey: queryKeys.skus(filters),
    queryFn: ({ signal }) => api.get<Page<SkuListItem>>(`/skus${qs(filters)}`, signal),
  });
}

export function useRecommendations(filters: Record<string, string> = { active: 'true', sort: 'priority' }) {
  return useQuery({
    queryKey: queryKeys.recommendations(filters),
    queryFn: ({ signal }) => api.get<Page<Recommendation>>(`/recommendations${qs(filters)}`, signal),
  });
}

export function useRecommendation(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.recommendation(id ?? ''),
    queryFn: ({ signal }) => api.get<Envelope<Recommendation>>(`/recommendations/${encodeURIComponent(id ?? '')}`, signal),
    enabled: Boolean(id),
  });
}

export function useScenario(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.scenario(id ?? ''),
    queryFn: ({ signal }) => api.get<Envelope<ScenarioRun>>(`/scenarios/${encodeURIComponent(id ?? '')}`, signal),
    enabled: Boolean(id),
  });
}

export function useAlerts(status = 'open') {
  return useQuery({
    queryKey: queryKeys.alerts(status),
    queryFn: ({ signal }) => api.get<Page<Alert>>(`/alerts${qs({ status })}`, signal),
  });
}
