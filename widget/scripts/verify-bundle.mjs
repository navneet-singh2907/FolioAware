import { readFile, stat } from "node:fs/promises";

const bundlePath = new URL("../dist/folio-aware.js", import.meta.url);
const maximumBytes = 50_000;
const forbiddenMarkers = [
  "Authorization",
  "Bearer ",
  "FOLIOAWARE_GOOGLE",
  "apiKey",
  "document.cookie",
  "firestore",
  "googleapis",
  "innerHTML",
  "indexedDB",
  "localStorage",
  "sessionStorage",
];

const [{ size }, bundle] = await Promise.all([
  stat(bundlePath),
  readFile(bundlePath, "utf8"),
]);

if (size > maximumBytes) {
  throw new Error(`Widget bundle exceeds ${maximumBytes} bytes`);
}

for (const marker of forbiddenMarkers) {
  if (bundle.includes(marker)) {
    throw new Error(`Widget bundle contains forbidden marker: ${marker}`);
  }
}

process.stdout.write(`Verified credential-free widget bundle (${size} bytes)\n`);
