import { test, expect, seedPreset, openPresets, openCreate, fillPreset, editPreset, holdRequest, provider } from './support'

test('loading is distinct from empty/error and adding stays available during a delayed list', async ({ page }) => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let failing = true
  await page.route('**/api/llm/presets', async route => {
    if (route.request().method() === 'GET' && failing) {
      await gate
      await route.fulfill({ status: 500, json: { error_code: 'SYS_002' } })
    } else await route.continue()
  })
  try {
    await openPresets(page)
    await expect(page.getByLabel('กำลังโหลด preset')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'ยังไม่มี preset' })).not.toBeVisible()
    const dialog = await openCreate(page)
    await dialog.getByRole('button', { name: 'ยกเลิก', exact: true }).click()
    release()
    await expect(page.getByText('โหลด preset ไม่สำเร็จ', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'ยังไม่มี preset' })).not.toBeVisible()
    failing = false
    await page.getByRole('button', { name: 'ลองอีกครั้ง', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'ยังไม่มี preset' })).toBeVisible()
  } finally { release() }
})

for (const field of [
  { label: 'ชื่อ preset', max: 80 }, { label: 'Model ID', max: 200 },
  { label: 'Base URL', max: 500 }, { label: 'API key', max: 500 },
]) {
  test(`preset validation: ${field.label} rejects blank and overlong values before sending`, async ({ page }) => {
    await openPresets(page)
    const dialog = await openCreate(page)
    await fillPreset(page)
    const sent: unknown[] = []
    page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/llm/presets')) sent.push(request.postDataJSON()) })
    for (const invalid of [' ', 'x'.repeat(field.max + 1), ...(field.label === 'Base URL' ? ['ftp://example.com', 'https://', 'https://a.test/v1?key=secret'] : [])]) {
      await dialog.getByLabel(field.label, { exact: true }).fill(invalid)
      await dialog.getByRole('heading').click()
      await expect(dialog.getByLabel(field.label, { exact: true })).toHaveAttribute('aria-invalid', 'true')
      await expect(dialog.getByRole('button', { name: 'บันทึก preset', exact: true })).toBeDisabled()
    }
    expect(sent).toEqual([])
  })
}

for (const mode of ['create', 'edit'] as const) {
  test(`${mode}: server failure keeps credentials for retry and never exposes the saved key`, async ({ page }) => {
    const preset = mode === 'edit' ? await seedPreset(page.request, 'Existing') : null
    await openPresets(page)
    const dialog = preset ? await editPreset(page, preset.name) : await openCreate(page)
    if (preset) await dialog.getByLabel('Model ID', { exact: true }).fill('e2e-ok-changed')
    else await fillPreset(page, 'New model')
    let failing = true
    await page.route(preset ? '**/api/llm/presets/' + preset.id : '**/api/llm/presets', async route => {
      if (failing && route.request().method() === (preset ? 'PATCH' : 'POST')) await route.fulfill({ status: 500, json: { error_code: 'SYS_002' } })
      else await route.continue()
    })
    const submit = dialog.getByRole('button', { name: preset ? 'บันทึกการแก้ไข' : 'บันทึก preset', exact: true })
    await submit.click()
    await expect(dialog.getByRole('alert')).toContainText('บันทึกไม่สำเร็จ')
    await expect(dialog.getByLabel('Model ID', { exact: true })).toHaveValue(preset ? 'e2e-ok-changed' : 'e2e-ok')
    await expect(dialog.getByLabel('API key', { exact: true })).toHaveValue(preset ? '' : provider.api_key)
    await expect(dialog.getByLabel('API key', { exact: true })).toHaveAttribute('type', 'password')
    failing = false
    await submit.click()
    await expect(dialog).not.toBeVisible()
    const list = await (await page.request.get('/api/llm/presets')).json()
    expect(list).toHaveLength(1)
    expect(list[0]).not.toHaveProperty('api_key')
    expect(list[0]).not.toHaveProperty('api_key_encrypted')
  })

  test(`${mode}: saving prevents duplicate submission and closing until completion`, async ({ page }) => {
    const preset = mode === 'edit' ? await seedPreset(page.request, 'Existing') : null
    await openPresets(page)
    const dialog = preset ? await editPreset(page, preset.name) : await openCreate(page)
    if (preset) await dialog.getByLabel('Model ID', { exact: true }).fill('changed')
    else await fillPreset(page)
    const held = await holdRequest(page, preset ? '**/api/llm/presets/' + preset.id : '**/api/llm/presets', preset ? 'PATCH' : 'POST')
    try {
      await dialog.getByRole('button', { name: preset ? 'บันทึกการแก้ไข' : 'บันทึก preset', exact: true }).click()
      await held.received
      await expect(dialog.getByRole('button', { name: 'กำลังบันทึก…', exact: true })).toBeDisabled()
      for (const label of ['ชื่อ preset', 'Model ID', 'Base URL', 'API key']) await expect(dialog.getByLabel(label, { exact: true })).toBeDisabled()
      await expect(dialog.getByRole('button', { name: 'ยกเลิก', exact: true })).toBeDisabled()
      await expect(dialog.getByRole('button', { name: 'ทดสอบการเชื่อมต่อ', exact: true })).toBeDisabled()
      await page.keyboard.press('Escape')
      await page.mouse.click(5, 5)
      await expect(dialog).toBeVisible()
      expect(held.requests).toHaveLength(1)
      held.release()
      await expect(dialog).not.toBeVisible()
      expect(held.requests).toHaveLength(1)
    } finally { held.release() }
  })
}

