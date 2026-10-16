import { useEffect, useRef, useState } from "react"
import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
  type RenderTask,
} from "pdfjs-dist"
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url"
import { ChevronLeft, ChevronRight, Minus, Plus } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { apiBase, type PageSummary } from "./api"

GlobalWorkerOptions.workerSrc = workerUrl

function PdfCanvas({
  pdf,
  number,
  thumbnail = false,
  zoom = 100,
}: {
  pdf: PDFDocumentProxy
  number: number
  thumbnail?: boolean
  zoom?: number
}) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const wrapper = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(!thumbnail)
  const [width, setWidth] = useState(0)
  const [status, setStatus] = useState("loading")
  useEffect(() => {
    const element = wrapper.current!
    const resize = new ResizeObserver(([entry]) =>
      setWidth(entry.contentRect.width)
    )
    resize.observe(element)
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { rootMargin: "150px" }
    )
    if (thumbnail) observer.observe(element)
    return () => {
      resize.disconnect()
      observer.disconnect()
    }
  }, [thumbnail])
  useEffect(() => {
    if (!visible || !width) return
    let cancelled = false
    let render: RenderTask | undefined
    pdf
      .getPage(number)
      .then(async (page) => {
        if (cancelled) return
        const element = canvas.current!
        const context = element.getContext("2d")!
        const original = page.getViewport({ scale: 1 })
        // Bound pixels even for huge source dimensions and zoom on high-DPI devices.
        const scale =
          (Math.min(width / original.width, thumbnail ? 1 : 1.5) * zoom) / 100
        const viewport = page.getViewport({ scale })
        const ratio = Math.min(
          window.devicePixelRatio || 1,
          2,
          Math.sqrt(8_000_000 / (viewport.width * viewport.height))
        )
        element.width = Math.max(1, Math.floor(viewport.width * ratio))
        element.height = Math.max(1, Math.floor(viewport.height * ratio))
        element.style.width = `${viewport.width}px`
        element.style.height = `${viewport.height}px`
        render = page.render({
          canvas: element,
          canvasContext: context,
          viewport,
          transform: [ratio, 0, 0, ratio, 0, 0],
        })
        await render.promise
        if (!cancelled) setStatus("ready")
      })
      .catch(() => {
        if (!cancelled) setStatus("error")
      })
    return () => {
      cancelled = true
      render?.cancel()
    }
  }, [pdf, number, visible, width, zoom, thumbnail])
  return (
    <div
      ref={wrapper}
      className={thumbnail ? "min-h-18 w-14" : "w-full min-w-0"}
    >
      {status === "loading" && (
        <Skeleton
          aria-label={thumbnail ? undefined : "กำลังแสดงหน้า PDF"}
          className={thumbnail ? "h-18 w-14" : "h-96 w-full"}
        />
      )}
      {status === "error" && (
        <p
          role={thumbnail ? undefined : "alert"}
          className="p-2 text-xs text-destructive"
        >
          แสดงหน้า PDF ไม่สำเร็จ
        </p>
      )}
      <canvas
        ref={canvas}
        aria-label={`${thumbnail ? "ภาพย่อ" : "PDF"} หน้า ${number}`}
        className={`mx-auto bg-white shadow-sm ${status !== "ready" ? "hidden" : ""}`}
      />
    </div>
  )
}

