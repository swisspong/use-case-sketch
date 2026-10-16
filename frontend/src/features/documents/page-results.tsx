import { useCallback, useEffect, useRef, useState } from "react"
import {
  CheckCircle2,
  CircleAlert,
  Copy,
  LoaderCircle,
  TriangleAlert,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  DocumentError,
  formatDate,
  getPage,
  listOcrPresets,
  OcrError,
  ocrPage,
  type OcrFailureReason,
  type OcrOutput,
  type PageResult,
  type Quality,
  type Thresholds,
} from "./api"

type Criterion = {
  key: keyof Thresholds
  metric:
    "thai_percent" | "garbled_thai_percent" | "text_chars" | "image_percent"
  label: string
  sign: string
  percent: boolean
  reason: string
}

const criteria: Criterion[] = [
  {
    key: "max_thai_percent",
    metric: "thai_percent",
    label: "สัดส่วนภาษาไทย",
    sign: "≤",
    percent: true,
    reason: "ภาษาไทยมากกว่าเกณฑ์",
  },
  {
    key: "max_garbled_thai_percent",
    metric: "garbled_thai_percent",
    label: "ข้อความที่อ่านไม่รู้เรื่อง",
    sign: "≤",
    percent: true,
    reason: "มีสระ/วรรณยุกต์ลอยหรืออักขระที่อ่านไม่ได้",
  },
  {
    key: "min_text_chars",
    metric: "text_chars",
    label: "จำนวนตัวอักษร",
    sign: "≥",
    percent: false,
    reason: "ข้อความน้อยเกินไป",
  },
  {
    key: "max_image_percent",
    metric: "image_percent",
    label: "รูปภาพในหน้า",
    sign: "≤",
    percent: true,
    reason: "รูปภาพมากเกินไป",
  },
]

const failureReasons: Record<OcrFailureReason, string> = {
  provider_timeout: "provider ไม่ตอบภายในเวลาที่กำหนด",
  provider_error: "provider ตอบกลับผิดพลาด",
  invalid_output: "ผล OCR ใช้งานไม่ได้",
}

type OcrState = { page: number } & (
  | { phase: "preparing" }
  | { phase: "running"; presetName: string; startedAt: number }
  | { phase: "failed"; reason: OcrFailureReason; hadPrevious: boolean }
  | {
      phase: "error"
      kind:
        | "no_default"
        | "preset_missing"
        | "presets_failed"
        | "system"
        | "network"
    }
)

function newest(a: OcrOutput | null, b: OcrOutput | undefined) {
  if (!b) return a
  if (!a) return b
  return Date.parse(b.created_at) >= Date.parse(a.created_at) ? b : a
}

function StatusIcon({ passed }: { passed: boolean }) {
  return passed ? (
    <CheckCircle2
      aria-label="ผ่าน"
      className="size-3.5 shrink-0 text-emerald-600"
    />
  ) : (
    <XCircle aria-label="ไม่ผ่าน" className="size-3.5 shrink-0 text-red-600" />
  )
}

function value(quality: Quality, c: Criterion) {
  return `${quality[c.metric]}${c.percent ? "%" : ""}`
}

