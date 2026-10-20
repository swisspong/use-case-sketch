import { test, expect, baseline } from "./support"
import { seed, twoPagePdf } from "./documents-support"

test("real viewer, snapshot, per-page quality, zoom, copy and browser history", async ({
  page,
  context,
}) => {
  const id = await seed(page.request)
  await page.request.patch("/api/text-quality/thresholds", { data: baseline })
  let fileRequests = 0
  page.on("request", (r) => {
    if (r.url().endsWith(`/${id}/file`)) fileRequests++
  })
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await page.goto(`/documents/${id}?page=1`)
  await expect(
    page.getByRole("heading", { name: "รายละเอียด.pdf" })
  ).toBeVisible()
  const panel = page.getByRole("region", { name: "ผลตรวจคุณภาพรายหน้า" })
  await expect(panel.getByText("ผ่านเกณฑ์", { exact: true })).toBeVisible()
  await expect(panel.getByText("เกณฑ์ ≤ 0%", { exact: true })).toBeVisible()
  await expect(panel.getByText("Hello PDF", { exact: true })).toBeVisible()
  await expect(page.getByLabel("PDF หน้า 1", { exact: true })).toBeVisible()
  await expect(
    page.getByRole("button", { name: "หน้า 1 ผ่านเกณฑ์", exact: true })
  ).toHaveAttribute("aria-current", "page")
  await page.getByRole("button", { name: "คัดลอกข้อความ" }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(
    "Hello PDF"
  )
  await page.getByRole("button", { name: "ขยาย PDF" }).click()
  await expect(page.getByLabel("ระดับซูม")).toHaveText("125%")
  await page.getByRole("button", { name: "หน้าถัดไป", exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`${id}\\?page=2$`))
  await expect(page.getByLabel("PDF หน้า 2", { exact: true })).toBeVisible()
  await expect(
    panel.getByText("ไม่พบข้อความในหน้านี้", { exact: true })
  ).toBeVisible()
  await expect(panel.getByText("ไม่ผ่านเกณฑ์ 1 จาก 4 ข้อ")).toBeVisible()
  await page.goBack()
  await expect(panel.getByText("Hello PDF", { exact: true })).toBeVisible()
  await page.goForward()
  await expect(
    panel.getByText("ไม่พบข้อความในหน้านี้", { exact: true })
  ).toBeVisible()
  await page.getByLabel("เลขหน้า", { exact: true }).fill("1")
  await page.getByLabel("เลขหน้า", { exact: true }).press("Enter")
  await expect(panel.getByText("Hello PDF", { exact: true })).toBeVisible()
  expect(fileRequests).toBe(1)
  await page.screenshot({
    path: "test-results/document-detail-desktop.png",
    fullPage: true,
  })
  await page.reload()
  await expect(panel.getByText("Hello PDF", { exact: true })).toBeVisible()
})

test("pending and failed page results leave viewer usable; late responses are discarded", async ({
  page,
}) => {
  const id = await seed(page.request)
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  let fail = true
  await page.route(`**/api/documents/${id}/pages/2`, async (route) => {
    if (fail) {
      await gate
      await route.fulfill({ status: 500, json: { error_code: "SYS_002" } })
    } else await route.continue()
  })
  await page.goto(`/documents/${id}`)
  await expect(page.getByText("Hello PDF", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "หน้าถัดไป", exact: true }).click()
  await expect(
    page.getByRole("status", { name: "กำลังโหลดผลรายหน้า" })
  ).toBeVisible()
  await expect(page.getByLabel("PDF หน้า 2", { exact: true })).toBeVisible()
  await page.getByRole("button", { name: "หน้าก่อนหน้า", exact: true }).click()
  release()
  await expect(page.getByText("Hello PDF", { exact: true })).toBeVisible()
  await expect(
    page.getByText("โหลดผลของหน้านี้ไม่สำเร็จ", { exact: true })
  ).toHaveCount(0)
  await page.getByRole("button", { name: "หน้าถัดไป", exact: true }).click()
  await expect(
    page.getByText("โหลดผลของหน้านี้ไม่สำเร็จ", { exact: true })
  ).toBeVisible()
  fail = false
  await page.getByRole("button", { name: "ลองอีกครั้ง", exact: true }).click()
  await expect(
    page.getByText("ไม่พบข้อความในหน้านี้", { exact: true })
  ).toBeVisible()
})

test("bad page URL resets to 1; PDF retries preserve results and mobile fits", async ({
  page,
}) => {
  const id = await seed(page.request)
  let fail = true
  await page.route(`**/api/documents/${id}/file`, async (route) => {
    if (fail)
      await route.fulfill({ status: 500, json: { error_code: "SYS_002" } })
    else await route.continue()
  })
  await page.goto(`/documents/${id}?page=999`)
  await expect(page).toHaveURL(new RegExp(`${id}\\?page=1$`))
  await expect(page.getByText("Hello PDF", { exact: true })).toBeVisible()
  await expect(
    page.getByText("โหลด PDF ไม่สำเร็จ", { exact: true })
  ).toBeVisible()
  fail = false
  await page.getByRole("button", { name: "ลองโหลด PDF อีกครั้ง" }).click()
  await expect(page.getByLabel("PDF หน้า 1", { exact: true })).toBeVisible()
  await page.goto(`/documents/${id}?page=invalid`)
  await expect(page).toHaveURL(new RegExp(`${id}\\?page=1$`))
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByText("Hello PDF", { exact: true })).toBeVisible()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth
    )
  ).toBeTruthy()
  await expect(page.getByLabel("PDF หน้า 1", { exact: true })).toBeVisible()
  await expect(
    page.getByText("ไม่พบหน้าที่ระบุ", { exact: true })
  ).not.toBeVisible({ timeout: 6000 })
  await page.screenshot({
    path: "test-results/document-detail-mobile.png",
    fullPage: true,
  })
})

