import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("server-renders the YANAO knowledge search", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  assert.match(response.headers.get("content-type") ?? "", /^text\/html\b/i);
  const html = await response.text();
  assert.match(html, /<title>База знаний ЯНАО<\/title>/i);
  assert.match(html, /Ответы по системам ЯНАО/);
  assert.match(html, /Поиск/);
  assert.match(html, /История/);
  assert.doesNotMatch(html, /codex-preview|SkeletonPreview|Your site is taking shape/i);
});

test("ships a populated public index and MAX Bridge integration", async () => {
  const [indexText, page, layout] = await Promise.all([
    readFile(new URL("../public/search-index.json", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
  ]);
  const index = JSON.parse(indexText);
  assert.ok(index.documents.length >= 1000);
  assert.ok(index.documents.some((item) => item.source === "rsed"));
  assert.ok(index.documents.some((item) => item.source === "esku"));
  assert.ok(index.documents.some((item) => item.source === "kb"));
  assert.ok(index.documents.some((item) => item.source === "files"));
  assert.ok(index.documents.every((item) => typeof item.bloom === "string"));
  assert.ok(index.documents.every((item) => !("content" in item)));
  assert.match(page, /WebApp/);
  assert.match(page, /openLink/);
  assert.match(page, /localStorage/);
  assert.match(layout, /https:\/\/st\.max\.ru\/js\/max-web-app\.js/);
});
