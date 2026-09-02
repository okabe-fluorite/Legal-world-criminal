import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..", "..", "..");
const require = createRequire(import.meta.url);
const { chromium } = require(path.join(repo, "frontend", "node_modules", "playwright-core"));
const outputDir = path.join(here, "qa", "screens");
fs.mkdirSync(outputDir, { recursive: true });

const mime = new Map([
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".webp", "image/webp"],
]);

const server = http.createServer((req, res) => {
  const requestPath = decodeURIComponent(new URL(req.url, "http://127.0.0.1").pathname);
  const relative = requestPath === "/" ? "index.html" : requestPath.slice(1);
  const file = path.resolve(here, relative);
  if (!file.startsWith(here + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    res.writeHead(404).end("not found");
    return;
  }
  res.writeHead(200, { "Content-Type": mime.get(path.extname(file).toLowerCase()) || "application/octet-stream" });
  fs.createReadStream(file).pipe(res);
});

await new Promise((resolve) => server.listen(8765, "127.0.0.1", resolve));

const browser = await chromium.launch({
  headless: true,
  executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
});
const page = await browser.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 1 });
const consoleErrors = [];
const pageErrors = [];
const failedRequests = [];
page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
page.on("pageerror", (error) => pageErrors.push(String(error)));
page.on("requestfailed", (request) => failedRequests.push(`${request.url()} :: ${request.failure()?.errorText || "failed"}`));

const slides = [];
for (let index = 1; index <= 13; index += 1) {
  await page.goto(`http://127.0.0.1:8765/index.html?slide=${index}`, { waitUntil: "networkidle" });
  await page.evaluate(() => window.__setLowPowerMode?.(true, { persist: false }));
  await page.waitForTimeout(200);
  const audit = await page.evaluate((slideIndex) => {
    const slide = document.querySelectorAll("section.slide")[slideIndex - 1];
    const rect = slide.getBoundingClientRect();
    const textNodes = [...slide.querySelectorAll("h1,h2,h3,p,li,.t-body,.t-body-sm,.t-h-prod,.t-meta,.col-ttl,.col-desc,.layer-ttl,.layer-desc,.name,.desc")];
    const overflow = textNodes.filter((el) => {
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return false;
      const clips = ["hidden", "clip", "scroll", "auto"].includes(style.overflow)
        || ["hidden", "clip", "scroll", "auto"].includes(style.overflowX)
        || ["hidden", "clip", "scroll", "auto"].includes(style.overflowY);
      const box = el.getBoundingClientRect();
      const outsideSlide = box.left < rect.left - 2 || box.right > rect.right + 2 || box.top < rect.top - 2 || box.bottom > rect.bottom + 2;
      return outsideSlide || (clips && (el.scrollWidth > el.clientWidth + 2 || el.scrollHeight > el.clientHeight + 2));
    }).map((el) => ({ tag: el.tagName, cls: el.className, text: el.textContent.trim().slice(0, 80), client: [el.clientWidth, el.clientHeight], scroll: [el.scrollWidth, el.scrollHeight] }));
    const images = [...slide.querySelectorAll("img")].map((img) => ({ src: img.getAttribute("src"), complete: img.complete, natural: [img.naturalWidth, img.naturalHeight], rect: Object.values(img.getBoundingClientRect().toJSON()) }));
    return {
      layout: slide.dataset.layout,
      slideRect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      overflow,
      images,
      title: slide.querySelector("h1,h2")?.textContent.trim().replace(/\s+/g, " ") || "",
    };
  }, index);
  const screenshot = path.join(outputDir, `slide-${String(index).padStart(2, "0")}.png`);
  await page.screenshot({ path: screenshot });
  slides.push({ index, screenshot: path.relative(here, screenshot).replaceAll("\\", "/"), ...audit });
}

await browser.close();
await new Promise((resolve) => server.close(resolve));

const report = {
  generatedAt: new Date().toISOString(),
  viewport: "1600x900",
  slides,
  consoleErrors: [...new Set(consoleErrors)],
  pageErrors: [...new Set(pageErrors)],
  failedRequests: [...new Set(failedRequests)],
};
fs.writeFileSync(path.join(here, "qa", "report.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify({
  slides: slides.length,
  layouts: [...new Set(slides.map((slide) => slide.layout))],
  overflowCount: slides.reduce((sum, slide) => sum + slide.overflow.length, 0),
  imageFailures: slides.flatMap((slide) => slide.images).filter((image) => !image.complete || image.natural[0] === 0).length,
  consoleErrors: report.consoleErrors.length,
  pageErrors: report.pageErrors.length,
  failedRequests: report.failedRequests.length,
  report: path.join(here, "qa", "report.json"),
}, null, 2));
