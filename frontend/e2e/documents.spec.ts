import { test, expect } from "./support"
import type { Page } from "@playwright/test"

function blankPdf() {
  let content = "%PDF-1.4\n"
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> >>",
  ]
  const offsets = [0]
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(content))
    content += `${index + 1} 0 obj\n${object}\nendobj\n`
  })
  const xref = Buffer.byteLength(content)
  content += `xref\n0 4\n0000000000 65535 f \n${offsets
    .slice(1)
    .map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`)
    .join("")}trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(content)
}
const pdf = blankPdf()
const file = (name: string) => ({
  name,
  mimeType: "application/pdf",
  buffer: pdf,
})
const documentsUrl = "**/api/documents?*"

async function choose(page: Page, name: string) {
  await page.getByLabel("ไฟล์ PDF", { exact: true }).setInputFiles(file(name))
}

test("upload, refresh, open detail by id, reload and read exact original PDF", async ({
  page,
}) => {
  const name = `เอกสาร-${Date.now()}.pdf`
  await page.goto("/documents")
  await expect(
    page.getByRole("heading", { name: "เอกสารทั้งหมด" })
  ).toBeVisible()
  const before = (await (await page.request.get("/api/documents")).json()) as {
    total: number
  }
  const posts: string[] = []
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/documents"))
      posts.push(request.url())
  })
  await choose(page, name)
  expect(posts).toHaveLength(0)
  await page.getByRole("button", { name: "อัปโหลด", exact: true }).click()
  await expect(page.getByRole("link", { name, exact: true })).toBeVisible()
  expect(posts).toHaveLength(1)
  const after = (await (await page.request.get("/api/documents")).json()) as {
    total: number
  }
  expect(after.total).toBe(before.total + 1)
  await page.reload()
  const link = page.getByRole("link", { name, exact: true })
  const href = await link.getAttribute("href")
  await link.click()
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText("ข้อความจาก PDF · หน้า 1")).toBeVisible()
  const originalLink = page.getByRole("link", { name: "เปิด PDF ต้นฉบับ" })
  const original = await page.request.get(
    (await originalLink.getAttribute("href"))!
  )
  expect(original.headers()["content-type"]).toBe("application/pdf")
  expect(await original.body()).toEqual(pdf)
  await page.goto("/settings")
  await page.getByRole("link", { name: "เอกสาร", exact: true }).click()
  await expect(page.getByRole("link", { name, exact: true })).toHaveAttribute(
    "href",
    href!
  )
  await page.screenshot({
    path: "test-results/documents-desktop.png",
    fullPage: true,
  })
})

test("client validation, corrupt PDF response, reset input and select the same file again", async ({
  page,
}) => {
  await page.goto("/documents")
  const input = page.getByLabel("ไฟล์ PDF", { exact: true })
  await input.setInputFiles({
    name: "text.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("hello"),
  })
  await expect(page.getByRole("alert")).toHaveText(
    "รองรับเฉพาะไฟล์ PDF เท่านั้น"
  )
  await input.setInputFiles({
    name: "big.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.alloc(20 * 1024 * 1024 + 1),
  })
  await expect(page.getByRole("alert")).toHaveText("ไฟล์ใหญ่เกิน 20 MB")
  const broken = {
    name: "broken.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\nbroken"),
  }
  await input.setInputFiles(broken)
  await expect(page.getByRole("alert")).toHaveCount(0)
  await page.getByRole("button", { name: "อัปโหลด", exact: true }).click()
  await expect(page.getByRole("alert")).toContainText(
    "ไฟล์อาจเสียหรือมีรหัสผ่าน"
  )
  await expect(input).toHaveValue("")
  await expect(
    page.getByRole("button", { name: "อัปโหลด", exact: true })
  ).toHaveCount(0)
  await input.setInputFiles(broken)
  await expect(
    page.getByRole("button", { name: "อัปโหลด", exact: true })
  ).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
})

test("drop multiple files is rejected and a single drop only selects", async ({
  page,
}) => {
  await page.goto("/documents")
  const dropzone = page.getByText("ลากไฟล์ PDF มาวางที่นี่ หรือ")
  const files = await page.evaluateHandle(() => {
    const data = new DataTransfer()
    data.items.add(new File(["a"], "a.pdf", { type: "application/pdf" }))
    data.items.add(new File(["b"], "b.pdf", { type: "application/pdf" }))
    return data
  })
  await dropzone.dispatchEvent("drop", { dataTransfer: files })
  await expect(page.getByRole("alert")).toHaveText("อัปโหลดได้ครั้งละ 1 ไฟล์")
  await files.dispose()
  const single = await page.evaluateHandle(() => {
    const data = new DataTransfer()
    data.items.add(new File(["a"], "a.pdf", { type: "application/pdf" }))
    return data
  })
  await dropzone.dispatchEvent("drop", { dataTransfer: single })
  await expect(
    page.getByRole("button", { name: "อัปโหลด", exact: true })
  ).toBeVisible()
  await expect(page.getByRole("alert")).toHaveCount(0)
  await single.dispose()
})