export function PdfViewer({
  id,
  count,
  pages,
  number,
  onPage,
}: {
  id: string
  count: number
  pages: PageSummary[]
  number: number
  onPage: (n: number) => void
}) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)
  const [error, setError] = useState(false)
  const [revision, setRevision] = useState(0)
  const [zoom, setZoom] = useState(100)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => {
    let cancelled = false
    const base = import.meta.env.BASE_URL
    const task = getDocument({
      url: `${apiBase}/documents/${encodeURIComponent(id)}/file`,
      cMapUrl: `${base}pdfjs/cmaps/`,
      cMapPacked: true,
      standardFontDataUrl: `${base}pdfjs/standard_fonts/`,
      wasmUrl: `${base}pdfjs/wasm/`,
    })
    const deadline = window.setTimeout(() => {
      if (!cancelled) setError(true)
      void task.destroy()
    }, 25000)
    task.promise
      .then((doc) => {
        window.clearTimeout(deadline)
        if (!cancelled) setPdf(doc)
      })
      .catch(() => {
        window.clearTimeout(deadline)
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
      window.clearTimeout(deadline)
      void task.destroy()
    }
  }, [id, revision])
  const commitPage = () => {
    const value = input.current?.value ?? ""
    if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > count) {
      if (input.current) input.current.value = String(number)
      return
    }
    onPage(Number(value))
  }
  return (
    <section
      aria-label="ตัวอ่าน PDF"
      className="flex min-w-0 flex-col overflow-hidden rounded-xl border bg-zinc-100 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-background p-2">
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            aria-label="หน้าก่อนหน้า"
            disabled={number <= 1}
            onClick={() => onPage(number - 1)}
          >
            <ChevronLeft />
          </Button>
          <Input
            key={number}
            ref={input}
            defaultValue={number}
            type="number"
            min={1}
            max={count}
            aria-label="เลขหน้า"
            className="w-16 text-center"
            onBlur={commitPage}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitPage()
            }}
          />
          <span className="text-sm text-muted-foreground">/ {count}</span>
          <Button
            variant="outline"
            size="icon"
            aria-label="หน้าถัดไป"
            disabled={number >= count}
            onClick={() => onPage(number + 1)}
          >
            <ChevronRight />
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            aria-label="ย่อ PDF"
            disabled={zoom <= 50}
            onClick={() => setZoom((z) => z - 25)}
          >
            <Minus />
          </Button>
          <output
            aria-label="ระดับซูม"
            className="min-w-10 text-center text-sm"
          >
            {zoom}%
          </output>
          <Button
            variant="outline"
            size="icon"
            aria-label="ขยาย PDF"
            disabled={zoom >= 200}
            onClick={() => setZoom((z) => z + 25)}
          >
            <Plus />
          </Button>
        </div>
      </div>
      {error ? (
        <div className="space-y-4 p-6">
          <p role="alert">โหลด PDF ไม่สำเร็จ</p>
          <Button
            variant="outline"
            onClick={() => {
              setError(false)
              setPdf(null)
              setRevision((n) => n + 1)
            }}
          >
            ลองโหลด PDF อีกครั้ง
          </Button>
        </div>
      ) : !pdf ? (
        <div role="status" aria-label="กำลังโหลด PDF" className="p-6">
          <Skeleton className="h-96 w-full" />
        </div>
      ) : (
        <div className="flex min-h-140 flex-1 lg:h-[calc(100dvh-220px)] lg:min-h-150">
          <nav
            aria-label="หน้าของเอกสาร"
            className="w-22 shrink-0 space-y-3 overflow-y-auto border-r bg-zinc-50 p-3"
          >
            {Array.from({ length: count }, (_, i) => {
              const page = pages[i]
              const n = i + 1
              return (
                <button
                  key={n}
                  aria-label={`หน้า ${n}${page ? (page.text_passed ? " ผ่านเกณฑ์" : " แนะนำ OCR") : ""}`}
                  aria-current={number === n ? "page" : undefined}
                  onClick={() => onPage(n)}
                  className={`block rounded-sm p-1 text-xs ${number === n ? "ring-2 ring-zinc-900" : "hover:ring-1 hover:ring-zinc-400"}`}
                >
                  <PdfCanvas pdf={pdf} number={n} thumbnail />
                  <span className="mt-1 flex items-center justify-center gap-1">
                    <span
                      aria-hidden
                      className={`size-1.5 rounded-full ${!page ? "bg-zinc-400" : page.text_passed ? "bg-emerald-500" : "bg-amber-500"}`}
                    />
                    {n}
                  </span>
                </button>
              )
            })}
          </nav>
          <div className="min-w-0 flex-1 overflow-auto p-4 sm:p-6">
            <PdfCanvas key={number} pdf={pdf} number={number} zoom={zoom} />
          </div>
        </div>
      )}
    </section>
  )
}
