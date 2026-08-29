import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const repo = path.resolve(path.dirname(new URL(import.meta.url).pathname.slice(1)), "..", "..");
const { chromium } = require(path.join(repo, "frontend", "node_modules", "playwright-core"));
const html = path.resolve(process.argv[2]);
const output = path.resolve(process.argv[3]);
if (!fs.existsSync(html)) throw new Error(`missing HTML: ${html}`);
fs.mkdirSync(output, { recursive: true });
const executablePath = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].find(fs.existsSync);
const browser = await chromium.launch({ headless: true, executablePath });
for (let index = 1; index <= 2; index += 1) {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await page.goto(`${pathToFileURL(html).href}?slide=${index}`, { waitUntil: "load" });
  await page.screenshot({ path: path.join(output, `CASE3_E2E_${index === 1 ? "INV" : "PR"}.png`) });
  await page.close();
}
await browser.close();
