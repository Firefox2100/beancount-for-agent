import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const root = join(dirname(fileURLToPath(import.meta.url)), "..");

/** A stub service. `routes` maps "METHOD /path" to `{ status?, body }`. */
export async function stubService(routes) {
  const requests = [];
  const server = createServer((req, res) => {
    let raw = "";
    req.on("data", (chunk) => (raw += chunk));
    req.on("end", () => {
      const url = new URL(req.url, "http://x");
      requests.push({ method: req.method, path: url.pathname, query: url.search, headers: req.headers, body: raw });
      const answer = routes[`${req.method} ${url.pathname}`] ?? { status: 404, body: { detail: "no route" } };
      res.writeHead(answer.status ?? 200, { "content-type": "application/json" });
      res.end(JSON.stringify(answer.body));
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return {
    url: `http://127.0.0.1:${server.address().port}`,
    requests,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

/** Run a command, resolving with its exit code and output. */
export function run(command, args, { env = {}, input = "" } = {}) {
  return new Promise((resolve) => {
    const child = spawn(command, args, { env: { PATH: process.env.PATH, HOME: "/nonexistent", ...env } });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.on("close", (code) => resolve({ code, stdout, stderr }));
    child.stdin.end(input);
  });
}
