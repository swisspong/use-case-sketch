import { useCallback, useEffect, useRef, useState } from "react"
import { Loader2, LockKeyhole, MoreHorizontal, Pencil, Plus, PlugZap, Trash2, Star } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Card, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger, DropdownMenuItem, DropdownMenuSeparator } from "@/components/ui/dropdown-menu"
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "@/components/ui/alert-dialog"
import { api, ApiError, type Preset } from "./api"
import { PresetEditor } from "./preset-editor"
import { connectionMessage } from "./connection-feedback"
import { LoadError } from "./threshold-panel"

export function PresetsPanel({ active }: { active: boolean }) {
  const [presets, setPresets] = useState<Preset[]>([])
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [editor, setEditor] = useState<{ preset: Preset | null } | null>(null)
  const [deleting, setDeleting] = useState<Preset | null>(null)
  const [deleteError, setDeleteError] = useState(false)
  const [pending, setPending] = useState("")
  const requestId = useRef(0)
  const mutationLock = useRef(false)
  const editorTrigger = useRef<HTMLElement | null>(null)
  const openEditor = (preset: Preset | null, trigger: HTMLElement | null) => {
    editorTrigger.current = trigger
    setEditor({ preset })
  }
  const load = useCallback(async () => {
    const id = ++requestId.current
    setLoading(true)
    setFailed(false)
    try {
      const response = await api.listPresets()
      if (id === requestId.current) setPresets(response)
    } catch {
      if (id === requestId.current) setFailed(true)
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }, [])
  useEffect(() => {
    const timer = window.setTimeout(() => { if (active) void load() }, 0)
    return () => window.clearTimeout(timer)
  }, [active, load])

  const errorToast = (error: unknown, action: string, retry: () => void) => {
    const code = error instanceof ApiError ? error.errorCode : ""
    if (code === "LLM_001" || code === "LLM_004") {
      toast.error(code === "LLM_001" ? "ไม่พบ preset นี้ (อาจถูกลบแล้ว)" : "มีการเปลี่ยนแปลงพร้อมกัน ลองอีกครั้ง")
      void load()
    } else toast.error(action, { description: "ระบบหรือการเชื่อมต่อมีปัญหา", action: { label: "ลองอีกครั้ง", onClick: retry } })
  }
  const makeDefault = async (preset: Preset) => {
    if (mutationLock.current || preset.is_default) return
    mutationLock.current = true
    setPending(preset.id)
    try {
      await api.setDefault(preset.id)
      toast.success(`ตั้ง “${preset.name}” เป็น default แล้ว`, { description: "เอกสารที่ประมวลผลหลังจากนี้จะใช้ preset นี้" })
      await load()
    } catch (error) { errorToast(error, "ตั้ง default ไม่สำเร็จ", () => void makeDefault(preset)) }
    finally { mutationLock.current = false; setPending("") }
  }
  const test = async (preset: Preset) => {
    if (mutationLock.current) return
    mutationLock.current = true
    setPending(preset.id)
    try {
      const result = await api.testConnection(preset.id, {})
      toast[result.ok ? "success" : "error"](`${preset.name} ${result.ok ? "เชื่อมต่อสำเร็จ" : "เชื่อมต่อไม่สำเร็จ"}`, {
        description: connectionMessage(result, preset.model_id),
      })
    } catch (error) { errorToast(error, "ทดสอบไม่สำเร็จ", () => void test(preset)) }
    finally { mutationLock.current = false; setPending("") }
  }
  const remove = async () => {
    if (!deleting || mutationLock.current) return
    mutationLock.current = true
    setPending(deleting.id)
    setDeleteError(false)
    try {
      try { await api.deletePreset(deleting.id) }
      catch (error) { if (!(error instanceof ApiError && error.errorCode === "LLM_001")) throw error }
      setDeleting(null)
      toast.success("ลบ preset แล้ว", { description: deleting.name })
      await load()
    } catch { setDeleteError(true) }
    finally { mutationLock.current = false; setPending("") }
  }
  return <>
    <Card className="settings-card gap-0 py-0 ring-0">
      <CardHeader className="flex flex-wrap items-start justify-between gap-4 border-b px-6 py-6 [.border-b]:pb-6">
        <div className="space-y-1.5"><CardTitle className="leading-5">Model presets</CardTitle>
          <CardDescription className="leading-[17px]">โมเดลแบบ OpenAI-compatible ที่ใช้ประมวลผลเอกสาร · เลือก 1 preset เป็น default</CardDescription></div>
        <Button id="add-preset" onClick={event => openEditor(null, event.currentTarget)}><Plus className="size-4" />เพิ่ม preset</Button>
      </CardHeader>
      {loading ? <div aria-label="กำลังโหลด preset" className="divide-y">
        {[0,1,2].map(index => <div className="space-y-3 px-6 py-5" key={index}><Skeleton className="h-4 w-36" /><Skeleton className="h-3 w-3/4" /><Skeleton className="h-3 w-48" /></div>)}
      </div> : failed ? <LoadError title="โหลด preset ไม่สำเร็จ" retry={() => void load()} /> :
        presets.length === 0 ? <div className="flex min-h-64 flex-col items-center justify-center gap-3 p-6 text-center">
          <PlugZap className="mb-1 size-8 text-muted-foreground" />
          <h2 className="font-medium">ยังไม่มี preset</h2>
          <p className="max-w-md text-sm leading-relaxed text-muted-foreground">เพิ่มโมเดล LLM อย่างน้อย 1 ตัวเพื่อประมวลผลเอกสาร · preset แรกจะถูกตั้งเป็น default ให้อัตโนมัติ</p>
          <Button variant="outline" onClick={event => openEditor(null, event.currentTarget)}><Plus className="size-4" />เพิ่ม preset</Button>
        </div> : <RadioGroup value={presets.find(p => p.is_default)?.id ?? ""} aria-label="Default model preset"
            onValueChange={id => { const p = presets.find(p => p.id === id); if (p) void makeDefault(p) }} className="gap-0 divide-y">
          {presets.map(preset => <div className={"flex items-start gap-4 px-6 py-4 " + (preset.is_default ? "bg-muted/30" : "")} key={preset.id}>
            <RadioGroupItem value={preset.id} id={"default-" + preset.id} aria-label={"ตั้ง " + preset.name + " เป็น default"} className="mt-1" disabled={!!pending} />
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <Label htmlFor={"default-" + preset.id} className="break-words">{preset.name}</Label>
                {preset.is_default && <Badge className="rounded px-1.5 py-0 text-xs">Default</Badge>}
              </div>
              <div className="flex flex-wrap gap-x-2 gap-y-1 text-xs">
                <code className="break-all rounded bg-muted px-1.5 py-0.5">{preset.model_id}</code>
                <span className="break-all font-mono leading-5 text-muted-foreground">{preset.base_url}</span>
              </div>
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground"><LockKeyhole className="size-3" />API key ถูกเข้ารหัสไว้ · ไม่แสดงซ้ำ</p>
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild><Button id={"preset-menu-" + preset.id} variant="ghost" size="icon" aria-label={"เมนู " + preset.name} disabled={!!pending}>
                {pending === preset.id ? <Loader2 className="size-4 animate-spin" /> : <MoreHorizontal className="size-4" />}
              </Button></DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => void test(preset)}><PlugZap />ทดสอบการเชื่อมต่อ</DropdownMenuItem>
                <DropdownMenuItem onSelect={() => openEditor(preset, document.getElementById("preset-menu-" + preset.id))}><Pencil />แก้ไข</DropdownMenuItem>
                <DropdownMenuItem disabled={preset.is_default} onSelect={() => void makeDefault(preset)}><Star />ตั้งเป็น default</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={() => { setDeleteError(false); setDeleting(preset) }}><Trash2 />ลบ</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>)}
        </RadioGroup>}
      <CardFooter className="px-6 py-3 text-xs text-muted-foreground">กด radio เพื่อเปลี่ยน default · มีผลทันที</CardFooter>
    </Card>
    {editor && <PresetEditor preset={editor.preset} close={() => setEditor(null)} refresh={() => void load()}
      returnFocus={() => {
        const target = editorTrigger.current
        if (target?.isConnected) target.focus()
        else document.getElementById("add-preset")?.focus()
      }}
      saved={(name, editing) => { setEditor(null); toast.success(editing ? "บันทึกการแก้ไขแล้ว" : "เพิ่ม preset แล้ว", { description: name }); void load() }} />}
    <AlertDialog open={!!deleting} onOpenChange={open => { if (!open && !mutationLock.current) setDeleting(null) }}>
      <AlertDialogContent className="sm:max-w-120">
        <AlertDialogHeader>
          <AlertDialogTitle>ลบ preset “{deleting?.name}”?</AlertDialogTitle>
          <AlertDialogDescription>ลบแล้วกู้คืนไม่ได้{deleting?.is_default ? " · preset นี้เป็น default ระบบจะตั้ง preset ที่สร้างล่าสุดเป็น default แทน" : ""}</AlertDialogDescription>
        </AlertDialogHeader>
        {deleteError && <p role="alert" className="rounded-md bg-destructive/5 p-3 text-sm text-destructive">ลบไม่สำเร็จ · ระบบหรือการเชื่อมต่อมีปัญหา · ลองลบอีกครั้ง</p>}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={!!pending}>ยกเลิก</AlertDialogCancel>
          <AlertDialogAction variant="destructive" disabled={!!pending} onClick={event => { event.preventDefault(); void remove() }}>
            {pending && <Loader2 className="size-4 animate-spin" />}{pending ? "กำลังลบ…" : "ลบ preset"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </>
}
