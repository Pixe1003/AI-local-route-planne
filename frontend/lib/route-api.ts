import type {
  RouteChainRequest,
  RouteChainResponse,
} from "@/lib/route-types";

export async function createRouteChain(
  request: RouteChainRequest,
): Promise<RouteChainResponse> {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (!apiBaseUrl) {
    throw new Error("Missing NEXT_PUBLIC_API_BASE_URL.");
  }

  const response = await fetch(`${apiBaseUrl}/api/route/chain`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }

  return response.json() as Promise<RouteChainResponse>;
}

async function readErrorMessage(response: Response) {
  try {
    const payload = await response.json();
    if (typeof payload.detail === "string") {
      return payload.detail;
    }

    if (payload.detail?.message) {
      const suffix = [payload.detail.info, payload.detail.infocode]
        .filter(Boolean)
        .join(" / ");
      return suffix ? `${payload.detail.message} (${suffix})` : payload.detail.message;
    }
  } catch {
    return `Route API request failed: HTTP ${response.status}`;
  }

  return `Route API request failed: HTTP ${response.status}`;
}
