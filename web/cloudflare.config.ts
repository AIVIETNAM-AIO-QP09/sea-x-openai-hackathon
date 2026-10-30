import { bindings, defineConfig } from 'cf/config';

export default defineConfig({
  accountId: '1177b93da7312e51a226b6ecffb1e251',
  worker: {
    name: 'hackathon',
    entrypoint: './worker.ts',
    compatibilityDate: '2026-10-30',
    domains: ['hackathon.dangphuc.me'],
    workersDev: false,
    previewUrls: false,
    assets: { notFoundHandling: 'single-page-application', runWorkerFirst: ['/healthz'] },
    env: {
      ASSETS: bindings.assets(),
      DB: bindings.d1({
        name: 'hackathon-db',
        id: '37eca8be-2aba-4aa1-bdb9-9fbf9e1ec79f',
      }),
    },
  },
});
