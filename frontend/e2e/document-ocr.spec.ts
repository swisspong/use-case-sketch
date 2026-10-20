import type { Page, Request } from "@playwright/test"
import { test, expect, holdRequest, seedPreset } from "./support"
import { seed } from "./documents-support"

// Seeded document: page 1 "Hello PDF" passes, page 2 is blank and suggests OCR.
// The test server simulates the provider by model id (tests/settings_app.py) while the
// real renderer, adapter, encryption and Postgres are used.

function panelOf(page: Page) {
  return page.getByRole("region", { name: "ผลตรวจคุณภาพรายหน้า" })
}

function countOcrPosts(page: Page, id: string) {
  const posts: Request[] = []
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().endsWith(`/api/documents/${id}/ocr`))
      posts.push(r)
  })
  return posts
}

async function setDefault(page: Page, presetId: string) {
  const r = await page.request.put(`/api/llm/presets/${presetId}/default`)
  expect(r.ok()).toBeTruthy()
}

test("first OCR: preparing, running with warning, compare view, tabs, thumbnail and reload", async ({
  page,
  context,
}) => {
  const id = await seed(page.request)
  const preset = await seedPreset(page.request, "Vision OK", {
    model_id: "e2e-ok",
  })
  await seedPreset(page.request, "Other model", { model_id: "e2e-ocr-poor" })
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  const presetsHeld = await holdRequest(page, "**/api/llm/presets", "GET")
  const ocrHeld = await holdRequest(page, `**/api/documents/${id}/ocr`, "POST")
  let pageGets = 0
  page.on("request", (r) => {
    if (r.url().endsWith(`/api/documents/${id}/pages/2`)) pageGets++
  })
  await page.goto(`/documents/${id}?page=2`)
  const panel = panelOf(page)
  await expect(panel.getByText("ไม่ผ่านเกณฑ์ 1 จาก 4 ข้อ")).toBeVisible()
  await expect(
    page.getByRole("button", { name: "หน้า 2 แนะนำ OCR", exact: true })
  ).toBeVisible()
  await panel.getByRole("button", { name: "OCR หน้านี้", exact: true }).click()

  // Presets are resolved first; the model name is unknown until they load.
  await expect(panel.getByText("กำลังเตรียม OCR…")).toBeVisible()
  await expect(panel.getByText(/กำลัง OCR หน้า/)).toHaveCount(0)
  presetsHeld.release()

  const request = await ocrHeld.received
  expect(request.postDataJSON()).toEqual({ page: 2, preset_id: preset.id })
  await expect(
    panel.getByText("กำลัง OCR หน้า 2 ด้วย Vision OK…", { exact: true })
  ).toBeVisible()
  await expect(panel.getByText("กำลัง OCR", { exact: true })).toBeVisible()
  await expect(
    panel.getByText("อย่าปิดหรือออกจากหน้านี้จนกว่าจะเสร็จ")
  ).toBeVisible()
  await expect(panel.getByText("00:0", { exact: false })).toBeVisible()
  await expect(
    panel.getByRole("button", { name: "OCR หน้านี้", exact: true })
  ).toHaveCount(0)

  // Leaving while the synchronous OCR runs triggers the native warning.
  const warning = page.waitForEvent("dialog")
  const reload = page.evaluate(() => window.location.reload())
  const dialog = await warning
  expect(dialog.type()).toBe("beforeunload")
  await dialog.dismiss()
  await reload

  const gets = pageGets
  ocrHeld.release()
  await expect(
    panel.getByRole("heading", { name: "ผลลัพธ์ · หน้า 2" })
  ).toBeVisible()
  await expect(panel.getByText("OCR แล้ว", { exact: true })).toBeVisible()
  await expect(
    page.getByRole("button", { name: "หน้า 2 OCR แล้ว", exact: true })
  ).toBeVisible()
  expect(pageGets).toBe(gets) // the POST response is used directly
  // OCR values are shown but never judged: no icons, no summary, no badge.
  const compare = panel.getByRole("table", { name: "เทียบผลเดิมกับ OCR" })
  await expect(compare.getByText("ไม่ผ่าน 1 ข้อ")).toBeVisible()
  await expect(compare.getByText("ผ่านทุกข้อ")).toHaveCount(0)
  const chars = compare.getByRole("row", { name: /จำนวนตัวอักษร/ })
  await expect(chars.getByRole("cell")).toHaveText(["0", "12"])
  await expect(chars.getByRole("cell").nth(1).getByLabel(/ผ่าน/)).toHaveCount(0)
  await expect(panel.getByText("ผ่าน", { exact: true })).toHaveCount(0)
  await expect(panel.getByText("ไม่ผ่าน", { exact: true })).toHaveCount(1)
  await expect(panel.getByText("Vision OK ·", { exact: false })).toBeVisible()
  await expect(panel.getByText("OCR · e2e-ok")).toBeVisible()
  await expect(panel.getByText("Hello OCR text", { exact: true })).toBeVisible()
  await panel.getByRole("button", { name: "คัดลอกข้อความ OCR" }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    "Hello OCR text"
  )

  await panel.getByRole("tab", { name: "ผลเดิม", exact: true }).click()
  await expect(
    panel.getByRole("table", { name: "คุณภาพผลเดิมเทียบเกณฑ์" })
  ).toBeVisible()
  await expect(panel.getByText("ไม่พบข้อความในหน้านี้")).toBeVisible()
  await expect(panel.getByText("Hello OCR text")).toHaveCount(0)
  await panel.getByRole("tab", { name: "OCR", exact: true }).click()
  const ocrValues = panel.getByRole("table", { name: "ค่าวัดข้อความ OCR" })
  await expect(ocrValues).toBeVisible()
  await expect(ocrValues.getByLabel(/ผ่าน/)).toHaveCount(0)
  await expect(panel.getByText("ผ่าน", { exact: true })).toHaveCount(0)
  await expect(panel.getByText("Hello OCR text", { exact: true })).toBeVisible()

  // Page 1 passed the parser: no alert, but OCR is still offered.
  await page.getByRole("button", { name: "หน้าก่อนหน้า", exact: true }).click()
  await expect(panel.getByText("Hello PDF", { exact: true })).toBeVisible()
  await expect(panel.getByText("ผ่านเกณฑ์", { exact: true })).toBeVisible()
  await expect(
    panel.getByRole("button", { name: "OCR หน้านี้", exact: true })
  ).toBeEnabled()

  await page.goto(`/documents/${id}?page=2`)
  await expect(panel.getByText("Hello OCR text", { exact: true })).toBeVisible()
  await expect(
    panel.getByRole("tab", { name: "เทียบผล", selected: true })
  ).toBeVisible()
  const detail = await (await page.request.get(`/api/documents/${id}`)).json()
  expect(detail.pages[1]).toEqual({
    number: 2,
    ocr_suggested: true,
    has_ocr: true,
  })
  expect(detail.ocr_suggested_count).toBe(0)
  await page.screenshot({
    path: "test-results/document-ocr-compare.png",
    fullPage: true,
  })
})