test('server preset validation identifies and focuses the field while keeping the dialog', async ({ page }) => {
  await openPresets(page)
  const dialog = await openCreate(page)
  await fillPreset(page)
  await page.route('**/api/llm/presets', async route => {
    if (route.request().method() === 'POST') await route.fulfill({ status: 422, json: { error_code: 'LLM_002', field: 'base_url' } })
    else await route.continue()
  })
  await dialog.getByRole('button', { name: 'บันทึก preset', exact: true }).click()
  await expect(dialog.getByLabel('Base URL', { exact: true })).toHaveAttribute('aria-invalid', 'true')
  await expect(dialog.getByLabel('Base URL', { exact: true })).toBeFocused()
  await expect(dialog.getByLabel('ชื่อ preset', { exact: true })).toHaveValue('Test model')
})

test('default selection from the menu retries failures without moving the badge early', async ({ page }) => {
  await seedPreset(page.request, 'First')
  const second = await seedPreset(page.request, 'Second')
  await openPresets(page)
  let failing = true
  await page.route('**/api/llm/presets/' + second.id + '/default', async route => {
    if (failing) await route.fulfill({ status: 500, json: { error_code: 'SYS_002' } })
    else await route.continue()
  })
  await page.getByRole('button', { name: 'เมนู Second', exact: true }).click()
  await page.getByRole('menuitem', { name: 'ตั้งเป็น default', exact: true }).click()
  await expect(page.getByText('ตั้ง default ไม่สำเร็จ', { exact: true })).toBeVisible()
  await expect(page.getByRole('radio', { name: 'ตั้ง First เป็น default' })).toBeChecked()
  failing = false
  await page.getByRole('button', { name: 'ลองอีกครั้ง', exact: true }).click()
  await expect(page.getByRole('radio', { name: 'ตั้ง Second เป็น default' })).toBeChecked()
  await page.getByRole('button', { name: 'เมนู Second', exact: true }).click()
  await expect(page.getByRole('menuitem', { name: 'ตั้งเป็น default', exact: true })).toBeDisabled()
})

for (const code of ['LLM_001', 'LLM_004']) {
  test(`default ${code} refreshes the list and leaves the original default`, async ({ page }) => {
    await seedPreset(page.request, 'First')
    const second = await seedPreset(page.request, 'Second')
    await openPresets(page)
    const radio = page.getByRole('radio', { name: 'ตั้ง Second เป็น default' })
    await expect(radio).toBeVisible()
    if (code === 'LLM_001') expect((await page.request.delete('/api/llm/presets/' + second.id)).status()).toBe(204)
    else await page.route('**/api/llm/presets/' + second.id + '/default', route => route.fulfill({ status: 409, json: { error_code: code } }))
    await radio.click()
    await expect(page.getByText(code === 'LLM_001' ? 'ไม่พบ preset นี้ (อาจถูกลบแล้ว)' : 'มีการเปลี่ยนแปลงพร้อมกัน ลองอีกครั้ง', { exact: true })).toBeVisible()
    await expect(page.getByRole('radio', { name: 'ตั้ง First เป็น default' })).toBeChecked()
    if (code === 'LLM_001') await expect(radio).not.toBeVisible()
    else await expect(radio).not.toBeChecked()
  })
}

