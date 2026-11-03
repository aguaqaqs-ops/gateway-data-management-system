import { createGatewayApi } from "./client";
import { createAuthenticatedFetch } from "./authenticated-fetch";
import { currentAccessToken } from "./session";

const baseUrl = window.location.origin;

export const gatewayApi = createGatewayApi({ baseUrl, token: currentAccessToken });

// Bundle transport is intentionally excluded from the top bar's connection indicator.
export const fetchBundle = createAuthenticatedFetch({ baseUrl, token: currentAccessToken, trackConnection: false });
