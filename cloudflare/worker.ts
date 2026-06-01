import { Container } from "@cloudflare/containers";

const BACKEND_INSTANCE_NAME = "web-v12-scrim";
const BACKEND_START_TIMEOUT_MS = 60000;

export class EsportsTycoonBackend extends Container<Env> {
  defaultPort = 8765;
  sleepAfter = "10m";
  pingEndpoint = "/healthz";
  enableInternet = false;
  envVars = { ESPORTS_TYCOON_CONTENT_BACKEND: "templated" };
}

interface Env {
  ESPORTS_TYCOON_BACKEND: DurableObjectNamespace<EsportsTycoonBackend>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/worker-healthz") {
      return new Response("ok\n", {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }

    const backend = env.ESPORTS_TYCOON_BACKEND.getByName(BACKEND_INSTANCE_NAME);

    try {
      await backend.startAndWaitForPorts({
        cancellationOptions: {
          instanceGetTimeoutMS: BACKEND_START_TIMEOUT_MS,
          portReadyTimeoutMS: BACKEND_START_TIMEOUT_MS,
          waitInterval: 1000,
        },
      });
      return backend.fetch(request);
    } catch (error) {
      console.error("Backend container unavailable", error);
      return new Response("backend container unavailable\n", {
        status: 503,
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
  },
};
