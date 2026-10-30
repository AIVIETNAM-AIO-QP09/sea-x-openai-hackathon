import { ApiError, createApiClient } from './client';
import type { Envelope, HealthStatus, Recommendation } from './types';

const user = { id: 'u-ops-1', role: 'operator' as const };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('createApiClient (HTTP)', () => {
  it('sends base URL and X-User / X-Role headers', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(200, { data: { status: 'ok', db: 'ok', ai: 'disabled' }, meta: {} }),
    );
    const client = createApiClient({ baseUrl: '/api/v1', useFixtures: false, user, fetchImpl });

    const health = await client.get<Envelope<HealthStatus>>('/health');

    expect(health.data.status).toBe('ok');
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/v1/health');
    expect(init.headers).toMatchObject({ 'X-User': 'u-ops-1', 'X-Role': 'operator' });
  });

  it('maps the 08 §1 error body to ApiError', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(400, {
        error: {
          code: 'PARAM_OUT_OF_RANGE',
          message: 'Giá trị hàng dư phải từ 0 đến 690.000đ.',
          details: { key: 'leftover_value_per_unit', min: 0, max: 690000, got: 900000 },
        },
      }),
    );
    const client = createApiClient({ baseUrl: '/api/v1', useFixtures: false, user, fetchImpl });

    const err = await client.put('/parameters/leftover_value_per_unit', { value: 900000 }).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 400, code: 'PARAM_OUT_OF_RANGE', details: { max: 690000 } });
  });

  it('POST sends JSON body, headers and maps 422 BLOCKING_DATA_ISSUE details', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse(422, {
        error: { code: 'BLOCKING_DATA_ISSUE', message: 'Chiến dịch CD006 chưa có mục tiêu.', details: { campaign_id: 'CD006', missing: 'goal' } },
      }),
    );
    const client = createApiClient({ baseUrl: '/api/v1', useFixtures: false, user, fetchImpl });
    const err = await client.post('/scenarios/run', { campaign_id: 'CD006', samples: 300, seed: 1 }).catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 422, code: 'BLOCKING_DATA_ISSUE', details: { missing: 'goal' } });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/v1/scenarios/run');
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json', 'X-Role': 'operator' });
    expect(JSON.parse(String(init.body))).toEqual({ campaign_id: 'CD006', samples: 300, seed: 1 });
  });

  it('turns network failures into a readable Vietnamese error', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    });
    const client = createApiClient({ baseUrl: '/api/v1', useFixtures: false, user, fetchImpl });

    await expect(client.get('/health')).rejects.toMatchObject({ code: 'NETWORK_ERROR', status: 0 });
  });
});

describe('createApiClient (fixtures)', () => {
  const client = createApiClient({ baseUrl: '/api/v1', useFixtures: true, user });

  it('serves the CD002 recommendation: schedule_hours wins, pause blocked', async () => {
    const rec = await client.get<Envelope<Recommendation>>('/recommendations/rec-551');
    expect(rec.data.best?.kind).toBe('schedule_hours');
    expect(rec.data.campaign_id).toBe('CD002');
    expect(rec.meta?.confidence).toBe('reference');

    const scn = await client.get<{ data: { results: { action: { kind: string }; feasible: boolean; violations: string[] }[] } }>(
      '/scenarios/scn-2291',
    );
    const pause = scn.data.results.find((r) => r.action.kind === 'pause');
    expect(pause).toMatchObject({ feasible: false, violations: ['campaign_must_run'] });
  });

  it('ignores the query string when matching fixtures', async () => {
    const skus = await client.get<{ data: unknown[] }>('/skus?sort=priority');
    expect(skus.data.length).toBeGreaterThan(0);
  });

  it('answers GET /skus/{sku} from the list fixture, and serves /campaigns/CD002', async () => {
    const one = await client.get<{ data: { sku: string; campaign: { id: string } } }>('/skus/NOICHIEN2L');
    expect(one.data).toMatchObject({ sku: 'NOICHIEN2L', campaign: { id: 'CD002' } });
    await expect(client.get('/skus/KHONGCO')).rejects.toMatchObject({ status: 404 });
    const cd = await client.get<{ data: { price_max_vnd: number; goal: { goal_id: string } } }>('/campaigns/CD002');
    expect(cd.data.price_max_vnd).toBe(690000);
    expect(cd.data.goal.goal_id).toBe('goal-cd002-1111');
  });

  it('fixtures have the real response shape (results carry key/label and full Dist)', async () => {
    const scn = await client.get<{ data: { results: { key: string; label: string; spend: Record<string, number> }[]; cache_hit: boolean } }>(
      '/scenarios/scn-2291',
    );
    for (const r of scn.data.results) {
      expect(r.key).toBeTruthy();
      expect(r.label).toBeTruthy();
      expect(Object.keys(r.spend).sort()).toEqual(['mean', 'p10', 'p50', 'p90']);
    }
    const me = await client.get<{ data: Record<string, unknown> }>('/me');
    expect(me.data).toMatchObject({ id: 'u-ops-1', role: 'operator', can_run_scenarios: true });
  });

  it('returns NOT_FOUND for paths without a fixture', async () => {
    await expect(client.get('/nope')).rejects.toMatchObject({ status: 404, code: 'NOT_FOUND' });
  });
});
