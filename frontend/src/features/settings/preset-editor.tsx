import { useEffect, useRef, useState } from "react"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { api, ApiError, type Preset, type PresetFields, type PresetField, type ConnectionResult } from "./api"
import { validatePreset } from "./fields"
import { ConnectionFeedback, connectionMessage } from "./connection-feedback"

const fields = [
  { key: "name", label: "ชื่อ preset", placeholder: "เช่น GPT-4o mini", hint: "ใช้แยก preset ในรายการ · ห้ามซ้ำ" },
  { key: "model_id", label: "Model ID", placeholder: "เช่น gpt-4o-mini", hint: "ชื่อโมเดลตามที่ provider กำหนด" },
  { key: "base_url", label: "Base URL", placeholder: "https://api.openai.com/v1", hint: "Endpoint แบบ OpenAI-compatible (http หรือ https)" },
  { key: "api_key", label: "API key", placeholder: "กรอก API key", hint: "เข้ารหัสก่อนบันทึก และจะไม่แสดงอีกหลังบันทึก" },
] as const

export function PresetEditor({ preset, close, saved, refresh, returnFocus }: {
  preset: Preset | null; close: () => void; saved: (name: string, editing: boolean) => void; refresh: () => void; returnFocus: () => void
}) {
  const editing = preset !== null
  const [data, setData] = useState<PresetFields>({ name: preset?.name ?? "", model_id: preset?.model_id ?? "", base_url: preset?.base_url ?? "", api_key: "" })
  const [touched, setTouched] = useState<Partial<Record<PresetField, boolean>>>({})
  const [serverErrors, setServerErrors] = useState<Partial<Record<PresetField, string>>>({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<ConnectionResult | null>(null)
  const [alert, setAlert] = useState("")
  const [testAlert, setTestAlert] = useState("")
  const generation = useRef(0)
  const mounted = useRef(true)
  const savingLock = useRef(false)
  const testingLock = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const validation = validatePreset(data, editing)
  const canTest = !validation.model_id && !validation.base_url && !validation.api_key
  const change = (key: PresetField, value: string) => {
    ++generation.current
    setData(previous => ({ ...previous, [key]: value }))
    setResult(null)
    setAlert("")
    setTestAlert("")
    setServerErrors(previous => { const next = { ...previous }; delete next[key]; return next })
  }
  const focusError = (errors: Partial<Record<PresetField, string>>) => {
    const first = fields.find(field => errors[field.key])
    if (first) window.requestAnimationFrame(() => document.getElementById("preset-" + first.key)?.focus())
  }
  const handleApiError = (error: unknown, action: "save" | "test") => {
    if (error instanceof ApiError) {
      if (error.errorCode === "LLM_001") {
        toast.error("ไม่พบ preset นี้ (อาจถูกลบแล้ว)")
        refresh()
        close()
        return
      }
      if (error.errorCode === "LLM_003" || error.errorCode === "LLM_002") {
        const key = error.errorCode === "LLM_003" ? "name" : error.field as PresetField
        if (fields.some(field => field.key === key)) {
          const errors = { [key]: error.errorCode === "LLM_003" ? "มี preset ชื่อนี้อยู่แล้ว" : "ค่าในช่องนี้ไม่ถูกต้อง" }
          setServerErrors(errors)
          focusError(errors)
          return
        }
      }
      if (error.errorCode === "LLM_004") {
        setAlert("มีการเปลี่ยนแปลงพร้อมกัน ลองอีกครั้ง")
        refresh()
        return
      }
    }
    if (action === "test") setTestAlert("ทดสอบไม่สำเร็จ ลองอีกครั้ง")
    else setAlert("บันทึกไม่สำเร็จ · ระบบหรือการเชื่อมต่อมีปัญหา · ค่าที่กรอกยังอยู่ กดบันทึกอีกครั้งได้")
  }
  const save = async () => {
    setTouched({ name: true, model_id: true, base_url: true, api_key: true })
    if (Object.keys(validation).length || savingLock.current) { focusError(validation); return }
    savingLock.current = true
    setSaving(true)
    setAlert("")
    ++generation.current
    const payload: Partial<PresetFields> = {}
    for (const { key } of fields) {
      const value = data[key].trim()
      if (key === "api_key" && editing && !value) continue
      if (!editing || key === "api_key" || value !== preset[key]) payload[key] = value
    }
    try {
      const response = await api.savePreset(preset?.id, payload)
      saved(response.name, editing)
    } catch (error) {
      if (mounted.current) handleApiError(error, "save")
    } finally {
      savingLock.current = false
      if (mounted.current) setSaving(false)
    }
  }
  const test = async () => {
    if (!canTest || testingLock.current || savingLock.current) return
    testingLock.current = true
    const version = ++generation.current
    setTesting(true)
    setResult(null)
    setTestAlert("")
    const payload: Partial<Omit<PresetFields, "name">> = { model_id: data.model_id.trim(), base_url: data.base_url.trim() }
    if (!editing || data.api_key.trim()) payload.api_key = data.api_key.trim()
    try {
      const response = await api.testConnection(preset?.id, payload)
      if (mounted.current && version === generation.current) setResult(response)
    } catch (error) {
      if (mounted.current && version === generation.current) handleApiError(error, "test")
    } finally {
      testingLock.current = false
      if (mounted.current) setTesting(false)
    }
  }
  return <Dialog open onOpenChange={open => { if (!open && !savingLock.current) close() }}>
    <DialogContent className="max-h-[90dvh] overflow-y-auto p-0 sm:max-w-130" onCloseAutoFocus={event => { event.preventDefault(); returnFocus() }} onEscapeKeyDown={event => { if (saving) event.preventDefault() }} onInteractOutside={event => { if (saving) event.preventDefault() }}>
      <DialogHeader className="px-6 pt-6">
        <DialogTitle>{editing ? "แก้ไข preset" : "เพิ่ม preset"}</DialogTitle>
        <DialogDescription>{editing ? "แก้เฉพาะช่องที่ต้องการ ช่องที่ไม่แก้จะคงค่าเดิม" : "ตั้งค่าโมเดล LLM แบบ OpenAI-compatible สำหรับประมวลผลเอกสาร"}</DialogDescription>
      </DialogHeader>
      <form onSubmit={event => { event.preventDefault(); void save() }} aria-busy={saving}>
        <div className="space-y-5 px-6 pb-6">
          {fields.map(field => {
            const testError = result && !result.ok && result.field === field.key ? connectionMessage(result, data.model_id) : undefined
            const error = serverErrors[field.key] ?? (touched[field.key] ? validation[field.key] : undefined) ?? testError
            const hint = field.key === "api_key" && editing ? "กรอกเฉพาะเมื่อต้องการเปลี่ยน key" : field.hint
            return <div className="space-y-2" key={field.key}>
              <Label htmlFor={"preset-" + field.key}>{field.label}</Label>
              <Input id={"preset-" + field.key} type={field.key === "api_key" ? "password" : "text"}
                value={data[field.key]} disabled={saving}
                placeholder={field.key === "api_key" && editing ? "เว้นว่างไว้เพื่อใช้ key เดิม" : field.placeholder}
                onChange={event => change(field.key, event.target.value)}
                onBlur={() => setTouched(previous => ({ ...previous, [field.key]: true }))}
                aria-invalid={!!error} aria-describedby={"preset-" + field.key + "-hint"} autoComplete="off" spellCheck={false} />
              <p id={"preset-" + field.key + "-hint"} className={"text-xs " + (error ? "text-destructive" : "text-muted-foreground")}>{error ?? hint}</p>
            </div>
          })}
          {result && <ConnectionFeedback result={result} modelId={data.model_id} savedKey={editing && !data.api_key.trim()} />}
          {(alert || testAlert) && <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{alert || testAlert}</div>}
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2 border-t bg-muted/40 px-6 py-4">
          <Button className="mr-auto" type="button" variant="outline" disabled={!canTest || testing || saving} onClick={() => void test()}>
            {testing && <Loader2 className="size-4 animate-spin" />}{testing ? "กำลังทดสอบ…" : "ทดสอบการเชื่อมต่อ"}
          </Button>
          <Button type="button" variant="outline" disabled={saving} onClick={close}>ยกเลิก</Button>
          <Button type="submit" disabled={saving || Object.keys(validation).length > 0}>{saving && <Loader2 className="size-4 animate-spin" />}{saving ? "กำลังบันทึก…" : editing ? "บันทึกการแก้ไข" : "บันทึก preset"}</Button>
        </div>
      </form>
    </DialogContent>
  </Dialog>
}