function QualityTable({
  rows,
  quality,
  thresholds,
  label,
}: {
  rows: Criterion[]
  quality: Quality
  thresholds: Thresholds
  label: string
}) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table aria-label={label} className="w-full text-sm">
        <tbody>
          {rows.map((c) => {
            const failed = quality.failed.includes(c.key)
            return (
              <tr key={c.key} className="border-b last:border-b-0">
                <th scope="row" className="px-3 py-3 text-left font-normal">
                  <span className="flex items-center gap-2">
                    <StatusIcon passed={!failed} />
                    {c.label}
                  </span>
                </th>
                <td className="px-2 py-3 text-right text-xs whitespace-nowrap text-muted-foreground">
                  เกณฑ์ {c.sign} {thresholds[c.key]}
                  {c.percent ? "%" : ""}
                </td>
                <td
                  className={`px-3 py-3 text-right font-medium ${failed ? "text-red-600" : ""}`}
                >
                  {value(quality, c)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Summary({ quality }: { quality: Quality }) {
  return (
    <Badge
      variant="outline"
      className={quality.passed ? "text-emerald-700" : "text-red-700"}
    >
      <span className="hidden sm:contents">
        <StatusIcon passed={quality.passed} />
      </span>
      {quality.passed ? "ผ่านทุกข้อ" : `ไม่ผ่าน ${quality.failed.length} ข้อ`}
    </Badge>
  )
}

function CompareTable({
  rows,
  parser,
  ocr,
  thresholds,
}: {
  rows: Criterion[]
  parser: Quality
  ocr: Quality
  thresholds: Thresholds
}) {
  const cell = (quality: Quality, c: Criterion) => {
    const failed = quality.failed.includes(c.key)
    return (
      <td
        className={`px-2 py-3 text-right font-medium whitespace-nowrap sm:px-3 ${failed ? "text-red-600" : ""}`}
      >
        <span className="inline-flex items-center gap-1.5">
          <StatusIcon passed={!failed} />
          {value(quality, c)}
        </span>
      </td>
    )
  }
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table aria-label="เทียบเกณฑ์ผลเดิมกับ OCR" className="w-full text-sm">
        <thead className="text-xs text-muted-foreground">
          <tr className="border-b">
            <th className="px-3 py-2 text-left font-normal">เกณฑ์</th>
            <th className="px-3 py-2 text-right font-normal">ผลเดิม</th>
            <th className="px-3 py-2 text-right font-normal">OCR</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr key={c.key} className="border-b">
              <th
                scope="row"
                className="min-w-24 px-3 py-3 text-left font-normal"
              >
                <span className="sm:mr-1">{c.label}</span>
                <span className="block text-xs text-muted-foreground sm:inline">
                  {c.sign} {thresholds[c.key]}
                  {c.percent ? "%" : ""}
                </span>
              </th>
              {cell(parser, c)}
              {cell(ocr, c)}
            </tr>
          ))}
          <tr className="bg-muted/40">
            <th scope="row" className="px-3 py-3 text-left font-medium">
              ผลรวม
            </th>
            <td className="px-2 py-2 text-right sm:px-3">
              <Summary quality={parser} />
            </td>
            <td className="px-2 py-2 text-right sm:px-3">
              <Summary quality={ocr} />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function TextBox({
  title,
  text,
  copyLabel,
  badge,
  tall = false,
}: {
  title: string
  text: string
  copyLabel: string
  badge?: React.ReactNode
  tall?: boolean
}) {
  return (
    <div className="min-w-0">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-xs font-medium text-muted-foreground">{title}</h3>
        <div className="flex items-center gap-2">
          {badge}
          <Button
            variant="outline"
            size="icon-sm"
            aria-label={copyLabel}
            disabled={!text}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(text)
                toast.success("คัดลอกข้อความแล้ว")
              } catch {
                toast.error("คัดลอกไม่สำเร็จ")
              }
            }}
          >
            <Copy className="size-3.5" />
          </Button>
        </div>
      </div>
      <div
        className={`overflow-auto rounded-lg border bg-zinc-50 p-4 text-sm leading-7 break-words whitespace-pre-wrap ${tall ? "min-h-80 lg:max-h-[calc(100dvh-540px)]" : "min-h-60 lg:max-h-[calc(100dvh-620px)]"}`}
      >
        {text || (
          <span className="text-muted-foreground">ไม่พบข้อความในหน้านี้</span>
        )}
      </div>
    </div>
  )
}

function PassBadge({ passed }: { passed: boolean }) {
  return (
    <Badge
      variant="outline"
      className={passed ? "text-emerald-700" : "text-red-700"}
    >
      <StatusIcon passed={passed} />
      {passed ? "ผ่าน" : "ไม่ผ่าน"}
    </Badge>
  )
}

