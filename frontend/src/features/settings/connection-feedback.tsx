import { CheckCircle2, CircleAlert } from "lucide-react"
import type { ConnectionResult } from "./api"

export function connectionMessage(result: ConnectionResult, modelId: string): string {
  if (result.ok) return `${modelId} ตอบกลับใน ${result.latency_ms} ms`
  if (result.reason === "unauthorized") return `API key ไม่ถูกต้อง หรือไม่มีสิทธิ์ใช้งาน (${result.upstream_status})`
  if (result.reason === "model_not_found") return `ไม่พบโมเดล “${modelId}” ที่ provider นี้ (${result.upstream_status})`
  if (result.reason === "unreachable") return "เชื่อมต่อไม่ได้ หรือไม่ตอบกลับภายใน 10 วินาที"
  return `provider ตอบกลับ ${result.upstream_status ?? "ไม่สำเร็จ"} · ลองใหม่ภายหลัง หรือตรวจโควตาของ provider`
}

export function ConnectionFeedback({ result, modelId, savedKey }: { result: ConnectionResult; modelId: string; savedKey: boolean }) {
  return <div role="status" className={"flex items-start gap-2 rounded-md border p-3 text-sm " + (result.ok ? "border-green-200 bg-green-50 text-green-800" : "border-destructive/25 bg-destructive/5 text-destructive")}>
    {result.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <CircleAlert className="mt-0.5 size-4 shrink-0" />}
    <div><p className="font-medium">{result.ok ? "เชื่อมต่อสำเร็จ" + (savedKey ? " · ใช้ API key ที่บันทึกไว้" : "") : "เชื่อมต่อไม่สำเร็จ"}</p>
      <p className="mt-1 text-xs">{connectionMessage(result, modelId)}</p>
      {!result.ok && <p className="mt-1 text-xs">ยังกดบันทึกได้ถ้าต้องการ</p>}
    </div>
  </div>
}
