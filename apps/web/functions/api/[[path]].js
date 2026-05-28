// Cloudflare Pages Function — API proxy
// Forwards /api/* → https://vct.tail8c8ced.ts.net/api/*
const BACKEND = "https://vct.tail8c8ced.ts.net";

export async function onRequest(context) {
  const { request } = context;
  const url = new URL(request.url);

  const targetUrl = `${BACKEND}${url.pathname}${url.search}`;

  try {
    const response = await fetch(targetUrl, {
      method: request.method,
      headers: request.headers,
      body: request.method !== "GET" && request.method !== "HEAD"
        ? await request.arrayBuffer()
        : undefined,
      redirect: "follow",
    });

    const modified = new Response(response.body, response);
    modified.headers.set("Access-Control-Allow-Origin", "*");
    return modified;
  } catch (err) {
    return new Response(JSON.stringify({ error: "Backend unreachable" }), {
      status: 502,
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
    });
  }
}
