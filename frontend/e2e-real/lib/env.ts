/**
 * Journey environment written by `scripts/run-real-backend-e2e.sh` for
 * `--suite journeys` (FE3b §4.6/§4.7):
 *
 * - GATEWAY_FE_IDENTITIES: JSON array of injected sessions, one entry per
 *   (journey scope, role); each carries its own token/actor and the scope's
 *   gateway device + business project, so reviewer/submitter sessions share the
 *   same Repository Service scope without sharing an actor id.
 * - GATEWAY_FE_JOURNEY_SCOPES: JSON document with one independent Repository
 *   Service scope per journey (unique RS Idempotency-Key + baseline node; the
 *   INITIAL baseline is empty and seeded before the backend starts).
 * - GATEWAY_FE_JOURNEY_INPUT_ROOT: upload directories rebuilt outside the
 *   worktree (placeholder .pmc + sql/dbcfg.sql + comps/logic/logics.xml).
 */

export interface JourneyIdentity {
  name: string;
  role: string;
  scope: string;
  token: string;
  actorId: string;
  businessProjectId: string;
  gatewayDeviceExternalKey: string;
}

export interface JourneyScopeRole {
  role: string;
  name: string;
}

export interface JourneyInputs {
  modified_only: string;
  full_initial: string;
  full_modified: string;
}

export interface JourneyScope {
  slug: string;
  roles: JourneyScopeRole[];
  repository_id: string;
  initial_commit_id: string;
  business_baseline_node_id: string;
  inputs: JourneyInputs;
}

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is required by the journeys suite (run scripts/run-real-backend-e2e.sh --suite journeys)`);
  return value;
}

export function previewBaseUrl(): string {
  return (process.env.GATEWAY_FE_PREVIEW_URL ?? "http://127.0.0.1:4173").replace(/\/$/, "");
}

export function identities(): JourneyIdentity[] {
  const raw = requireEnv("GATEWAY_FE_IDENTITIES");
  const parsed = JSON.parse(raw) as JourneyIdentity[];
  if (!Array.isArray(parsed) || parsed.length === 0) throw new Error("GATEWAY_FE_IDENTITIES is empty");
  return parsed;
}

export function journeyScopes(): JourneyScope[] {
  const raw = requireEnv("GATEWAY_FE_JOURNEY_SCOPES");
  const parsed = JSON.parse(raw) as { scopes?: JourneyScope[] };
  if (!parsed.scopes || parsed.scopes.length === 0) throw new Error("GATEWAY_FE_JOURNEY_SCOPES has no scopes");
  return parsed.scopes;
}

export function scopeBySlug(slug: string): JourneyScope {
  const found = journeyScopes().find((scope) => scope.slug === slug);
  if (!found) throw new Error(`journey scope ${slug} is missing from GATEWAY_FE_JOURNEY_SCOPES`);
  return found;
}

export function identityFor(scope: JourneyScope, role: string): JourneyIdentity {
  const declared = scope.roles.find((entry) => entry.role === role);
  if (!declared) throw new Error(`journey scope ${scope.slug} has no ${role} session`);
  const found = identities().find((identity) => identity.name === declared.name);
  if (!found) throw new Error(`identity ${declared.name} for scope ${scope.slug}/${role} is missing`);
  return found;
}

export function resultsDir(): string {
  return process.env.GATEWAY_FE_RESULTS_DIR ?? "/results";
}

export function inputDir(scope: JourneyScope, key: keyof JourneyInputs): string {
  const directory = scope.inputs[key];
  if (!directory) throw new Error(`journey scope ${scope.slug} has no ${key} input directory`);
  return directory;
}