test('pending default selection locks actions and keeps the old badge until the server confirms', async ({ page }) => {
  await seedPreset(page.request, 'First')
  const second = await seedPreset(page.request, 'Second')
  await openPresets(page)
  const held = await holdRequest(page, '**/api/llm/presets/' + second.id + '/default', 'PUT')
  try {
    await page.getByRole('radio', { name: 'ตั้ง Second เป็น default' }).click()
    await held.received
    await expect(page.getByRole('radio', { name: 'ตั้ง First เป็น default' })).toBeChecked()
    await expect(page.getByRole('radio', { name: 'ตั้ง Second เป็น default' })).not.toBeChecked()
    for (const radio of await page.getByRole('radio').all()) await expect(radio).toBeDisabled()
    await expect(page.getByRole('button', { name: 'เมนู Second', exact: true })).toBeDisabled()
    held.release()
    await expect(page.getByRole('radio', { name: 'ตั้ง Second เป็น default' })).toBeChecked()
    expect(held.requests).toHaveLength(1)
  } finally { held.release() }
})

test('a concurrently deleted preset closes the edit dialog and refreshes the list', async ({ page }) => {
  const preset = await seedPreset(page.request, 'Gone')
  await openPresets(page)
  const dialog = await editPreset(page, preset.name)
  await page.request.delete('/api/llm/presets/' + preset.id)
  await dialog.getByLabel('Model ID', { exact: true }).fill('changed')
  await dialog.getByRole('button', { name: 'บันทึกการแก้ไข', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByText('ไม่พบ preset นี้ (อาจถูกลบแล้ว)', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'ยังไม่มี preset' })).toBeVisible()
})

test('first-preset conflict retains the draft and refreshes concurrent presets before retry', async ({ page }) => {
  await openPresets(page)
  const dialog = await openCreate(page)
  await fillPreset(page, 'My draft')
  await seedPreset(page.request, 'Concurrent')
  let failing = true
  await page.route('**/api/llm/presets', async route => {
    if (failing && route.request().method() === 'POST') await route.fulfill({ status: 409, json: { error_code: 'LLM_004' } })
    else await route.continue()
  })
  await dialog.getByRole('button', { name: 'บันทึก preset', exact: true }).click()
  await expect(dialog.getByRole('alert')).toHaveText('มีการเปลี่ยนแปลงพร้อมกัน ลองอีกครั้ง')
  await expect(dialog.getByLabel('ชื่อ preset', { exact: true })).toHaveValue('My draft')
  failing = false
  await dialog.getByRole('button', { name: 'บันทึก preset', exact: true }).click()
  await expect(dialog).not.toBeVisible()
  await expect(page.getByRole('radio', { name: 'ตั้ง Concurrent เป็น default' })).toBeChecked()
  await expect(page.getByRole('radio', { name: 'ตั้ง My draft เป็น default' })).not.toBeChecked()
})

test('deletion chooses the newest of three, preserves default for other deletes and supports cancel', async ({ page }) => {
  await seedPreset(page.request, 'First')
  await seedPreset(page.request, 'Middle')
  await seedPreset(page.request, 'Newest')
  await openPresets(page)
  for (const name of ['First', 'Middle']) {
    await page.getByRole('button', { name: 'เมนู ' + name, exact: true }).click()
    await page.getByRole('menuitem', { name: 'ลบ', exact: true }).click()
    await page.getByRole('button', { name: 'ลบ preset', exact: true }).click()
    await expect(page.getByRole('alertdialog')).not.toBeVisible()
    await expect(page.getByRole('radio', { name: 'ตั้ง Newest เป็น default' })).toBeChecked()
  }
  await page.getByRole('button', { name: 'เมนู Newest', exact: true }).click()
  await page.getByRole('menuitem', { name: 'ลบ', exact: true }).click()
  await page.getByRole('button', { name: 'ยกเลิก', exact: true }).click()
  await expect(page.getByRole('radio', { name: 'ตั้ง Newest เป็น default' })).toBeChecked()
  expect(await (await page.request.get('/api/llm/presets')).json()).toHaveLength(1)
})

test('delete in flight cannot be repeated or dismissed and missing presets count as deleted', async ({ page }) => {
  const preset = await seedPreset(page.request, 'Gone')
  await openPresets(page)
  await page.getByRole('button', { name: 'เมนู Gone', exact: true }).click()
  await page.getByRole('menuitem', { name: 'ลบ', exact: true }).click()
  await page.request.delete('/api/llm/presets/' + preset.id)
  const held = await holdRequest(page, '**/api/llm/presets/' + preset.id, 'DELETE')
  try {
    await page.getByRole('button', { name: 'ลบ preset', exact: true }).click()
    await held.received
    await expect(page.getByRole('button', { name: 'กำลังลบ…', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: 'ยกเลิก', exact: true })).toBeDisabled()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('alertdialog')).toBeVisible()
    held.release()
    await expect(page.getByRole('alertdialog')).not.toBeVisible()
    await expect(page.getByRole('heading', { name: 'ยังไม่มี preset' })).toBeVisible()
    expect(held.requests).toHaveLength(1)
  } finally { held.release() }
})
