/**
 * End-to-end browser verification + demo screenshots.
 * Drives the real UI: types a question, submits, watches the live trace, waits for the
 * final report, and captures screenshots into <repo>/screenshots/.
 *
 * Usage: node scripts/screenshot.mjs [--question "..."]
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(__dirname, "../../screenshots");
mkdirSync(OUT, { recursive: true });

const QUESTION =
  process.argv.includes("--question")
    ? process.argv[process.argv.indexOf("--question") + 1]
    : "How do reflection loops and citation checking improve the reliability of multi-agent LLM research assistants?";

const CHROMIUM = process.env.CHROMIUM_PATH ?? "/usr/bin/chromium";

function log(msg) {
  console.log(`[shot] ${new Date().toISOString().slice(11, 19)} ${msg}`);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const browser = await puppeteer.launch({
    executablePath: CHROMIUM,
    headless: true,
    args: ["--no-sandbox", "--disable-gpu", "--force-dark-mode"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });

  const runUrlArg = process.argv.includes("--run-url")
    ? process.argv[process.argv.indexOf("--run-url") + 1]
    : null;

  if (runUrlArg) {
    // re-capture 03/04 on an existing (finished or finishing) run
    await page.goto(runUrlArg, { waitUntil: "domcontentloaded", timeout: 60000 });
    log(`run page (existing): ${runUrlArg}`);
  } else {
    // 1 — home page with the query typed in
    await page.goto("http://localhost:3000", { waitUntil: "networkidle0", timeout: 60000 });
    await page.waitForSelector("textarea");
    await page.type("textarea", QUESTION, { delay: 4 });
    await sleep(400);
    await page.screenshot({ path: `${OUT}/01-query-input.png` });
    log("captured 01-query-input.png");

    // submit through the real UI button -> navigates to /runs/<id>
    await Promise.all([
      page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 60000 }),
      page.click("button:not([disabled])"),
    ]);
    const runUrl = page.url();
    log(`run page: ${runUrl}`);
    if (!/\/runs\//.test(runUrl)) throw new Error("did not navigate to a run page");

    // 2 — live trace mid-execution: wait for DAG nodes + a few findings, then shoot
    await page.waitForSelector(".react-flow__node", { timeout: 120000 });
    log("DAG rendered");
    await page.waitForFunction(
      () => document.body.innerText.includes("answered:") ||
            document.body.innerText.includes("sandbox output"),
      { timeout: 240000 });
    await sleep(1500);
    await page.screenshot({ path: `${OUT}/02-live-trace.png` });
    log("captured 02-live-trace.png (mid-execution)");
  }

  // 3 — wait for completion: the .pdf download link renders only on a finished run
  await page.waitForSelector('a[href$="report.pdf"]', { timeout: 600000 });
  log("run finished");
  await sleep(2500); // let the final report + verdicts load
  await page.screenshot({ path: `${OUT}/03-final-report.png` });
  log("captured 03-final-report.png");

  // 4 — citation audit tab (bonus)
  const tabs = await page.$$("button");
  for (const t of tabs) {
    const text = await t.evaluate((el) => el.textContent);
    if (text.includes("Citation audit")) { await t.click(); break; }
  }
  await sleep(1200);
  await page.screenshot({ path: `${OUT}/04-citation-audit.png`, fullPage: false });
  log("captured 04-citation-audit.png");

  // sanity assertions for the e2e verification
  const bodyText = await page.evaluate(() => document.body.innerText);
  const checks = {
    "coverage badge": /% cited/.test(bodyText),
    "verdict labels": /(supported|unsupported)/.test(bodyText),
    "pdf link": /\.pdf/.test(bodyText),
  };
  for (const [name, ok] of Object.entries(checks)) log(`check ${name}: ${ok ? "OK" : "MISSING"}`);
  if (Object.values(checks).some((v) => !v)) process.exitCode = 1;

  await browser.close();
  log("done");
}

main().catch((e) => { console.error(e); process.exit(1); });