test("rerun keeps the previous result while running, replaces it on success and keeps it on failure", async ({
  page,
}) => {
  const id = await seed(page.request)
  await seedPreset(page.request, "Vision OK", { model_id: "e2e-ok" })
  const poor = await seedPreset(page.request, "Poor", {
    model_id: "e2e-ocr-poor",
  })
  const broken = await seedPreset(page.request, "Broken", {
    model_id: "e2e-unavailable",
  })
  const first = await page.request.post(`/api/documents/${id}/ocr`, {
    data: { page: 2 },
  })
  expect((await first.json()).status).toBe("ok")
  await setDefault(page, poor.id)
  const posts = countOcrPosts(page, id)
  const held = await holdRequest(page, `**/api/documents/${id}/ocr`, "POST")
  await page.goto(`/documents/${id}?page=2`)
  const panel = panelOf(page)
  await panel.getByRole("button", { name: "OCR ใหม่", exact: true }).click()
  await held.received
  await expect(
    panel.getByText("กำลัง OCR หน้า 2 ด้วย Poor…", { exact: true })
  ).toBeVisible()
  // The previous compare view, text and metadata stay visible while waiting.
  await expect(panel.getByText("Hello OCR text", { exact: true })).toBeVisible()
  await expect(panel.getByText("Vision OK ·", { exact: false })).toBeVisible()
  await expect(
    panel.getByRole("button", { name: "OCR ใหม่", exact: true })
  ).toBeDisabled()
  held.release()
  await expect(panel.getByText("Poor ·", { exact: false })).toBeVisible()
  await expect(panel.getByText("Hello OCR text")).toHaveCount(0)
  await expect(panel.getByText("OCR · e2e-ocr-poor")).toBeVisible()
  // A poor OCR text is not judged: only the parser summary, page counts as OCR'd.
  await expect(
    panel
      .getByRole("table", { name: "เทียบผลเดิมกับ OCR" })
      .getByText("ไม่ผ่าน 1 ข้อ")
  ).toHaveCount(1)
  await expect(
    page.getByRole("button", { name: "หน้า 2 OCR แล้ว", exact: true })
  ).toBeVisible()

  await setDefault(page, broken.id)
  await panel.getByRole("button", { name: "OCR ใหม่", exact: true }).click()
  await expect(panel.getByText("OCR ใหม่ไม่สำเร็จ")).toBeVisible()
  await expect(
    panel.getByText("ยังเก็บผล OCR เดิมไว้ · ลองอีกครั้งได้")
  ).toBeVisible()
  await expect(panel.getByText("Poor ·", { exact: false })).toBeVisible()
  await expect(panel.getByText("OCR แล้ว", { exact: true })).toBeVisible()
  await page.reload()
  await expect(panel.getByText("OCR · e2e-ocr-poor")).toBeVisible()
  expect(posts).toHaveLength(2)
})

