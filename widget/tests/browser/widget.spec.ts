import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const ANSWER =
  'Project Atlas used FastAPI. <img src=x onerror="globalThis.pwned=true">';
const FIXTURE = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>FolioAware browser test fixture</title>
    <style>
      body { margin: 0; min-height: 100vh; }
      button, textarea, a { all: unset; }
    </style>
  </head>
  <body>
    <main>
      <h1>Synthetic portfolio</h1>
      <p>This fixture contains no private portfolio or visitor data.</p>
    </main>
    <folio-aware
      api-base-url="https://api.example"
      assistant-name="Synthetic portfolio assistant"
    ></folio-aware>
  </body>
</html>`;

function responseFor(question: string): Record<string, unknown> {
  const knowledgeGap = question.includes("pizza");
  return {
    requestId: "browser-request-1",
    answer: knowledgeGap ? "I don't have verified information about that." : ANSWER,
    answerStatus: knowledgeGap ? "knowledge_gap" : "answered",
    citations: knowledgeGap
      ? []
      : [
          {
            sourceId: "project-atlas",
            title: "Project Atlas",
            url: "/projects/atlas",
          },
        ],
    knowledgeVersion: "synthetic-version-1",
  };
}

async function fulfillApi(route: Route): Promise<void> {
  const origin = "null";
  if (route.request().method() === "OPTIONS") {
    await route.fulfill({
      status: 204,
      headers: {
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST",
        "Access-Control-Allow-Origin": origin,
      },
    });
    return;
  }

  const payload = route.request().postDataJSON() as { question?: unknown };
  const question = typeof payload.question === "string" ? payload.question : "";
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    headers: { "Access-Control-Allow-Origin": origin },
    body: JSON.stringify(responseFor(question)),
  });
}

async function openFixture(page: Page): Promise<void> {
  await page.route("https://api.example/v1/ask", fulfillApi);
  await page.setContent(FIXTURE);
  await page.addScriptTag({ path: "dist/folio-aware.js", type: "module" });
  await page.getByRole("button", { name: "Ask Synthetic portfolio assistant" }).click();
}

async function expectNoAccessibilityViolations(page: Page): Promise<void> {
  const result = await new AxeBuilder({ page }).include("folio-aware").analyze();
  expect(result.violations).toEqual([]);
}

test("renders a safe cited answer and preserves keyboard focus behavior", async ({
  page,
}) => {
  await openFixture(page);
  const question = page.getByLabel("Ask about this portfolio");
  await expect(question).toBeFocused();
  await expectNoAccessibilityViolations(page);

  await question.fill("How was Project Atlas built?");
  await question.press("Enter");

  await expect(page.getByRole("status")).toHaveText("Answer ready.");
  await expect(page.getByLabel("Portfolio answer")).toContainText(ANSWER);
  await expect(page.locator("folio-aware img")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Project Atlas" })).toHaveAttribute(
    "href",
    "/projects/atlas",
  );
  await expectNoAccessibilityViolations(page);

  await question.press("Escape");
  const launcher = page.getByRole("button", {
    name: "Ask Synthetic portfolio assistant",
  });
  await expect(launcher).toBeFocused();
  await expect(launcher).toHaveAttribute("aria-expanded", "false");
});

test("renders an accessible responsive knowledge gap without sources", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openFixture(page);
  const question = page.getByLabel("Ask about this portfolio");
  await question.fill("What is the owner's favorite pizza topping?");
  await question.press("Enter");

  await expect(page.getByRole("status")).toHaveText("No verified answer was found.");
  await expect(page.getByLabel("Portfolio answer")).toContainText(
    "I don't have verified information about that.",
  );
  await expect(page.getByRole("heading", { name: "Sources" })).toBeHidden();
  await expect(page.getByRole("link")).toHaveCount(0);
  const box = await page.getByRole("dialog").boundingBox();
  expect(box).not.toBeNull();
  expect((box?.x ?? -1) + (box?.width ?? 0)).toBeLessThanOrEqual(390);
  await expectNoAccessibilityViolations(page);
});
