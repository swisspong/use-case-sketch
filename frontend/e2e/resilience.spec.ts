import { test, expect } from './support'

for (const failure of ['network', 'invalid-json', 'unknown-code', 'malformed-success'] as const) {
  test(`threshold load fallback: ${failure} shows retry without inventing values`, async ({ page }) => {
    let failing = true
    await page.route('**/api/text-quality/thresholds', async route => {
      if (!failing) { await route.continue(); return }
      if (failure === 'network') await route.abort('failed')
      else if (failure === 'invalid-json') await route.fulfill({ status: 500, contentType: 'text/html', body: '<h1>Unavailable</h1>' })
      else if (failure === 'unknown-code') await route.fulfill({ status: 418, json: { error_code: 'UNKNOWN_999' } })
      else await route.fulfill({ status: 200, json: { max_thai_percent: 50 } })
    })
    await page.goto('/')
    await expect(page.getByText('โหลดเกณฑ์ไม่สำเร็จ', { exact: true })).toBeVisible()
    await expect(page.getByRole('spinbutton')).toHaveCount(0)
    failing = false
    await page.getByRole('button', { name: 'ลองอีกครั้ง', exact: true }).click()
    await expect(page.getByRole('spinbutton', { name: 'สัดส่วนภาษาไทย', exact: true })).toHaveValue('50')
  })

  test(`threshold save fallback: ${failure} retains the latest draft for retry`, async ({ page }) => {
    let failing = true
    await page.route('**/api/text-quality/thresholds', async route => {
      if (!failing || route.request().method() !== 'PATCH') { await route.continue(); return }
      if (failure === 'network') await route.abort('failed')
      else if (failure === 'invalid-json') await route.fulfill({ status: 500, contentType: 'text/plain', body: 'Unavailable' })
      else if (failure === 'unknown-code') await route.fulfill({ status: 422, json: { error_code: 'UNKNOWN_999' } })
      else await route.fulfill({ status: 200, json: {} })
    })
    await page.goto('/')
    const input = page.getByRole('spinbutton', { name: 'สัดส่วนภาษาไทย', exact: true })
    await input.fill('71')
    await page.getByRole('button', { name: 'บันทึก', exact: true }).click()
    await expect(page.getByText('บันทึกไม่สำเร็จ', { exact: true })).toBeVisible()
    await expect(input).toHaveValue('71')
    await input.fill('72')
    failing = false
    await page.getByRole('button', { name: 'ลองอีกครั้ง', exact: true }).click()
    await expect(page.getByText('บันทึกการตั้งค่าแล้ว', { exact: true })).toBeVisible()
    await page.reload()
    await expect(input).toHaveValue('72')
  })
}
