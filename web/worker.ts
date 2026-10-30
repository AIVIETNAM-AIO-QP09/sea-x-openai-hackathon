type Env = {
  DB: { prepare(sql: string): { first(): Promise<unknown> } };
  ASSETS: { fetch(request: Request): Promise<Response> };
  CITY_UI?: { fetch(request: Request): Promise<Response> };
};

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    if (url.pathname !== '/healthz') {
      if (env.CITY_UI) {
        const cityRoute =
          (url.pathname === '/' &&
            url.searchParams.get('workspace') !== 'operations') ||
          url.pathname === '/login' ||
          url.pathname.startsWith('/city-demo') ||
          url.pathname.startsWith('/mock-data') ||
          url.pathname.startsWith('/_next/') ||
          url.pathname.startsWith('/cases/') ||
          url.pathname.startsWith('/api/auth/') ||
          url.pathname.startsWith('/api/pm/') ||
          url.pathname === '/api/workflow/ai' ||
          url.pathname === '/icon.svg' ||
          url.pathname === '/favicon.ico';
        if (cityRoute) return env.CITY_UI.fetch(request);
        // The city owns login. Planned API routes and the existing Vite app keep
        // their original handlers; checking the session adds no commerce rights.
        const sessionUrl = new URL('/api/auth/session', url);
        const session = await env.CITY_UI.fetch(
          new Request(sessionUrl, {
            headers: { cookie: request.headers.get('cookie') ?? '' },
          }),
        );
        if (!session.ok) {
          if (url.pathname.startsWith('/api/'))
            return Response.json(
              {
                error: {
                  code: 'UNAUTHENTICATED',
                  message: 'Sign in to continue.',
                },
              },
              { status: 401, headers: { 'Cache-Control': 'no-store' } },
            );
          return Response.redirect(
            new URL(
              `/login?next=${encodeURIComponent(url.pathname + url.search)}`,
              url,
            ),
            307,
          );
        }
      }
      return env.ASSETS.fetch(request);
    }

    let healthy = true;
    try {
      await env.DB.prepare('SELECT 1 AS ok').first();
    } catch {
      healthy = false;
    }
    return Response.json(
      {
        status: healthy ? 'ok' : 'degraded',
        db: healthy ? 'ok' : 'error',
        mode: 'fixtures',
      },
      { status: healthy ? 200 : 503, headers: { 'Cache-Control': 'no-store' } },
    );
  },
};