test("pending upload is locked; failure clears file and never retries automatically", async ({
  page,
}) => {
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  let posts = 0
  await page.route("**/api/documents", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue()
      return
    }
    posts++
    await gate
    await route.fulfill({ status: 500, json: { error_code: "SYS_002" } })
  })
  await page.goto("/documents")
  await choose(page, "pending.pdf")
  await page.getByRole("button", { name: "อัปโหลด", exact: true }).click()
  await expect(
    page.getByText("กรุณาเปิดหน้านี้ไว้จนกว่าจะบันทึกสำเร็จ")
  ).toBeVisible()
  await expect(page.getByLabel("ไฟล์ PDF", { exact: true })).toBeDisabled()
  await expect(
    page.getByRole("button", { name: "อัปโหลด", exact: true })
  ).toHaveCount(0)
  release()
  await expect(page.getByRole("alert")).toContainText("อัปโหลดไม่สำเร็จ")
  await expect(
    page.getByRole("button", { name: "เลือกไฟล์", exact: true })
  ).toBeVisible()
  await expect(page.getByLabel("ไฟล์ PDF", { exact: true })).toHaveValue("")
  expect(posts).toBe(1)
})

test("loading, empty, list failure and explicit retry", async ({ page }) => {
  let release!: () => void
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  let failing = true
  await page.route(documentsUrl, async (route) => {
    if (failing) {
      await gate
      await route.fulfill({ status: 500, json: { error_code: "SYS_002" } })
      return
    }
    await route.fulfill({ json: { items: [], total: 0 } })
  })
  await page.goto("/documents")
  await expect(
    page.getByRole("status", { name: "กำลังโหลดรายการ" })
  ).toBeVisible()
  release()
  await expect(page.getByRole("alert")).toHaveText("โหลดรายการไม่สำเร็จ")
  failing = false
  await page.getByRole("button", { name: "ลองอีกครั้ง", exact: true }).click()
  await expect(page.getByText("ยังไม่มีเอกสาร", { exact: true })).toBeVisible()
  await expect(page.getByRole("table")).toHaveCount(0)
  await expect(page.getByRole("button", { name: "ถัดไป" })).toHaveCount(0)
})

test("real persisted documents paginate newest first", async ({ page }) => {
  for (let n = 0; n < 21; n++) {
    const response = await page.request.post("/api/documents", {
      multipart: {
        file: {
          name: `pagination-${n}.pdf`,
          mimeType: "application/pdf",
          buffer: pdf,
        },
      },
    })
    expect(response.status()).toBe(201)
  }
  await page.goto("/documents")
  await expect(
    page.getByRole("link", { name: "pagination-20.pdf", exact: true })
  ).toBeVisible()
  await expect(page.getByRole("button", { name: "ก่อนหน้า" })).toBeDisabled()
  await page.getByRole("button", { name: "ถัดไป" }).click()
  await expect(
    page.getByRole("link", { name: "pagination-0.pdf", exact: true })
  ).toBeVisible()
  await expect(page.getByRole("button", { name: "ถัดไป" })).toBeDisabled()
  await page.getByRole("button", { name: "ก่อนหน้า" }).click()
  await expect(
    page.getByRole("link", { name: "pagination-20.pdf", exact: true })
  ).toBeVisible()
})

test("missing detail and mobile upload navigation", async ({ page }) => {
  await page.goto("/documents/00000000-0000-0000-0000-000000000001")
  await expect(page.getByRole("heading", { name: "ไม่พบเอกสาร" })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.getByRole("link", { name: "กลับไปเอกสารทั้งหมด" }).click()
  const name = `mobile-${Date.now()}.pdf`
  await choose(page, name)
  await page.getByRole("button", { name: "อัปโหลด", exact: true }).click()
  await page.getByRole("link", { name, exact: true }).click()
  await expect(page.getByRole("heading", { name, exact: true })).toBeVisible()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth
    )
  ).toBeTruthy()
  await page.screenshot({
    path: "test-results/document-upload-mobile.png",
    fullPage: true,
  })
})