for (const scenario of [
  {
    model: "e2e-timeout",
    message: "provider ไม่ตอบภายในเวลาที่กำหนด · ลองอีกครั้งได้",
  },
  {
    model: "e2e-unavailable",
    message: "provider ตอบกลับผิดพลาด · ลองอีกครั้งได้",
  },
  { model: "e2e-malformed", message: "ผล OCR ใช้งานไม่ได้ · ลองอีกครั้งได้" },
]) {
  test(`provider failure ${scenario.model} shows the shared failed state and retries only on click`, async ({
    page,
  }) => {
    const id = await seed(page.request)
    await seedPreset(page.request, "Failing", { model_id: scenario.model })
    const posts = countOcrPosts(page, id)
    await page.goto(`/documents/${id}?page=2`)
    const panel = panelOf(page)
    await panel
      .getByRole("button", { name: "OCR หน้านี้", exact: true })
      .click()
    await expect(panel.getByText("OCR หน้า 2 ไม่สำเร็จ")).toBeVisible({
      timeout: 10000,
    })
    await expect(panel.getByText(scenario.message)).toBeVisible()
    await expect(panel.getByText("ข้อความจาก PDF · หน้า 2")).toBeVisible()
    expect(posts).toHaveLength(1)
    await page.waitForTimeout(500)
    expect(posts).toHaveLength(1) // never resent automatically
    if (scenario.model === "e2e-unavailable") {
      const list = (await (
        await page.request.get("/api/llm/presets")
      ).json()) as { id: string }[]
      await page.request.patch(`/api/llm/presets/${list[0].id}`, {
        data: { model_id: "e2e-ok" },
      })
      await panel
        .getByRole("button", { name: "ลองอีกครั้ง", exact: true })
        .click()
      await expect(
        panel.getByText("Hello OCR text", { exact: true })
      ).toBeVisible()
      expect(posts).toHaveLength(2)
    }
  })
}

test("no default preset links to LLM settings without calling OCR", async ({
  page,
}) => {
  const id = await seed(page.request)
  const posts = countOcrPosts(page, id)
  await page.goto(`/documents/${id}?page=2`)
  const panel = panelOf(page)
  await panel.getByRole("button", { name: "OCR หน้านี้", exact: true }).click()
  await expect(panel.getByText("ยังไม่มี LLM preset สำหรับ OCR")).toBeVisible()
  expect(posts).toHaveLength(0)
  const direct = await page.request.post(`/api/documents/${id}/ocr`, {
    data: { page: 2 },
  })
  expect(direct.status()).toBe(409)
  expect(await direct.json()).toEqual({
    code: "no_default_preset",
    error_code: "DOC_012",
  })
  await panel.getByRole("link", { name: "ไปตั้งค่า LLM presets" }).click()
  await expect(page).toHaveURL(/\/settings\?tab=llm$/)
  await expect(
    page.getByRole("tab", { name: "LLM Model", selected: true })
  ).toBeVisible()
})

test("a preset deleted while OCR is requested shows DOC_013; retry starts the normal flow again", async ({
  page,
}) => {
  const id = await seed(page.request)
  const preset = await seedPreset(page.request, "Short lived", {
    model_id: "e2e-ok",
  })
  const held = await holdRequest(page, `**/api/documents/${id}/ocr`, "POST")
  await page.goto(`/documents/${id}?page=2`)
  const panel = panelOf(page)
  await panel.getByRole("button", { name: "OCR หน้านี้", exact: true }).click()
  await held.received
  expect(
    (await page.request.delete(`/api/llm/presets/${preset.id}`)).status()
  ).toBe(204)
  held.release()
  await expect(panel.getByText("ไม่พบ LLM preset ที่เลือก")).toBeVisible()
  await expect(
    panel.getByText("preset อาจถูกลบไปแล้ว · ลองใหม่ด้วย preset เริ่มต้น")
  ).toBeVisible()
  await panel.getByRole("button", { name: "ลองอีกครั้ง", exact: true }).click()
  await expect(panel.getByText("ยังไม่มี LLM preset สำหรับ OCR")).toBeVisible()
})

