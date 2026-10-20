import { test, expect, openPresets, openCreate, fillPreset, seedPreset, editPreset, holdRequest, provider } from './support'

test('new credentials pass through the API and adapter and display provider success', async ({ page }) => {
  await openPresets(page)
  const dialog = await openCreate(page)
  await fillPreset(page)
  await dialog.getByLabel('ชื่อ preset', { exact: true }).fill('')
  await expect(dialog.getByRole('button', { name: 'บันทึก preset', exact: true })).toBeDisabled()
  await dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
  await expect(dialog.getByText('เชื่อมต่อสำเร็จ', { exact: true })).toBeVisible()
  await expect(dialog.getByRole('status')).toContainText(/e2e-ok ตอบกลับใน \d+ ms/)
  expect((await (await page.request.get('/api/llm/presets')).json())).toEqual([])
})

for (const scenario of [
  { name: 'wrong key', model: 'e2e-ok', key: 'incorrect-key', field: 'API key', message: 'API key ไม่ถูกต้อง หรือไม่มีสิทธิ์ใช้งาน (401)' },
  { name: 'missing model', model: 'e2e-missing', key: 'e2e-key', field: 'Model ID', message: 'ไม่พบโมเดล “e2e-missing” ที่ provider นี้ (404)' },
  { name: 'wrong endpoint', model: 'e2e-ok', key: 'e2e-key', field: 'Base URL', message: 'เชื่อมต่อไม่ได้ หรือไม่ตอบกลับภายใน 10 วินาที' },
  { name: 'rate limit', model: 'e2e-rate-limit', key: 'e2e-key', field: null, message: 'provider ตอบกลับ 429' },
  { name: 'unavailable', model: 'e2e-unavailable', key: 'e2e-key', field: null, message: 'provider ตอบกลับ 503' },
  { name: 'malformed', model: 'e2e-malformed', key: 'e2e-key', field: 'Base URL', message: 'เชื่อมต่อไม่ได้ หรือไม่ตอบกลับภายใน 10 วินาที' },
  { name: 'timeout', model: 'e2e-timeout', key: 'e2e-key', field: 'Base URL', message: 'เชื่อมต่อไม่ได้ หรือไม่ตอบกลับภายใน 10 วินาที' },
]) {
  test(`provider ${scenario.name} produces the appropriate field feedback without blocking save`, async ({ page }) => {
    await openPresets(page)
    const dialog = await openCreate(page)
    await fillPreset(page)
    await dialog.getByLabel('Model ID', { exact: true }).fill(scenario.model)
    await dialog.getByLabel('API key', { exact: true }).fill(scenario.key)
    if (scenario.name === 'wrong endpoint') await dialog.getByLabel('Base URL', { exact: true }).fill('https://unconfigured.invalid/v1')
    await dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
    await expect(dialog.getByRole('status')).toContainText(scenario.message, { timeout: scenario.name === 'timeout' ? 15000 : 5000 })
    if (scenario.field) {
      await expect(dialog.getByLabel(scenario.field, { exact: true })).toHaveAttribute('aria-invalid', 'true')
      await expect(dialog.getByLabel(scenario.field, { exact: true })).toHaveAccessibleDescription(new RegExp(scenario.message.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')))
    } else {
      for (const field of ['ชื่อ preset', 'Model ID', 'Base URL', 'API key']) await expect(dialog.getByLabel(field, { exact: true })).toHaveAttribute('aria-invalid', 'false')
    }
    await expect(dialog.getByRole('button', { name: 'บันทึก preset', exact: true })).toBeEnabled()
    expect(await (await page.request.get('/api/llm/presets')).json()).toEqual([])
  })
}

test('editing tests saved credentials and temporary overrides without persisting them; menu tests the saved model', async ({ page }) => {
  const preset = await seedPreset(page.request, 'Saved model')
  await openPresets(page)
  const dialog = await editPreset(page, preset.name)
  const key = dialog.getByLabel('API key', { exact: true })
  await expect(key).toHaveValue('')
  await dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
  await expect(dialog.getByRole('status')).toContainText('เชื่อมต่อสำเร็จ · ใช้ API key ที่บันทึกไว้')
  await dialog.getByLabel('Model ID', { exact: true }).fill('e2e-ok-alias')
  await dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
  await expect(dialog.getByRole('status')).toContainText(/e2e-ok-alias ตอบกลับใน \d+ ms/)
  expect(await (await page.request.get('/api/llm/presets')).json()).toEqual([preset])
  await dialog.getByRole('button', { name: 'ยกเลิก', exact: true }).click()
  await page.getByRole('button', { name: 'เมนู Saved model', exact: true }).click()
  await page.getByRole('menuitem', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
  await expect(page.getByText('Saved model เชื่อมต่อสำเร็จ', { exact: true })).toBeVisible()
  await expect(page.getByText(/e2e-ok ตอบกลับใน \d+ ms/)).toBeVisible()
})

test('replacing an API key is write-only and used by subsequent blank-key tests', async ({ page }) => {
  await seedPreset(page.request, 'Rotate key')
  await openPresets(page)
  const dialog = await editPreset(page, 'Rotate key')
  await dialog.getByLabel('Model ID', { exact: true }).fill('e2e-rotated')
  await dialog.getByLabel('API key', { exact: true }).fill('rotated-key')
  await dialog.getByRole('button', { name: 'บันทึกการแก้ไข', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await editPreset(page, 'Rotate key')
  await expect(dialog.getByLabel('API key', { exact: true })).toHaveValue('')
  await dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
  await expect(dialog.getByRole('status')).toContainText('เชื่อมต่อสำเร็จ · ใช้ API key ที่บันทึกไว้')
  const response = await page.request.get('/api/llm/presets')
  expect(await response.text()).not.toContain('rotated-key')
  expect(await response.text()).not.toContain('api_key')
})

test('editing a field invalidates a connection result that is still in flight', async ({ page }) => {
  await openPresets(page)
  const dialog = await openCreate(page)
  await fillPreset(page)
  const held = await holdRequest(page, '**/api/llm/presets/test', 'POST')
  try {
    await dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
    await held.received
    await expect(dialog.getByRole('button', { name: 'กำลังทดสอบ…', exact: true })).toBeDisabled()
    await dialog.getByLabel('Model ID', { exact: true }).fill('edited-while-testing')
    const response = page.waitForResponse(r => r.url().endsWith('/llm/presets/test'))
    held.release()
    await response
    await expect(dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true })).toBeEnabled()
    await expect(dialog.getByRole('status')).toHaveCount(0)
    await expect(dialog.getByLabel('Model ID', { exact: true })).toHaveValue('edited-while-testing')
    expect(held.requests).toHaveLength(1)
  } finally { held.release() }
})

test('saving stays available while testing and closing the saved dialog ignores late results', async ({ page }) => {
  await openPresets(page)
  const dialog = await openCreate(page)
  await fillPreset(page, 'Saved during test')
  const held = await holdRequest(page, '**/api/llm/presets/test', 'POST')
  try {
    await dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
    await held.received
    await expect(dialog.getByRole('button', { name: 'บันทึก preset', exact: true })).toBeEnabled()
    await dialog.getByRole('button', { name: 'บันทึก preset', exact: true }).click()
    await expect(dialog).not.toBeVisible()
    await expect(page.getByRole('radio', { name: 'ตั้ง Saved during test เป็น default' })).toBeChecked()
    const response = page.waitForResponse(r => r.url().endsWith('/llm/presets/test'))
    held.release()
    await response
    await expect(page.getByRole('dialog')).not.toBeVisible()
    await expect(page.getByText('เชื่อมต่อสำเร็จ', { exact: true })).not.toBeVisible()
  } finally { held.release() }
})

test('connection API failure keeps the draft for retry and missing saved preset refreshes the list', async ({ page }) => {
  const preset = await seedPreset(page.request, 'Transient')
  await openPresets(page)
  const dialog = await editPreset(page, preset.name)
  let failing = true
  await page.route('**/api/llm/presets/' + preset.id + '/test', async route => {
    if (failing) await route.fulfill({ status: 500, json: { error_code: 'SYS_002' } })
    else await route.continue()
  })
  await dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
  await expect(dialog.getByRole('alert')).toHaveText('ทดสอบไม่สำเร็จ ลองอีกครั้ง')
  await expect(dialog.getByLabel('Model ID', { exact: true })).toHaveValue(provider.model_id)
  failing = false
  await dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
  await expect(dialog.getByRole('status')).toContainText('เชื่อมต่อสำเร็จ')
  await page.request.delete('/api/llm/presets/' + preset.id)
  await dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByText('ไม่พบ preset นี้ (อาจถูกลบแล้ว)', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'ยังไม่มี preset' })).toBeVisible()
})