test("a stalled PDF load times out independently and can be retried", async ({
  page,
}) => {
  const id = await seed(page.request)
  await page.clock.install()
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  let arrived!: () => void
  const received = new Promise<void>((resolve) => {
    arrived = resolve
  })
  let first = true
  await page.route(`**/api/documents/${id}/file`, async (route) => {
    if (first) {
      first = false
      arrived()
      await gate
      await route.fulfill({ status: 500, body: "timeout" })
    } else await route.continue()
  })
  await page.goto(`/documents/${id}`)
  await expect(page.getByText("Hello PDF", { exact: true })).toBeVisible()
  await received
  await page.clock.fastForward(25001)
  await expect(
    page.getByText("โหลด PDF ไม่สำเร็จ", { exact: true })
  ).toBeVisible()
  release()
  await page.getByRole("button", { name: "ลองโหลด PDF อีกครั้ง" }).click()
  await expect(page.getByLabel("PDF หน้า 1", { exact: true })).toBeVisible()
  await page.clock.fastForward(30000)
  await expect(
    page.getByText("โหลด PDF ไม่สำเร็จ", { exact: true })
  ).toHaveCount(0)
})

for (const scenario of [
  {
    name: "Thai above maximum",
    changes: { max_thai_percent: 50, max_garbled_thai_percent: 100 },
    failed: ["max_thai_percent"],
    reason: "ภาษาไทยมากกว่าเกณฑ์",
  },
  {
    name: "v3 detects Latin substitutions",
    changes: { max_thai_percent: 100, max_garbled_thai_percent: 24 },
    failed: ["max_garbled_thai_percent"],
    reason: "มีสระ/วรรณยุกต์ลอยหรืออักขระที่อ่านไม่ได้",
  },
  {
    name: "exact Thai and garbled thresholds pass",
    changes: { max_thai_percent: 75, max_garbled_thai_percent: 25 },
    failed: [],
    reason: "",
  },
]) {
  test(scenario.name, async ({ page }) => {
    const thresholds = { ...baseline, ...scenario.changes, min_text_chars: 8 }
    await page.request.patch("/api/text-quality/thresholds", {
      data: thresholds,
    })
    const response = await page.request.post("/api/documents", {
      multipart: {
        file: {
          name: "ไทย.pdf",
          mimeType: "application/pdf",
          buffer: twoPagePdf("ABC DEF", {
            A: "ท",
            B: "ี",
            D: "เ",
            E: "ช",
            F: "ืMอ",
          }),
        },
      },
    })
    expect(response.status()).toBe(201)
    const { document: doc } = (await response.json()) as {
      document: { id: string; ocr_suggested_count: number }
    }
    expect(doc.ocr_suggested_count).toBe(scenario.failed.length ? 2 : 1)
    const result = (await (
      await page.request.get(`/api/documents/${doc.id}/pages/1`)
    ).json()) as {
      parser: {
        text: string
        quality: { failed: string[]; garbled_thai_percent: number }
      }
    }
    expect(result.parser.text.trim()).toBe("ทีC เชืMอ")
    expect(result.parser.quality.garbled_thai_percent).toBe(25)
    expect(result.parser.quality.failed).toEqual(scenario.failed)
    await page.goto(`/documents/${doc.id}`)
    const panel = page.getByRole("region", { name: "ผลตรวจคุณภาพรายหน้า" })
    await expect(panel.getByText("ทีC เชืMอ", { exact: true })).toBeVisible()
    await expect(
      panel.getByText(`เกณฑ์ ≤ ${thresholds.max_thai_percent}%`, {
        exact: true,
      })
    ).toBeVisible()
    if (scenario.failed.length) {
      await expect(
        panel.getByText("ไม่ผ่านเกณฑ์ 1 จาก 4 ข้อ", { exact: true })
      ).toBeVisible()
      await expect(
        panel.getByText(scenario.reason, { exact: false })
      ).toBeVisible()
    } else
      await expect(panel.getByText("ผ่านเกณฑ์", { exact: true })).toBeVisible()
  })
}

