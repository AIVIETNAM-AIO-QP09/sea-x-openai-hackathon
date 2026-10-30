import { describe, expect, it } from 'vitest';
import worker from '../worker';

describe('Cloudflare deployment health', () => {
  it('reports healthy only when the bound database responds', async () => {
    const response = await worker.fetch(new Request('https://example.test/healthz'), {
      DB: { prepare: () => ({ first: async () => ({ ok: 1 }) }) },
      ASSETS: { fetch: async () => new Response('app') },
    });
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: 'ok', db: 'ok', mode: 'fixtures' });
    expect(response.headers.get('Cache-Control')).toBe('no-store');
  });

  it('returns 503 without exposing database errors', async () => {
    const response = await worker.fetch(new Request('https://example.test/healthz'), {
      DB: { prepare: () => ({ first: async () => { throw new Error('private detail'); } }) },
      ASSETS: { fetch: async () => new Response('app') },
    });
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ status: 'degraded', db: 'error', mode: 'fixtures' });
  });

  it('serves app routes through the assets binding', async () => {
    const response = await worker.fetch(new Request('https://example.test/settings'), {
      DB: { prepare: () => { throw new Error('App assets must not query D1'); } },
      ASSETS: { fetch: async () => new Response('<div id="root"></div>') },
    });
    expect(await response.text()).toBe('<div id="root"></div>');
  });
});
