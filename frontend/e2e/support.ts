import { test as base, expect, type APIRequestContext, type Page, type Request } from '@playwright/test'

export const baseline = { max_thai_percent: 50, max_garbled_thai_percent: 5, min_text_chars: 50, max_image_percent: 80 }
export const qualityFields = [
  { key: 'max_thai_percent', label: 'สัดส่วนภาษาไทย', percent: true },
  { key: 'max_garbled_thai_percent', label: 'ข้อความที่อ่านไม่รู้เรื่อง', percent: true },
  { key: 'min_text_chars', label: 'ข้อความน้อยเกินไป', percent: false },
  { key: 'max_image_percent', label: 'รูปภาพในหน้า', percent: true },
] as const

export const provider = { base_url: 'https://e2e-provider.invalid/v1', model_id: 'e2e-ok', api_key: 'e2e-key' }
export type Preset = { id: string; name: string; model_id: string; base_url: string; is_default: boolean }

export const test = base.extend({
  page: async ({ page }, runWithPage) => {
    const reset = await page.request.patch('/api/text-quality/thresholds', { data: baseline })
    expect(reset.ok()).toBeTruthy()
    const list = await page.request.get('/api/llm/presets')
    expect(list.ok()).toBeTruthy()
    for (const preset of await list.json() as Preset[]) {
      expect((await page.request.delete('/api/llm/presets/' + preset.id)).status()).toBe(204)
    }
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    await runWithPage(page)
    expect(errors, 'unhandled browser errors').toEqual([])
  },
})
export { expect }

export async function seedPreset(request: APIRequestContext, name: string, changes: Partial<typeof provider> = {}): Promise<Preset> {
  const response = await request.post('/api/llm/presets', { data: { name, ...provider, ...changes } })
  expect(response.status()).toBe(201)
  return response.json()
}

export async function openPresets(page: Page) {
  await page.goto('/')
  await page.getByRole('tab', { name: 'LLM Model', exact: true }).click()
}

export async function openCreate(page: Page) {
  await page.getByRole('button', { name: 'เพิ่ม preset', exact: true }).first().click()
  return page.getByRole('dialog')
}

export async function editPreset(page: Page, name: string) {
  await page.getByRole('button', { name: 'เมนู ' + name, exact: true }).click()
  await page.getByRole('menuitem', { name: 'แก้ไข', exact: true }).click()
  return page.getByRole('dialog')
}

export async function fillPreset(page: Page, name = 'Test model') {
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('ชื่อ preset', { exact: true }).fill(name)
  await dialog.getByLabel('Model ID', { exact: true }).fill(provider.model_id)
  await dialog.getByLabel('Base URL', { exact: true }).fill(provider.base_url)
  await dialog.getByLabel('API key', { exact: true }).fill(provider.api_key)
}

export async function holdRequest(page: Page, pattern: string, method: string) {
  let release!: () => void
  let arrived!: (request: Request) => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const received = new Promise<Request>(resolve => { arrived = resolve })
  const requests: Request[] = []
  await page.route(pattern, async route => {
    if (route.request().method() !== method) { await route.continue(); return }
    requests.push(route.request())
    arrived(route.request())
    await gate
    await route.continue()
  })
  return { release, received, requests }
}
