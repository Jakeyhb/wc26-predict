// Cloudflare Pages Function — API proxy with caching
// Forwards /api/* → https://vct.tail8c8ced.ts.net/api/*
const BACKEND = "https://vct.tail8c8ced.ts.net";

// Cache GET requests to reduce latency on repeated calls
function cacheKey(request) {
  const url = new URL(request.url);
  return url.pathname + url.search;
}

function cacheTTL(pathname) {
  if (pathname.includes("/matches/schedule") || pathname.includes("/matches/upcoming")) return 300;
  if (pathname.includes("/predictions/") && pathname.includes("/latest")) return 120;
  if (pathname.includes("/predictions/") && pathname.includes("/history")) return 60;
  if (pathname.includes("/health") || pathname.includes("/stats")) return 180;
  if (pathname.includes("/teams")) return 600;
  return 0; // no cache for POST, analysis, etc.
}

export async function onRequest(context) {
  const { request, env } = context;
  const url = new URL(request.url);

  // Only cache GET requests
  if (request.method === "GET") {
    const ttl = cacheTTL(url.pathname);
    if (ttl > 0) {
      const cached = await caches.default.match(request);
      if (cached) return cached;
    }
  }

  const targetUrl = `${BACKEND}${url.pathname}${url.search}`;
  const init = {
    method: request.method,
    headers: request.headers,
    redirect: "follow",
  };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  try {
    const response = await fetch(targetUrl, init);
    const modified = new Response(response.body, response);
    modified.headers.set("Access-Control-Allow-Origin", "*");

    // Cache successful GET responses
    if (request.method === "GET" && response.ok) {
      const ttl = cacheTTL(url.pathname);
      if (ttl > 0) {
        modified.headers.set("Cache-Control", `public, max-age=${ttl}`);
        context.waitUntil(caches.default.put(request, modified.clone()));
      }
    }

    return modified;
  } catch (err) {
    return new Response(JSON.stringify({ error: "Backend unreachable" }), {
      status: 502,
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
    });
  }
}
