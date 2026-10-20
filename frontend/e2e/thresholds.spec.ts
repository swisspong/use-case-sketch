import { test, expect, baseline, qualityFields, holdRequest } from './support'

for (const field of qualityFields) {
  test(`${field.key}: reject invalid edits without requests and persist boundary values`, async ({ page }) => {
    await page.goto('/')
    const input = page.getByRole('spinbutton', { name: field.label, exact: true })
    await expect(input).toHaveValue(String(baseline[field.key]))
    const save = page.getByRole('button', { name: 'บันทึก', exact: true })
    const patches: unknown[] = []
    page.on('request', request => {
      if (request.method() === 'PATCH') patches.push(request.postDataJSON())
    })
    for (const value of ['', '-1', '1.5', ...(field.percent ? ['101'] : [])]) {
      await input.fill(value)
      await expect(input).toHaveAttribute('aria-invalid', 'true')
      await expect(save).toBeDisabled()
      await expect(input).toHaveAccessibleDescription(new RegExp(field.percent ? 'ต้องเป็นจำนวนเต็ม 0–100' : 'ต้องเป็นจำนวนเต็มตั้งแต่ 0 ขึ้นไป'))
    }
    expect(patches).toEqual([])
    for (const value of ['0', field.percent ? '100' : '1000']) {
      await input.fill(value)
      await expect(input).toHaveAttribute('aria-invalid', 'false')
      await save.click()
      await expect(save).toBeDisabled()
      await expect(page.getByText('บันทึกการตั้งค่าแล้ว', { exact: true })).toBeVisible()
      await page.reload()
      await expect(input).toHaveValue(value)
    }
    expect(patches).toEqual([{ [field.key]: 0 }, { [field.key]: field.percent ? 100 : 1000 }])
  })
}

test('all four changes persist together and restoring the snapshot sends nothing', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('spinbutton').first()).toBeVisible()
  const patches: unknown[] = []
  page.on('request', request => { if (request.method() === 'PATCH') patches.push(request.postDataJSON()) })
  const save = page.getByRole('button', { name: 'บันทึก', exact: true })
  const thai = page.getByRole('spinbutton', { name: 'สัดส่วนภาษาไทย', exact: true })
  await thai.fill('51')
  await thai.fill('50')
  await expect(save).toBeDisabled()
  expect(patches).toEqual([])
  const values = ['61', '8', '123', '79']
  for (const [index, field] of qualityFields.entries()) await page.getByRole('spinbutton', { name: field.label, exact: true }).fill(values[index])
  await save.click()
  await expect(save).toBeDisabled()
  await expect(page.getByText('บันทึกการตั้งค่าแล้ว', { exact: true })).toBeVisible()
  await page.reload()
  for (const [index, field] of qualityFields.entries()) await expect(page.getByRole('spinbutton', { name: field.label, exact: true })).toHaveValue(values[index])
  expect(patches).toEqual([{ max_thai_percent: 61, max_garbled_thai_percent: 8, min_text_chars: 123, max_image_percent: 79 }])
})

test('percentage sliders update numeric inputs by keyboard and pointer', async ({ page }) => {
  await page.goto('/')
  for (const field of qualityFields.filter(field => field.percent)) {
    const slider = page.getByRole('slider', { name: field.label, exact: true })
    const input = page.getByRole('spinbutton', { name: field.label, exact: true })
    await slider.focus()
    await slider.press('ArrowRight')
    await expect(input).toHaveValue(String(baseline[field.key] + 1))
    await slider.press('Home')
    await expect(input).toHaveValue('0')
    const track = slider.locator('xpath=ancestor::*[@data-slot="slider"]')
    const bounds = await track.boundingBox()
    expect(bounds).not.toBeNull()
    await page.mouse.click(bounds!.x + bounds!.width * 0.7, bounds!.y + bounds!.height / 2)
    await expect.poll(async () => Number(await input.inputValue())).toBeGreaterThan(60)
    await expect.poll(async () => Number(await input.inputValue())).toBeLessThan(80)
    const thumb = await slider.boundingBox()
    expect(thumb).not.toBeNull()
    await page.mouse.move(thumb!.x + thumb!.width / 2, thumb!.y + thumb!.height / 2)
    await page.mouse.down()
    await page.mouse.move(bounds!.x + bounds!.width * 0.3, bounds!.y + bounds!.height / 2, { steps: 5 })
    await page.mouse.up()
    await expect.poll(async () => Number(await input.inputValue())).toBeGreaterThan(20)
    await expect.poll(async () => Number(await input.inputValue())).toBeLessThan(40)
  }
})

