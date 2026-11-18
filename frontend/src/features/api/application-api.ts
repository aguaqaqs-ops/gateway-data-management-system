import { useState } from "react";
import { createGatewayApi, bindGatewayApi } from "./client";
import { createAuthenticatedFetch } from "./authenticated-fetch";
import { currentGatewaySession } from "./session";

const baseUrl = window.location.origin;
export const gatewayApi = createGatewayApi({ baseUrl, session: currentGatewaySession });
export function useBoundGatewayApi() {
  return useState(() => bindGatewayApi(gatewayApi))[0];
}
export function boundBundleFetch() {
  return createAuthenticatedFetch({
    baseUrl,
    session: currentGatewaySession,
    boundSession: currentGatewaySession(),
    trackConnection: false,
  });
}
