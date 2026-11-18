import { PassThrough, Transform } from "node:stream";

import type { EntryContext } from "react-router";
import { createReadableStreamFromReadable } from "@react-router/node";
import { ServerRouter } from "react-router";
import { isbot } from "isbot";
import type { RenderToPipeableStreamOptions } from "react-dom/server";
import { renderToPipeableStream } from "react-dom/server";
import { addBeaconNonce, buildContentSecurityPolicy, generateNonce } from "./csp.server";

export const streamTimeout = 5_000;

// Lighthouse's simulated paint timing counts every request that started before the
// first paint as paint-blocking. The home page emitted ~20 modulepreloads (~140 KB)
// that, throttled, pushed LCP to ~2.4 s although the real paint was at ~0.1 s. Only
// the entry, runtime and framework chunks stay preloaded (tests/e2e/ssr-head.spec.ts pins this); the route chunks are fetched as the entry imports them.
const ESSENTIAL_PRELOAD = /<link rel="modulepreload" href="\/assets\/(?!entry\.client|rolldown-runtime|framework)[^"]*"[^>]*\/>/g;

/** Drops non-essential modulepreload hints from the document <head> and nonces the beacon tag, then passes the rest through. */
function trimModulePreloads(nonce: string): Transform {
  let pending = "";
  let done = false;
  return new Transform({
    transform(chunk: Buffer, _encoding, callback) {
      if (done) return callback(null, chunk);
      pending += chunk.toString("utf8");
      const headEnd = pending.indexOf("</head>");
      if (headEnd === -1) return callback();
      done = true;
      const html = addBeaconNonce(pending.slice(0, headEnd).replace(ESSENTIAL_PRELOAD, ""), nonce) + pending.slice(headEnd);
      pending = "";
      callback(null, html);
    },
    flush(callback) {
      callback(null, done ? undefined : pending);
    },
  });
}

export default function handleRequest(
  request: Request,
  responseStatusCode: number,
  responseHeaders: Headers,
  routerContext: EntryContext,
) {
  // https://httpwg.org/specs/rfc9110.html#HEAD
  if (request.method.toUpperCase() === "HEAD") {
    return new Response(null, {
      status: responseStatusCode,
      headers: responseHeaders,
    });
  }

  // One nonce per response. The Cloudflare edge may cache the whole response (headers included)
  // for s-maxage, so the nonce and the CSP header always travel together. See docs/production-security-runbook.md.
  const nonce = generateNonce();
  // Dev needs Vite's inline HMR/refresh scripts, which carry no nonce: enforce only in production builds.
  if (import.meta.env.PROD) {
    responseHeaders.set("Content-Security-Policy", buildContentSecurityPolicy(nonce));
  }

  return new Promise((resolve, reject) => {
    let shellRendered = false;
    const userAgent = request.headers.get("user-agent");

    // Ensure requests from bots and SPA Mode renders wait for all content to load before responding
    // https://react.dev/reference/react-dom/server/renderToPipeableStream#waiting-for-all-content-to-load-for-crawlers-and-static-generation
    const readyOption: keyof RenderToPipeableStreamOptions =
      (userAgent && isbot(userAgent)) || routerContext.isSpaMode
        ? "onAllReady"
        : "onShellReady";

    // Abort the rendering stream after the `streamTimeout` so it has time to
    // flush down the rejected boundaries
    let timeoutId: ReturnType<typeof setTimeout> | undefined = setTimeout(
      () => abort(),
      streamTimeout + 1000,
    );

    const { pipe, abort } = renderToPipeableStream(
      <ServerRouter context={routerContext} url={request.url} nonce={nonce} />,
      {
        // React's own streaming inline scripts (Suspense boundary swaps) need the nonce too.
        nonce,
        [readyOption]() {
          shellRendered = true;
          const body = new PassThrough({
            final(callback) {
              // Clear the timeout to prevent retaining the closure and memory leak
              clearTimeout(timeoutId);
              timeoutId = undefined;
              callback();
            },
          });
          const stream = createReadableStreamFromReadable(body.pipe(trimModulePreloads(nonce)));

          responseHeaders.set("Content-Type", "text/html");

          pipe(body);

          resolve(
            new Response(stream, {
              headers: responseHeaders,
              status: responseStatusCode,
            }),
          );
        },
        onShellError(error: unknown) {
          reject(error);
        },
        onError(error: unknown) {
          responseStatusCode = 500;
          // Log streaming rendering errors from inside the shell.  Don't log
          // errors encountered during initial shell rendering since they'll
          // reject and get logged in handleDocumentRequest.
          if (shellRendered) {
            console.error(error);
          }
        },
      },
    );
  });
}
