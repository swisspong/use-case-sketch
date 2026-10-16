import type { PresetFields, ThresholdKey } from "./api"

export const thresholdFields: { key: ThresholdKey; label: string; bound: string; description: string; unit: string }[] = [
  { key: "max_thai_percent", label: "สัดส่วนภาษาไทย", bound: "สูงสุด", description: "สัดส่วนตัวอักษรไทยในข้อความของหน้า ถ้าเกินค่านี้ แนะนำให้ OCR หน้านี้", unit: "%" },
  { key: "max_garbled_thai_percent", label: "ข้อความที่อ่านไม่รู้เรื่อง", bound: "สูงสุด", description: "สัดส่วนข้อความไทยที่เพี้ยน เช่น สระหรือวรรณยุกต์ลอยผิดตำแหน่ง ถ้าเกินค่านี้ ถือว่าอ่านไม่ได้", unit: "%" },
  { key: "min_text_chars", label: "ข้อความน้อยเกินไป", bound: "ขั้นต่ำ", description: "จำนวนตัวอักษรในหน้า (ไม่นับช่องว่าง) ถ้าน้อยกว่าค่านี้ ถือว่าหน้านั้นมีข้อความน้อยเกินไป", unit: "ตัวอักษร" },
  { key: "max_image_percent", label: "รูปภาพในหน้า", bound: "สูงสุด", description: "พื้นที่ที่รูปภาพครอบคลุมเทียบกับทั้งหน้า ถ้าเกินค่านี้ ถือว่าเป็นหน้ารูปภาพ (เช่น หน้าสแกน)", unit: "%" },
]

export function thresholdError(key: ThresholdKey, raw: string): string | undefined {
  const value = Number(raw)
  if (raw.trim() === "" || !Number.isSafeInteger(value) || value < 0 || (key !== "min_text_chars" && value > 100)) {
    return key === "min_text_chars" ? "ต้องเป็นจำนวนเต็มตั้งแต่ 0 ขึ้นไป" : "ต้องเป็นจำนวนเต็ม 0–100"
  }
}
export function validatePreset(data: PresetFields, editing: boolean) {
  const errors: Partial<Record<keyof PresetFields, string>> = {}
  for (const [key, max, label] of [["name",80,"ชื่อ preset"],["model_id",200,"Model ID"],["base_url",500,"Base URL"],["api_key",500,"API key"]] as const) {
    const value = data[key].trim()
    if (key === "api_key" && editing && !value) continue
    if (!value) errors[key] = `กรอก ${label}`
    else if ([...value].length > max) errors[key] = `ต้องไม่เกิน ${max} ตัวอักษร`
  }
  if (data.base_url.trim() && !errors.base_url) {
    try {
      const url = new URL(data.base_url.trim())
      if (!["http:", "https:"].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash || /\s/.test(data.base_url.trim())) throw new Error()
    } catch { errors.base_url = "ต้องเป็น URL แบบ http(s) เช่น https://api.openai.com/v1" }
  }
  return errors
}
