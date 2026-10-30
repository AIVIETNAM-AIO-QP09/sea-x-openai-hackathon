// Single entry point for API types. Aliases point into schema.d.ts (generated
// by `npm run gen:api`); if the backend names a schema differently, fix it here.
import type { components } from './schema';

type S = components['schemas'];

export type HealthStatus = S['HealthStatus'];
export type Meta = S['Meta'];
export type Source = S['Source'];
export type ComputeState = S['ComputeState'];
export type Confidence = S['Confidence'];
export type ActionKind = S['ActionKind'];
export type ActionSpec = S['ActionSpec'];
export type Quantiles = S['Quantiles'];
export type Freshness = S['Freshness'];
export type FreshnessSource = S['FreshnessSource'];
export type SkuListItem = S['SkuListItem'];
export type Recommendation = S['Recommendation'];
export type RecommendationStatus = S['RecommendationStatus'];
export type ZoneBar = S['ZoneBar'];
export type ZoneVerdict = S['ZoneVerdict'];
export type AltThreshold = S['AltThreshold'];
export type BreakevenRequest = S['BreakevenRequest'];
export type BreakevenResponse = S['BreakevenResponse'];
export type FlipCondition = S['FlipCondition'];
export type InputsRef = S['InputsRef'];
export type SimRequest = S['SimRequest'];
export type ScenarioRun = S['ScenarioRun'];
export type ScenarioResult = S['ScenarioResult'];
export type DecisionCreate = S['DecisionCreate'];
export type DecisionCreated = S['DecisionCreated'];
export type Alert = S['Alert'];
export type LiveStatus = S['LiveStatus'];

/** Response frame for numeric results (08-api §1). */
export type Envelope<T> = {
  data: T;
  meta?: Meta;
};

/** List response with cursor pagination (08-api §1). */
export type Page<T> = Envelope<T[]> & { next_cursor?: string | null };

export type ApiErrorBody = S['ApiErrorBody'];
