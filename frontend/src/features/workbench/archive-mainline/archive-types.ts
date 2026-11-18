import type { components } from "../../api/generated/openapi";

export type Schemas = components["schemas"];
export type Candidates = Schemas["ArchiveCandidatesResponse"];
export type Candidate = Candidates["candidates"][number];
export type Plan = Schemas["PreviewArchivePlanResponse"];
export type Anomaly = Plan["anomalies"][number];
export type Result = Schemas["ArchiveResultResponse"];
export type CloseResult = Schemas["CloseSubmissionResponse"];