test("historical minimum-Thai snapshots keep their original labels and decisions", async ({
  page,
}) => {
  const id = await seed(page.request)
  await page.route(`**/api/documents/${id}/pages/1`, async (route) => {
    await route.fulfill({
      json: {
        number: 1,
        thresholds: {
          min_thai_percent: 50,
          max_garbled_thai_percent: 5,
          min_text_chars: 1,
          max_image_percent: 80,
        },
        parser: {
          text: "historical text",
          quality: {
            thai_percent: 38,
            garbled_thai_percent: 0,
            text_chars: 14,
            image_percent: 0,
            failed: ["min_thai_percent"],
            passed: false,
          },
        },
        ocr: null,
      },
    })
  })
  await page.goto(`/documents/${id}`)
  const panel = page.getByRole("region", { name: "ผลตรวจคุณภาพรายหน้า" })
  await expect(
    panel.getByText("ผลตรวจตามเกณฑ์เดิม", { exact: false })
  ).toBeVisible()
  await expect(panel.getByText("เกณฑ์ ≥ 50%", { exact: true })).toBeVisible()
  await expect(
    panel.getByText("ภาษาไทยน้อยกว่าเกณฑ์", { exact: false })
  ).toBeVisible()
})

test("pdf.js decoders, cmaps and fonts are served at the paths the viewer loads", async ({
  request,
}) => {
  // Scanned PDFs (JBIG2/JPX) render blank if these fall back to index.html.
  for (const path of [
    "/pdfjs/wasm/jbig2.wasm",
    "/pdfjs/wasm/openjpeg.wasm",
    "/pdfjs/cmaps/Adobe-Japan1-UCS2.bcmap",
    "/pdfjs/standard_fonts/FoxitDingbats.pfb",
  ]) {
    const response = await request.get(path)
    expect(response.ok(), path).toBe(true)
    expect(response.headers()["content-type"] ?? "", path).not.toContain(
      "text/html"
    )
  }
})
