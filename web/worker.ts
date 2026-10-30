type Env = {
  DB: { prepare(sql: string): { first(): Promise<unknown> } };
  ASSETS: { fetch(request: Request): Promise<Response> };
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (new URL(request.url).pathname !== '/healthz') return env.ASSETS.fetch(request);

    let healthy = true;
    try {
      await env.DB.prepare('SELECT 1 AS ok').first();
    } catch {
      healthy = false;
    }
    return Response.json(
      { status: healthy ? 'ok' : 'degraded', db: healthy ? 'ok' : 'error', mode: 'fixtures' },
      { status: healthy ? 200 : 503, headers: { 'Cache-Control': 'no-store' } },
    );
  },
};
