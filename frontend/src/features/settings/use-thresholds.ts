import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { api, ApiError, thresholdKeys, type ThresholdKey, type Thresholds, type ThresholdValues } from "./api"
import { thresholdError } from "./fields"

export function useThresholds(active: boolean) {
  const [snapshot, setSnapshot] = useState<Thresholds | null>(null)
  const [draft, setDraft] = useState<Partial<Record<ThresholdKey, string>>>({})
  const [loading, setLoading] = useState(true)
  const [loadFailed, setLoadFailed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [serverErrors, setServerErrors] = useState<Partial<Record<ThresholdKey, string>>>({})
  const loadSequence = useRef(0)
  const saveLock = useRef(false)
  const load = useCallback(async () => {
    const sequence = ++loadSequence.current
    setLoading(true)
    setLoadFailed(false)
    try {
      const response = await api.getThresholds()
      if (sequence !== loadSequence.current) return
      setSnapshot(response)
      setDraft({})
    } catch {
      if (sequence === loadSequence.current) setLoadFailed(true)
    } finally {
      if (sequence === loadSequence.current) setLoading(false)
    }
  }, [])
  useEffect(() => {
    const timer = window.setTimeout(() => { if (active && !snapshot) void load() }, 0)
    return () => window.clearTimeout(timer)
  }, [active, snapshot, load])

  useEffect(() => {
    if (saving) return
    const key = thresholdKeys.find(field => serverErrors[field])
    if (key) document.getElementById(key)?.focus()
  }, [serverErrors, saving])

  const values = Object.fromEntries(thresholdKeys.map(key => [key, draft[key] ?? String(snapshot?.[key] ?? "")])) as Record<ThresholdKey, string>
  const errors = { ...serverErrors }
  if (snapshot) for (const key of thresholdKeys) {
    const error = thresholdError(key, values[key])
    if (error) errors[key] = error
  }
  const dirty = snapshot !== null && thresholdKeys.some(key => values[key].trim() === "" || Number(values[key]) !== snapshot[key])
  const invalid = Object.keys(errors).length > 0
  const reset = () => { setDraft({}); setServerErrors({}) }
  const change = (key: ThresholdKey, value: string) => {
    setDraft(previous => ({ ...previous, [key]: value }))
    setServerErrors(previous => { const next = { ...previous }; delete next[key]; return next })
  }
  const save = async () => {
    if (!snapshot || !dirty || invalid || saveLock.current) return
    saveLock.current = true
    setSaving(true)
    const diff: Partial<ThresholdValues> = {}
    for (const key of thresholdKeys) if (Number(values[key]) !== snapshot[key]) diff[key] = Number(values[key])
    try {
      const response = await api.updateThresholds(diff)
      setSnapshot(response)
      reset()
      toast.success("บันทึกการตั้งค่าแล้ว", { description: "เกณฑ์ใหม่จะใช้กับเอกสารที่ประมวลผลหลังจากนี้" })
    } catch (error) {
      if (error instanceof ApiError && error.errorCode === "TQ_001" && thresholdKeys.includes(error.field as ThresholdKey)) {
        const key = error.field as ThresholdKey
        setServerErrors({ [key]: key === "min_text_chars" ? "ต้องเป็นจำนวนเต็มตั้งแต่ 0 ขึ้นไป" : "ต้องเป็นจำนวนเต็ม 0–100" })
      } else toast.error("บันทึกไม่สำเร็จ", { description: "ค่าที่แก้ยังอยู่ในฟอร์ม · ลองอีกครั้ง", action: { label: "ลองอีกครั้ง", onClick: () => {
        const form = document.getElementById("threshold-form")
        if (form instanceof HTMLFormElement) form.requestSubmit()
      } } })
    } finally {
      saveLock.current = false
      setSaving(false)
    }
  }
  return { snapshot, values, errors, dirty, invalid, loading, loadFailed, saving, load, reset, change, save }
}
export type ThresholdController = ReturnType<typeof useThresholds>