test('loading hides values until the response and displays server defaults', async ({ page }) => {
  const held = await holdRequest(page, '**/api/text-quality/thresholds', 'GET')
  try {
    await page.goto('/')
    await held.received
    await expect(page.getByLabel('กำลังโหลดค่า')).toHaveCount(4)
    await expect(page.getByRole('spinbutton')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'บันทึก', exact: true })).toBeDisabled()
    held.release()
    const data = await (await page.request.get('/api/text-quality/thresholds')).json()
    expect(data.defaults).toEqual({ max_thai_percent: 43, max_garbled_thai_percent: 7, min_text_chars: 64, max_image_percent: 81 })
    for (const field of qualityFields) {
      await expect(page.getByRole('spinbutton', { name: field.label, exact: true })).toHaveValue(String(baseline[field.key]))
      await expect(page.getByText(`ค่าเริ่มต้น ${data.defaults[field.key]}${field.percent ? '%' : ' ตัวอักษร'}`, { exact: true })).toBeVisible()
    }
  } finally { held.release() }
})

test('saving locks controls, prevents duplicate submits and completes after changing tabs', async ({ page }) => {
  const held = await holdRequest(page, '**/api/text-quality/thresholds', 'PATCH')
  try {
    await page.goto('/')
    const input = page.getByRole('spinbutton', { name: 'สัดส่วนภาษาไทย', exact: true })
    await input.fill('66')
    await page.getByRole('button', { name: 'บันทึก', exact: true }).click()
    await held.received
    await expect(page.getByRole('button', { name: 'กำลังบันทึก…', exact: true })).toBeDisabled()
    for (const control of await page.getByRole('spinbutton').all()) await expect(control).toBeDisabled()
    await expect(page.getByRole('button', { name: 'ยกเลิก', exact: true })).toBeDisabled()
    await input.press('Enter')
    await page.getByRole('tab', { name: 'LLM Model', exact: true }).click()
    await expect(page.getByRole('alertdialog')).not.toBeVisible()
    held.release()
    await expect(page.getByText('บันทึกการตั้งค่าแล้ว', { exact: true })).toBeVisible()
    expect(held.requests).toHaveLength(1)
    await page.getByRole('tab', { name: 'เกณฑ์คุณภาพข้อความ', exact: true }).click()
    await expect(input).toHaveValue('66')
    await expect(page.getByRole('button', { name: 'บันทึก', exact: true })).toBeDisabled()
  } finally { held.release() }
})

test('server field error retains edits and focuses the invalid field after unlocking', async ({ page }) => {
  await page.route('**/api/text-quality/thresholds', async route => {
    if (route.request().method() === 'PATCH') await route.fulfill({ status: 422, json: { code: 'threshold_out_of_range', error_code: 'TQ_001', field: 'min_text_chars' } })
    else await route.continue()
  })
  await page.goto('/')
  const input = page.getByRole('spinbutton', { name: 'ข้อความน้อยเกินไป', exact: true })
  await input.fill('75')
  await page.getByRole('button', { name: 'บันทึก', exact: true }).click()
  await expect(input).toHaveAttribute('aria-invalid', 'true')
  await expect(input).toBeFocused()
  await expect(input).toHaveValue('75')
})

test('dirty reload raises a native warning and staying preserves the draft', async ({ page }) => {
  await page.goto('/')
  const input = page.getByRole('spinbutton', { name: 'สัดส่วนภาษาไทย', exact: true })
  await input.fill('67')
  const warning = page.waitForEvent('dialog')
  const reload = page.evaluate(() => window.location.reload())
  const dialog = await warning
  expect(dialog.type()).toBe('beforeunload')
  await dialog.dismiss()
  await reload
  await expect(input).toHaveValue('67')
  await page.getByRole('button', { name: 'ยกเลิก', exact: true }).click()
})