function Alert({
  tone,
  title,
  children,
  action,
}: {
  tone: "red" | "amber"
  title: string
  children: React.ReactNode
  action?: React.ReactNode
}) {
  const Icon = tone === "red" ? TriangleAlert : CircleAlert
  return (
    <div
      role="alert"
      className={`flex flex-wrap items-center gap-3 rounded-lg border p-3 text-sm ${tone === "red" ? "border-red-200 bg-red-50 text-red-700" : "border-amber-200 bg-amber-50 text-amber-800"}`}
    >
      <Icon className="size-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">{title}</p>
        <p className="mt-1 text-xs">{children}</p>
      </div>
      {action}
    </div>
  )
}

function elapsedLabel(startedAt: number, now: number) {
  const seconds = Math.max(0, Math.floor((now - startedAt) / 1000))
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`
}

function Running({
  number,
  presetName,
  startedAt,
}: {
  number: number
  presetName: string
  startedAt: number
}) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <div role="status" className="space-y-3 rounded-lg border p-4">
      <div className="flex items-center gap-2 text-sm font-medium">
        <LoaderCircle className="size-4 shrink-0 animate-spin" />
        <span className="min-w-0 flex-1 truncate">
          กำลัง OCR หน้า {number} ด้วย {presetName}…
        </span>
        <span className="text-xs font-normal text-muted-foreground tabular-nums">
          {elapsedLabel(startedAt, now)}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-muted">
        <div className="h-full w-1/3 animate-[ocr-progress_1.6s_ease-in-out_infinite] rounded-full bg-foreground" />
      </div>
      <p className="text-xs text-muted-foreground">
        อย่าปิดหรือออกจากหน้านี้จนกว่าจะเสร็จ
      </p>
    </div>
  )
}

export function Results({
  id,
  number,
  onMissing,
  onMissingDocument,
  onOcrSaved,
}: {
  id: string
  number: number
  onMissing: () => void
  onMissingDocument: () => void
  onOcrSaved: (number: number, textPassed: boolean) => void
}) {
  const [state, setState] = useState<{
    id: string
    number: number
    data?: PageResult
    error?: boolean
  } | null>(null)
  const [revision, setRevision] = useState(0)
  const [ocr, setOcr] = useState<OcrState | null>(null)
  const [saved, setSaved] = useState<Record<number, OcrOutput>>({})
  // The view resets to "compare" whenever the page changes.
  const [tabState, setTabState] = useState({ number, tab: "compare" })
  const tab = tabState.number === number ? tabState.tab : "compare"
  const setTab = useCallback(
    (next: string) => setTabState({ number, tab: next }),
    [number]
  )
  const busy = ocr?.phase === "preparing" || ocr?.phase === "running"
  const busyRef = useRef(false)

  useEffect(() => {
    const controller = new AbortController()
    getPage(id, number, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ id, number, data })
      })
      .catch((failure) => {
        if (controller.signal.aborted) return
        if (
          failure instanceof DocumentError &&
          failure.errorCode === "DOC_008" &&
          number !== 1
        ) {
          onMissing()
          return
        }
        if (
          failure instanceof DocumentError &&
          failure.errorCode === "DOC_007"
        ) {
          onMissingDocument()
          return
        }
        setState({ id, number, error: true })
      })
    return () => controller.abort()
  }, [id, number, revision, onMissing, onMissingDocument])

  useEffect(() => {
    if (!busy) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ""
    }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [busy])

  const startOcr = useCallback(
    async (page: number, hadPrevious: boolean) => {
      // One OCR request at a time; never resent automatically.
      if (busyRef.current) return
      busyRef.current = true
      try {
        setOcr({ page, phase: "preparing" })
        let presetId: string
        let presetName: string
        try {
          const preset = (await listOcrPresets()).find((p) => p.is_default)
          if (!preset) {
            setOcr({ page, phase: "error", kind: "no_default" })
            return
          }
          presetId = preset.id
          presetName = preset.name
        } catch {
          setOcr({ page, phase: "error", kind: "presets_failed" })
          return
        }
        setOcr({ page, phase: "running", presetName, startedAt: Date.now() })
        try {
          const result = await ocrPage(id, page, presetId)
          if (result.status === "ok") {
            setSaved((current) => ({ ...current, [page]: result.ocr }))
            onOcrSaved(page, result.text_passed)
            setTabState({ number: page, tab: "compare" })
            setOcr(null)
          } else
            setOcr({
              page,
              phase: "failed",
              reason: result.reason,
              hadPrevious,
            })
        } catch (failure) {
          const code = failure instanceof OcrError ? failure.errorCode : ""
          if (code === "DOC_007") {
            setOcr(null)
            onMissingDocument()
          } else if (code === "DOC_012")
            setOcr({ page, phase: "error", kind: "no_default" })
          else if (code === "DOC_013")
            setOcr({ page, phase: "error", kind: "preset_missing" })
          else
            setOcr({
              page,
              phase: "error",
              kind:
                failure instanceof OcrError && failure.network
                  ? "network"
                  : "system",
            })
        }
      } finally {
        busyRef.current = false
      }
    },
    [id, onMissingDocument, onOcrSaved]
  )

  const current = state?.id === id && state.number === number ? state : null
  const result = current?.data
  const quality = result?.parser.quality
  const latest = result ? newest(result.ocr, saved[number]) : null
  const pageOcr = ocr?.page === number ? ocr : null
  const legacy = result && "min_thai_percent" in result.thresholds
  const rows = criteria.map((c) =>
    legacy && c.key === "max_thai_percent"
      ? {
          ...c,
          key: "min_thai_percent" as const,
          sign: "≥",
          reason: "ภาษาไทยน้อยกว่าเกณฑ์",
        }
      : c
  )
  const run = () => startOcr(number, latest !== null)

  const notice = (() => {
    if (!pageOcr) return null
    const retry = (
      <Button variant="outline" size="sm" onClick={run} disabled={busy}>
        ลองอีกครั้ง
      </Button>
    )
    switch (pageOcr.phase) {
      case "preparing":
        return (
          <div role="status" className="rounded-lg border p-4">
            <p className="text-sm font-medium">กำลังเตรียม OCR…</p>
            <p className="mt-2 text-xs text-muted-foreground">กรุณารอสักครู่</p>
          </div>
        )
      case "running":
        return (
          <Running
            number={number}
            presetName={pageOcr.presetName}
            startedAt={pageOcr.startedAt}
          />
        )
      case "failed":
        return pageOcr.hadPrevious ? (
          <Alert tone="red" title="OCR ใหม่ไม่สำเร็จ" action={retry}>
            ยังเก็บผล OCR เดิมไว้ · ลองอีกครั้งได้
          </Alert>
        ) : (
          <Alert
            tone="red"
            title={`OCR หน้า ${number} ไม่สำเร็จ`}
            action={retry}
          >
            {failureReasons[pageOcr.reason]} · ลองอีกครั้งได้
          </Alert>
        )
      case "error":
        switch (pageOcr.kind) {
          case "no_default":
            return (
              <Alert
                tone="amber"
                title="ยังไม่มี LLM preset สำหรับ OCR"
                action={
                  <a
                    href="/settings?tab=llm"
                    className={buttonVariants({
                      variant: "outline",
                      size: "sm",
                    })}
                  >
                    ไปตั้งค่า LLM presets
                  </a>
                }
              >
                เพิ่ม preset และตั้งเป็นค่าเริ่มต้นก่อน แล้วกลับมาสั่ง OCR
                อีกครั้ง
              </Alert>
            )
          case "preset_missing":
            return (
              <Alert
                tone="red"
                title="ไม่พบ LLM preset ที่เลือก"
                action={retry}
              >
                preset อาจถูกลบไปแล้ว · ลองใหม่ด้วย preset เริ่มต้น
              </Alert>
            )
          case "presets_failed":
            return (
              <Alert
                tone="red"
                title="โหลดการตั้งค่า OCR ไม่สำเร็จ"
                action={retry}
              >
                ตรวจสอบการเชื่อมต่อ แล้วลองอีกครั้ง
              </Alert>
            )
          case "network":
            return (
              <Alert tone="red" title="OCR ไม่สำเร็จ" action={retry}>
                การเชื่อมต่อขาดหาย · กด “ลองอีกครั้ง” เพื่อสั่ง OCR ใหม่
              </Alert>
            )
          default:
            return (
              <Alert tone="red" title="OCR ไม่สำเร็จ" action={retry}>
                เกิดข้อผิดพลาด · กด “ลองอีกครั้ง” เพื่อสั่ง OCR ใหม่
              </Alert>
            )
        }
    }
  })()

  const runningBadge = pageOcr?.phase === "running" && (
    <Badge variant="outline" className="text-muted-foreground">
      <LoaderCircle className="size-3 animate-spin" />
      กำลัง OCR
    </Badge>
  )

  const body = (() => {
    if (current?.error)
      return (
        <div className="space-y-4 p-5">
          <p role="alert">โหลดผลของหน้านี้ไม่สำเร็จ</p>
          <Button
            variant="outline"
            onClick={() => {
              setState(null)
              setRevision((n) => n + 1)
            }}
          >
            ลองอีกครั้ง
          </Button>
        </div>
      )
    if (!result || !quality)
      return (
        <div
          role="status"
          aria-label="กำลังโหลดผลรายหน้า"
          className="space-y-4 p-5"
        >
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      )
    return null
  })()

  const legacyNote = legacy && (
    <p className="rounded-lg bg-muted p-3 text-xs text-muted-foreground">
      ผลตรวจตามเกณฑ์เดิม (สัดส่วนภาษาไทยขั้นต่ำ) · คงผลที่บันทึกไว้ตอนอัปโหลด
    </p>
  )

  if (body || !result || !quality || !latest)
    return (
      <section
        aria-label="ผลตรวจคุณภาพรายหน้า"
        className="min-w-0 overflow-hidden rounded-xl border bg-background shadow-sm"
      >
        <div className="flex flex-wrap items-center gap-2 border-b px-5 py-4">
          <h2 className="font-semibold">ข้อความจาก PDF · หน้า {number}</h2>
          {runningBadge ||
            (quality && (
              <Badge
                variant="outline"
                className={
                  quality.passed ? "text-emerald-700" : "text-amber-700"
                }
              >
                {quality.passed ? "ผ่านเกณฑ์" : "แนะนำ OCR"}
              </Badge>
            ))}
        </div>
        {body ??
          (result && quality && (
            <div className="space-y-5 p-5">
              {legacyNote}
              {notice ??
                (!quality.passed && (
                  <Alert
                    tone="amber"
                    title={`ไม่ผ่านเกณฑ์ ${quality.failed.length} จาก 4 ข้อ`}
                    action={
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={run}
                        disabled={busy}
                      >
                        OCR หน้านี้
                      </Button>
                    }
                  >
                    {rows
                      .filter((c) => quality.failed.includes(c.key))
                      .map((c) => c.reason)
                      .join(" และ")}{" "}
                    · แนะนำให้ OCR หน้านี้
                  </Alert>
                ))}
              <div>
                <h3 className="mb-2 text-xs text-muted-foreground">
                  คุณภาพข้อความเทียบเกณฑ์
                </h3>
                <QualityTable
                  rows={rows}
                  quality={quality}
                  thresholds={result.thresholds}
                  label="คุณภาพข้อความเทียบเกณฑ์"
                />
              </div>
              {quality.passed && !notice && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={run}
                  disabled={busy}
                >
                  OCR หน้านี้
                </Button>
              )}
              <TextBox
                title="ข้อความที่ดึงจาก PDF"
                text={result.parser.text}
                copyLabel="คัดลอกข้อความ"
                tall
              />
            </div>
          ))}
      </section>
    )

  return (
    <Tabs value={tab} onValueChange={setTab} className="min-w-0">
      <section
        aria-label="ผลตรวจคุณภาพรายหน้า"
        className="min-w-0 overflow-hidden rounded-xl border bg-background shadow-sm"
      >
        <div className="flex flex-wrap items-center gap-2 border-b px-5 py-4">
          <h2 className="font-semibold">ผลลัพธ์ · หน้า {number}</h2>
          {runningBadge || (
            <Badge variant="outline" className="text-emerald-700">
              <CheckCircle2 className="size-3 text-emerald-600" />
              OCR แล้ว
            </Badge>
          )}
          <TabsList className="ml-auto" aria-label="มุมมองผลลัพธ์">
            <TabsTrigger value="compare">เทียบผล</TabsTrigger>
            <TabsTrigger value="parser">ผลเดิม</TabsTrigger>
            <TabsTrigger value="ocr">OCR</TabsTrigger>
          </TabsList>
        </div>
        <div className="space-y-5 p-5">
          {legacyNote}
          {notice}
          {tab !== "parser" && (
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="text-xs text-muted-foreground">ผล OCR</span>
              <span className="min-w-0 flex-1">
                {latest.preset_name} · {formatDate(latest.created_at)}
              </span>
              <Button variant="outline" size="sm" onClick={run} disabled={busy}>
                OCR ใหม่
              </Button>
            </div>
          )}
          <TabsContent value="compare" className="space-y-5">
            <CompareTable
              rows={rows}
              parser={quality}
              ocr={latest.quality}
              thresholds={result.thresholds}
            />
            <div className="grid gap-4 md:grid-cols-2">
              <TextBox
                title="ผลเดิม"
                text={result.parser.text}
                copyLabel="คัดลอกข้อความผลเดิม"
                badge={<PassBadge passed={quality.passed} />}
              />
              <TextBox
                title={`OCR · ${latest.model_id}`}
                text={latest.text}
                copyLabel="คัดลอกข้อความ OCR"
                badge={<PassBadge passed={latest.quality.passed} />}
              />
            </div>
          </TabsContent>
          <TabsContent value="parser" className="space-y-5">
            <div>
              <h3 className="mb-2 text-xs text-muted-foreground">
                คุณภาพข้อความเทียบเกณฑ์
              </h3>
              <QualityTable
                rows={rows}
                quality={quality}
                thresholds={result.thresholds}
                label="คุณภาพผลเดิมเทียบเกณฑ์"
              />
            </div>
            <TextBox
              title="ผลเดิม"
              text={result.parser.text}
              copyLabel="คัดลอกข้อความผลเดิม"
              badge={<PassBadge passed={quality.passed} />}
              tall
            />
          </TabsContent>
          <TabsContent value="ocr" className="space-y-5">
            <div>
              <h3 className="mb-2 text-xs text-muted-foreground">
                คุณภาพข้อความเทียบเกณฑ์
              </h3>
              <QualityTable
                rows={rows}
                quality={latest.quality}
                thresholds={result.thresholds}
                label="คุณภาพ OCR เทียบเกณฑ์"
              />
            </div>
            <TextBox
              title={`OCR · ${latest.model_id}`}
              text={latest.text}
              copyLabel="คัดลอกข้อความ OCR"
              badge={<PassBadge passed={latest.quality.passed} />}
              tall
            />
          </TabsContent>
        </div>
      </section>
    </Tabs>
  )
}
