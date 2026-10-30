import type { RouteObject } from 'react-router';
import { AppShell } from './components/AppShell';
import { ShiftOverviewPage } from './pages/ShiftOverviewPage';
import {
  AlertsPage,
  AssistantPage,
  ComparePage,
  DecisionsPage,
  ImportPage,
  NotFoundPage,
  SettingsPage,
  SkuDetailPage,
} from './pages/placeholders';

// Routes follow 09-giao-dien §1. `/sku` and `/compare` without params are entry
// points for the side nav; deep links carry the SKU or campaign.
export const routes: RouteObject[] = [
  {
    element: <AppShell />,
    children: [
      { index: true, element: <ShiftOverviewPage /> },
      { path: 'sku', element: <SkuDetailPage /> },
      { path: 'sku/:sku', element: <SkuDetailPage /> },
      { path: 'sku/:sku/compare', element: <ComparePage /> },
      { path: 'campaign/:id/compare', element: <ComparePage /> },
      { path: 'compare', element: <ComparePage /> },
      { path: 'import', element: <ImportPage /> },
      { path: 'alerts', element: <AlertsPage /> },
      { path: 'decisions', element: <DecisionsPage /> },
      { path: 'assistant', element: <AssistantPage /> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];
