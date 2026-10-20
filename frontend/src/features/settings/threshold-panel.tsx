import { Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Slider } from "@/components/ui/slider"
import { Skeleton } from "@/components/ui/skeleton"
import { thresholdFields } from "./fields"
import type { ThresholdController } from "./use-thresholds"

export function LoadError({ title, retry }: { title: string; retry: () => void }) {
  return <div className="flex min-h-64 flex-col items-center justify-center gap-3 p-6 text-center" role="alert">
    <p className="font-medium">{title}</p>
    <p className="text-sm text-muted-foreground">ระบบหรือการเชื่อมต่อมีปัญหา · ลองอีกครั้ง</p>
    <Button variant="outline" onClick={retry}>ลองอีกครั้ง</Button>
  </div>
}

export function ThresholdPanel({ state }: { state: ThresholdController }) {
  return <Card className="settings-card gap-0 py-0 ring-0">
    <CardHeader className="gap-1.5 border-b px-6 py-6 [.border-b]:pb-6">
      <CardTitle className="leading-5">เกณฑ์คุณภาพข้อความ</CardTitle>
      <CardDescription className="leading-[17px]">เข้าเงื่อนไขข้อใดข้อหนึ่ง → แนะนำ OCR · ค่าเท่ากับเกณฑ์ถือว่าผ่าน</CardDescription>
    </CardHeader>
    {state.loadFailed ? <LoadError title="โหลดเกณฑ์ไม่สำเร็จ" retry={() => void state.load()} /> :
      <form id="threshold-form" noValidate onSubmit={event => { event.preventDefault(); void state.save() }} aria-label="เกณฑ์คุณภาพข้อความ" aria-busy={state.loading || state.saving}>
        <div className="divide-y">
          {thresholdFields.map(field => {
            const count = field.key === "min_text_chars"
            const error = state.errors[field.key]
            return <div className="threshold-row" key={field.key}>
              <div className="min-w-0 flex-1">
                <div className="mb-1.5 flex items-center gap-2">
                  <Label htmlFor={field.key} className="leading-[17px]">{field.label}</Label>
                  <Badge variant="secondary" className="rounded px-1.5 py-0 text-xs font-normal">{field.bound}</Badge>
                </div>
                <p className="text-[13px] leading-[19.5px] text-muted-foreground" id={field.key + "-description"}>{field.description}</p>
              </div>
              {state.loading || !state.snapshot ? <div className="w-full shrink-0 space-y-2 md:w-81" aria-label="กำลังโหลดค่า">
                <Skeleton className="ml-auto h-9 w-full" /><Skeleton className="ml-auto h-3 w-20" />
              </div> : <div className={count ? "w-full shrink-0 md:w-37" : "w-full shrink-0 md:w-81"}>
                <div className="flex items-center gap-4">
                  {!count && <Slider aria-label={field.label} value={[Math.max(0, Math.min(100, Number(state.values[field.key]) || 0))]}
                    min={0} max={100} step={1} disabled={state.saving}
                    onValueChange={([value]) => state.change(field.key, String(value))} className="flex-1" />}
                  <div className={"relative " + (count ? "w-full" : "w-22 shrink-0")}>
                    <Input id={field.key} type="number" min={0} max={count ? undefined : 100} step={1}
                      value={state.values[field.key]} onChange={event => state.change(field.key, event.target.value)}
                      disabled={state.saving} aria-invalid={!!error}
                      aria-describedby={field.key + "-description " + field.key + "-hint"}
                      className={count ? "pr-18 text-right" : "pr-7 text-right"} />
                    <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-sm text-muted-foreground">{field.unit}</span>
                  </div>
                </div>
                <p id={field.key + "-hint"} className={"mt-1.5 text-right text-xs " + (error ? "text-destructive" : "text-muted-foreground")}>
                  {error ?? `ค่าเริ่มต้น ${state.snapshot.defaults[field.key]}${count ? " ตัวอักษร" : "%"}`}
                </p>
              </div>}
            </div>
          })}
        </div>
        <CardFooter className="justify-end gap-2 px-6 py-4">
          <Button className="h-8.5 px-4" type="button" variant="outline" disabled={!state.dirty || state.saving || state.loading} onClick={state.reset}>ยกเลิก</Button>
          <Button className="h-8.5 px-4" type="submit" disabled={!state.dirty || state.invalid || state.saving || state.loading}>
            {state.saving && <Loader2 className="size-4 animate-spin" />}{state.saving ? "กำลังบันทึก…" : "บันทึก"}
          </Button>
        </CardFooter>
      </form>}
  </Card>
}
