import puppeteer from "puppeteer-core";
const browser = await puppeteer.launch({
  executablePath: "/usr/bin/chromium", headless: "new",
});
const page = await browser.newPage();
const errs = [];
page.on("console", (m) => { if (m.type() === "error") errs.push(`console: ${m.text()}`); });
page.on("pageerror", (e) => errs.push(`pageerror: ${e.message}`));

await page.goto("http://192.168.178.50:8090/", { waitUntil: "networkidle0" });
await new Promise((r) => setTimeout(r, 1500));

console.log("mode before:", await page.evaluate(() => typeof mode !== "undefined" ? mode : "UNDEFINED"));
console.log("#pg exists:", await page.evaluate(() => !!document.getElementById("pg")));
console.log("setMode exists:", await page.evaluate(() => typeof window.setMode));

await page.click("#pg");
await new Promise((r) => setTimeout(r, 1200));

console.log("mode after click:", await page.evaluate(() => typeof mode !== "undefined" ? mode : "UNDEFINED"));
console.log("stage class:", await page.evaluate(() => document.getElementById("stage").className));
console.log("body class:", await page.evaluate(() => document.body.className));
console.log("errors:", errs.length ? errs : "none");
await browser.close();
