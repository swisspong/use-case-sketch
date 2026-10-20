import { useCallback, useEffect, useRef, useState } from "react"
import { FileText, Upload, LoaderCircle } from "lucide-react"
import { toast } from "sonner"
import { AppSidebar } from "@/components/app-sidebar"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Toaster } from "@/components/ui/sonner"
import {
  DocumentError,
  formatDate,
  formatSize,
  listDocuments,
  uploadDocument,
  type DocumentList,
} from "./api"

const errors: Record<string, string> = {
  DOC_001: "รองรับเฉพาะไฟล์ PDF เท่านั้น",
  DOC_002: "ไฟล์ใหญ่เกิน 20 MB",
  DOC_003: "อัปโหลดได้ครั้งละ 1 ไฟล์",
  DOC_004: "อ่าน PDF ไม่สำเร็จ · ไฟล์อาจเสียหรือมีรหัสผ่าน",
  DOC_006: "ประมวลผลไม่ทันเวลา",
}

export function DocumentsPage() {
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [list, setList] = useState<DocumentList | null>(null)
  const [loadError, setLoadError] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [dragging, setDragging] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const pending = useRef<ReturnType<typeof uploadDocument> | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      pending.current?.abort()
    }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    listDocuments(page, controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        if (!data.items.length && data.total > 0 && page > 1) {
          setPage(Math.ceil(data.total / 20))
          return
        }
        setList(data)
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError(true)
      })
    return () => controller.abort()
  }, [page, revision])
  useEffect(() => {
    if (!busy) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ""
    }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [busy])
  const selectFiles = useCallback((files: FileList | null) => {
    if (pending.current) return
    const candidates = Array.from(files ?? [])
    setFile(null)
    setError("")
    setProgress(0)
    if (input.current) input.current.value = ""
    if (!candidates.length) return
    const candidate = candidates[0]
    const code =
      candidates.length > 1
        ? "DOC_003"
        : !candidate.name.toLowerCase().endsWith(".pdf")
          ? "DOC_001"
          : candidate.size > 20 * 1024 * 1024
            ? "DOC_002"
            : null
    if (code) {
      setError(errors[code])
      return
    }
    setFile(candidate)
  }, [])
  const refresh = () => {
    setList(null)
    setLoadError(false)
    setRevision((n) => n + 1)
  }
  const changePage = (next: number) => {
    setList(null)
    setLoadError(false)
    setPage(next)
  }
  const upload = async () => {
    if (!file || pending.current) return
    setBusy(true)
    setError("")
    setProgress(0)
    const request = uploadDocument(file, setProgress)
    pending.current = request
    try {
      const result = await request.promise
      if (!mounted.current) return
      toast.success(`อัปโหลด ${result.document.filename} แล้ว`, {
        description: `${result.document.page_count} หน้า · ประมวลผล ${Math.round(result.duration_ms / 1000)} วินาที`,
      })
      if (page === 1 && list)
        setList((current) =>
          current
            ? {
                items: [result.document, ...current.items].slice(0, 20),
                total: current.total + 1,
              }
            : current
        )
      else refresh()
    } catch (failure) {
      if (mounted.current)
        setError(
          failure instanceof DocumentError
            ? (errors[failure.errorCode] ??
                "อัปโหลดไม่สำเร็จ · กรุณาเลือกไฟล์ใหม่")
            : "อัปโหลดไม่สำเร็จ · กรุณาเลือกไฟล์ใหม่"
        )
    } finally {
      pending.current = null
      if (mounted.current) {
        setBusy(false)
        setFile(null)
        setProgress(0)
        if (input.current) input.current.value = ""
      }
    }
  }
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <a
        href="#documents-content"
        className="sr-only z-50 bg-background p-3 focus:not-sr-only focus:fixed"
      >
        ข้ามไปเนื้อหา
      </a>
      <AppSidebar active="documents" />
      <main
        id="documents-content"
        className="min-w-0 space-y-6 px-5 py-8 sm:px-8 md:ml-62 md:px-12 md:py-10"
      >
        <header>
          <h1 className="text-2xl font-semibold">เอกสาร</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            อัปโหลด PDF เพื่อดึงข้อความและตรวจคุณภาพ
          </p>
        </header>
        <section
          aria-labelledby="upload-title"
          className="space-y-4 rounded-xl border p-6"
        >
          <div>
            <h2 id="upload-title" className="font-semibold">
              อัปโหลดเอกสาร
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              ดึงข้อความและตรวจคุณภาพรายหน้า พร้อมเก็บไฟล์ต้นฉบับ
            </p>
          </div>
          <div
            onDragOver={(event) => {
              event.preventDefault()
              if (!busy) setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              selectFiles(event.dataTransfer.files)
            }}
            className={`flex min-h-48 flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-6 text-center ${dragging ? "border-primary bg-muted" : "border-border"}`}
          >
            <input
              ref={input}
              type="file"
              accept=".pdf,application/pdf"
              aria-label="ไฟล์ PDF"
              className="sr-only"
              tabIndex={-1}
              disabled={busy}
              onChange={(event) => {
                const files = event.target.files
                if (files?.length) selectFiles(files)
              }}
            />
            {busy ? (
              <>
                <LoaderCircle className="size-7 animate-spin text-muted-foreground" />
                <p role="status">
                  {progress < 100
                    ? `กำลังอัปโหลด ${progress}%`
                    : "กำลังดึงข้อความและตรวจคุณภาพ"}
                </p>
                <progress
                  aria-label="ความคืบหน้าการอัปโหลด"
                  max={100}
                  value={progress}
                  className="w-full max-w-sm"
                />
                <p className="text-sm text-muted-foreground">
                  กรุณาเปิดหน้านี้ไว้จนกว่าจะบันทึกสำเร็จ
                </p>
              </>
            ) : (
              <>
                <Upload className="size-7 text-muted-foreground" />
                {file ? (
                  <>
                    <p className="max-w-full font-medium break-all">
                      {file.name}{" "}
                      <span className="font-normal text-muted-foreground">
                        · {formatSize(file.size)}
                      </span>
                    </p>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        onClick={() => input.current?.click()}
                      >
                        เปลี่ยนไฟล์
                      </Button>
                      <Button onClick={upload}>อัปโหลด</Button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-sm">ลากไฟล์ PDF มาวางที่นี่ หรือ</p>
                    <Button
                      variant="outline"
                      onClick={() => input.current?.click()}
                    >
                      เลือกไฟล์
                    </Button>
                  </>
                )}
                <p className="text-xs text-muted-foreground">
                  PDF เท่านั้น · ครั้งละ 1 ไฟล์ · ขนาดไม่เกิน 20 MB
                </p>
              </>
            )}
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </section>
        <section
          aria-labelledby="list-title"
          aria-busy={!list && !loadError}
          className="overflow-hidden rounded-xl border"
        >
          <div className="flex items-center gap-2 border-b px-6 py-5">
            <h2 id="list-title" className="font-semibold">
              เอกสารทั้งหมด
            </h2>
            <Badge variant="secondary">{list?.total ?? "–"}</Badge>
          </div>
          {loadError ? (
            <div className="space-y-3 p-10 text-center">
              <p role="alert">โหลดรายการไม่สำเร็จ</p>
              <Button variant="outline" onClick={refresh}>
                ลองอีกครั้ง
              </Button>
            </div>
          ) : !list ? (
            <div
              role="status"
              aria-label="กำลังโหลดรายการ"
              className="space-y-5 p-6"
            >
              {Array.from({ length: 5 }, (_, n) => (
                <Skeleton key={n} className="h-9 w-full" />
              ))}
            </div>
          ) : list.total === 0 ? (
            <div className="flex flex-col items-center gap-2 px-6 py-14">
              <FileText className="mb-2 size-8 text-muted-foreground" />
              <p className="font-medium">ยังไม่มีเอกสาร</p>
              <p className="text-sm text-muted-foreground">
                เลือกไฟล์ PDF ด้านบนเพื่อเริ่มต้น
              </p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-175 text-left text-sm">
                  <thead className="border-b bg-muted/40 text-muted-foreground">
                    <tr>
                      {[
                        "ชื่อเอกสาร",
                        "ขนาด",
                        "หน้า",
                        "อัปโหลดเมื่อ",
                        "ผลตรวจ",
                      ].map((label) => (
                        <th key={label} className="px-6 py-3 font-medium">
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {list.items.map((document) => (
                      <tr
                        key={document.id}
                        className="cursor-pointer border-b hover:bg-muted/40"
                        onClick={(event) => {
                          if (!(event.target as HTMLElement).closest("a"))
                            window.location.assign(`/documents/${document.id}`)
                        }}
                      >
                        <td className="px-6 py-5">
                          <a
                            className="flex items-center gap-3 font-medium hover:underline focus-visible:underline"
                            href={`/documents/${document.id}`}
                          >
                            <FileText className="size-5 shrink-0 text-muted-foreground" />
                            <span className="max-w-72 truncate">
                              {document.filename}
                            </span>
                          </a>
                        </td>
                        <td className="px-6 py-5 whitespace-nowrap text-muted-foreground">
                          {formatSize(document.size_bytes)}
                        </td>
                        <td className="px-6 py-5">{document.page_count}</td>
                        <td className="px-6 py-5 whitespace-nowrap text-muted-foreground">
                          {formatDate(document.uploaded_at)}
                        </td>
                        <td className="px-6 py-5 whitespace-nowrap">
                          <Badge
                            variant="outline"
                            className={
                              document.quality_status === "checked"
                                ? document.ocr_suggested_count === 0
                                  ? "border-emerald-200 text-emerald-700"
                                  : "border-amber-200 text-amber-700"
                                : ""
                            }
                          >
                            {document.quality_status !== "checked"
                              ? "ยังไม่ได้ตรวจคุณภาพ"
                              : document.ocr_suggested_count === 0
                                ? "ผ่านเกณฑ์"
                                : `แนะนำ OCR ${document.ocr_suggested_count} หน้า`}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4">
                <p className="text-xs text-muted-foreground">
                  แสดง {(page - 1) * 20 + 1}–{Math.min(page * 20, list.total)}{" "}
                  จาก {list.total} รายการ
                </p>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={page === 1 || busy}
                    onClick={() => changePage(page - 1)}
                  >
                    ก่อนหน้า
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={page * 20 >= list.total || busy}
                    onClick={() => changePage(page + 1)}
                  >
                    ถัดไป
                  </Button>
                </div>
              </div>
            </>
          )}
        </section>
      </main>
      <Toaster theme="light" position="bottom-right" />
    </div>
  )
}