test("preset loading failure, server error and lost connection are retried by the user", async ({
  page,
}) => {
  const id = await seed(page.request)
  await seedPreset(page.request, "Vision OK", { model_id: "e2e-ok" })
  let presetsFail = true
  await page.route("**/api/llm/presets", async (route) => {
    if (presetsFail)
      await route.fulfill({ status: 500, json: { error_code: "SYS_002" } })
    else await route.continue()
  })
  let mode: "server" | "network" | "malformed" | "pass" = "server"
  await page.route(`**/api/documents/${id}/ocr`, async (route) => {
    if (mode === "server")
      await route.fulfill({
        status: 500,
        json: { code: "internal_error", error_code: "SYS_002" },
      })
    else if (mode === "network") await route.abort("connectionreset")
    else if (mode === "malformed") await route.fulfill({ json: { page: 2 } })
    else await route.continue()
  })
  const posts = countOcrPosts(page, id)
  await page.goto(`/documents/${id}?page=2`)
  const panel = panelOf(page)
  const retry = panel.getByRole("button", { name: "ลองอีกครั้ง", exact: true })
  await panel.getByRole("button", { name: "OCR หน้านี้", exact: true }).click()
  await expect(panel.getByText("โหลดการตั้งค่า OCR ไม่สำเร็จ")).toBeVisible()
  expect(posts).toHaveLength(0)

  presetsFail = false
  await retry.click()
  await expect(panel.getByText("OCR ไม่สำเร็จ", { exact: true })).toBeVisible()
  await expect(
    panel.getByText("เกิดข้อผิดพลาด · กด “ลองอีกครั้ง” เพื่อสั่ง OCR ใหม่")
  ).toBeVisible()

  mode = "network"
  await retry.click()
  await expect(
    panel.getByText("การเชื่อมต่อขาดหาย · กด “ลองอีกครั้ง” เพื่อสั่ง OCR ใหม่")
  ).toBeVisible()

  mode = "malformed"
  await retry.click()
  await expect(
    panel.getByText("เกิดข้อผิดพลาด · กด “ลองอีกครั้ง” เพื่อสั่ง OCR ใหม่")
  ).toBeVisible()
  expect(posts).toHaveLength(3)

  mode = "pass"
  await retry.click()
  await expect(panel.getByText("Hello OCR text", { exact: true })).toBeVisible()
  expect(posts).toHaveLength(4)
})

test("changing page during OCR disables OCR elsewhere and the late result only updates its page", async ({
  page,
}) => {
  const id = await seed(page.request)
  await seedPreset(page.request, "Vision OK", { model_id: "e2e-ok" })
  const held = await holdRequest(page, `**/api/documents/${id}/ocr`, "POST")
  await page.goto(`/documents/${id}?page=2`)
  const panel = panelOf(page)
  await panel.getByRole("button", { name: "OCR หน้านี้", exact: true }).click()
  await held.received
  await page.getByRole("button", { name: "หน้าก่อนหน้า", exact: true }).click()
  await expect(panel.getByText("Hello PDF", { exact: true })).toBeVisible()
  await expect(
    panel.getByRole("button", { name: "OCR หน้านี้", exact: true })
  ).toBeDisabled()
  held.release()
  await expect(
    page.getByRole("button", { name: "หน้า 2 OCR แล้ว", exact: true })
  ).toBeVisible()
  await expect(
    panel.getByRole("heading", { name: "ข้อความจาก PDF · หน้า 1" })
  ).toBeVisible()
  await expect(
    panel.getByRole("button", { name: "OCR หน้านี้", exact: true })
  ).toBeEnabled()
  await page.getByRole("button", { name: "หน้าถัดไป", exact: true }).click()
  await expect(panel.getByText("Hello OCR text", { exact: true })).toBeVisible()
  expect(held.requests).toHaveLength(1)
})

test("compare view fits a mobile viewport", async ({ page }) => {
  const id = await seed(page.request)
  await seedPreset(page.request, "Vision OK", { model_id: "e2e-ok" })
  await page.request.post(`/api/documents/${id}/ocr`, { data: { page: 2 } })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`/documents/${id}?page=2`)
  await expect(
    panelOf(page).getByText("Hello OCR text", { exact: true })
  ).toBeVisible()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth
    )
  ).toBeTruthy()
  await page.screenshot({
    path: "test-results/document-ocr-mobile.png",
    fullPage: true,
  })
})
