import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = process.env.GUIZANG_SKILL_ROOT
  || "C:\\Users\\26967\\.codex\\skills\\guizang-ppt-skill-main";
const templatePath = path.join(skillRoot, "assets", "template-swiss.html");
const slidesPath = path.join(here, "slides.html");
const outputPath = path.join(here, "index.html");

const template = fs.readFileSync(templatePath, "utf8");
const slides = fs.readFileSync(slidesPath, "utf8").trim();
const markerStart = template.indexOf("<!-- SLIDES_HERE");
const deckEnd = template.indexOf("\n</div>\n\n<div id=\"nav\">", markerStart);

if (markerStart < 0 || deckEnd < 0) {
  throw new Error("Guizang template markers not found");
}

const layoutIds = [...slides.matchAll(/data-layout="(S\d{2})"/g)].map((m) => m[1]);
if (layoutIds.length !== 13) {
  throw new Error(`Expected 13 data-layout slides, found ${layoutIds.length}`);
}

let output = template
  .replace("[必填] 替换为 PPT 标题 · Deck Title", "星火智学 · 刑法学科模型可信推理技术体系")
  .replace("</head>", "<link rel=\"icon\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' fill='%23002FA7'/%3E%3C/svg%3E\">\n</head>")
  .slice(0, markerStart)
  + slides
  + template.slice(deckEnd);

fs.writeFileSync(outputPath, output, "utf8");
console.log(JSON.stringify({
  output: outputPath,
  slides: layoutIds.length,
  layouts: [...new Set(layoutIds)],
  bytes: Buffer.byteLength(output, "utf8"),
}, null, 2));
