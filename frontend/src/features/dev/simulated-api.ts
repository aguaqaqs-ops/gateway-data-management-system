if (typeof import.meta.env !== "undefined" && import.meta.env.PROD) {
  throw new Error("Gateway simulated API module is forbidden in production");
}

export const SIMULATED_API_MODULE_MARKER = "GatewaySimulatedApiModule";
export * from "./mock-data";
