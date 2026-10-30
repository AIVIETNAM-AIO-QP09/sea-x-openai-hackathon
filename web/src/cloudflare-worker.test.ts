import { describe, expect, it } from 'vitest';
import worker from '../worker';

describe('Cloudflare deployment health', () => {
  it('reports healthy only when the bound database responds', async () => {
    const response = await worker.fetch(
      new Request('https://example.test/healthz'),
      {
        DB: { prepare: () => ({ first: async () => ({ ok: 1 }) }) },
        ASSETS: { fetch: async () => new Response('app') },
      },
    );
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      status: 'ok',
      db: 'ok',
      mode: 'fixtures',
    });
    expect(response.headers.get('Cache-Control')).toBe('no-store');
  });

  it('returns 503 without exposing database errors', async () => {
    const response = await worker.fetch(
      new Request('https://example.test/healthz'),
      {
        DB: {
          prepare: () => ({
            first: async () => {
              throw new Error('private detail');
            },
          }),
        },
        ASSETS: { fetch: async () => new Response('app') },
      },
    );
    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({
      status: 'degraded',
      db: 'error',
      mode: 'fixtures',
    });
  });

  it('serves app routes through the assets binding', async () => {
    const response = await worker.fetch(
      new Request('https://example.test/settings'),
      {
        DB: {
          prepare: () => {
            throw new Error('App assets must not query D1');
          },
        },
        ASSETS: { fetch: async () => new Response('<div id="root"></div>') },
      },
    );
    expect(await response.text()).toBe('<div id="root"></div>');
  });
});

describe('isolated city frontend service', () => {
  const base = {
    DB: { prepare: () => ({ first: async () => ({ ok: 1 }) }) },
    ASSETS: { fetch: async () => new Response('existing app') },
  };
  it('routes city, login and sample-data paths to the frontend service', async () => {
    for (const path of [
      '/',
      '/city-demo',
      '/login',
      '/mock-data',
      '/_next/static/app.js',
      '/api/auth/login',
    ]) {
      const response = await worker.fetch(
        new Request(`https://example.test${path}`),
        {
          ...base,
          CITY_UI: {
            fetch: async (request) =>
              new Response(new URL(request.url).pathname),
          },
        },
      );
      expect(await response.text()).toBe(path);
    }
  });
  it('preserves existing routes and D1 health without granting API privileges', async () => {
    const CITY_UI = { fetch: async () => new Response(null, { status: 200 }) };
    const response = await worker.fetch(
      new Request('https://example.test/?workspace=operations'),
      { ...base, CITY_UI },
    );
    expect(await response.text()).toBe('existing app');
    const health = await worker.fetch(
      new Request('https://example.test/healthz'),
      { ...base, CITY_UI },
    );
    expect(await health.json()).toEqual({
      status: 'ok',
      db: 'ok',
      mode: 'fixtures',
    });
  });
  it('requires a validated session for the existing app and API surface', async () => {
    const CITY_UI = { fetch: async () => new Response(null, { status: 401 }) };
    const page = await worker.fetch(
      new Request('https://example.test/settings'),
      { ...base, CITY_UI },
    );
    expect(page.status).toBe(307);
    const api = await worker.fetch(
      new Request('https://example.test/api/v1/skus'),
      { ...base, CITY_UI },
    );
    expect(api.status).toBe(401);
    expect(await api.json()).toHaveProperty('error.code', 'UNAUTHENTICATED');
  });
});
