import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { AppSidebar } from "@/components/app-sidebar"
import { Button, buttonVariants } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Toaster } from "@/components/ui/sonner"
import {
  apiBase,
  DocumentError,
  formatDate,
  formatSize,
  getDocument,
  type DocumentDetail,
} from "./api"
import { Results } from "./page-results"
import { PdfViewer } from "./pdf-viewer"

function pageFromUrl() {
  const raw = new URLSearchParams(window.location.search).get("page") ?? "1"
  return /^\d+$/.test(raw) && Number.isSafeInteger(Number(raw))
    ? Number(raw)
    : 0
}

export function DocumentDetailPage({ id }: { id: string }) {
  const [state, setState] = useState<{
    id: string
    data?: DocumentDetail
    error?: string
  } | null>(null)
  const [revision, setRevision] = useState(0)
  const [requestedNumber, setNumber] = useState(pageFromUrl)
  const changePage = useCallback((next: number) => {
    const url = new URL(window.location.href)
    url.searchParams.set("page", String(next))
    window.history.pushState(null, "", url)
    setNumber(next)
  }, [])
  const missingPage = useCallback(() => {
    changePage(1)
    toast.error("ไม่พบหน้าที่ระบุ")
  }, [changePage])
  const missingDocument = useCallback(
    () => setState({ id, error: "ไม่พบเอกสาร" }),
    [id]
  )
  // Use the OCR response directly for the thumbnail colour; no refetch needed.
  const ocrSaved = useCallback(
    (page: number, textPassed: boolean) =>
      setState((current) =>
        current?.id === id && current.data
          ? {
              ...current,
              data: {
                ...current.data,
                pages: current.data.pages.map((p) =>
                  p.number === page
                    ? { ...p, has_ocr: true, text_passed: textPassed }
                    : p
                ),
              },
            }
          : current
      ),
    [id]
  )
  useEffect(() => {
    const update = () => setNumber(pageFromUrl())
    window.addEventListener("popstate", update)
    return () => window.removeEventListener("popstate", update)
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    getDocument(id, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ id, data })
      })
      .catch((failure) => {
        if (!controller.signal.aborted)
          setState({
            id,
            error:
              failure instanceof DocumentError &&
              ["DOC_007", "REQ_001"].includes(failure.errorCode)
                ? "ไม่พบเอกสาร"
                : "โหลดเอกสารไม่สำเร็จ",
          })
      })
    return () => controller.abort()
  }, [id, revision])
  const current = state?.id === id ? state : null
  const document = current?.data
  const number =
    document && requestedNumber >= 1 && requestedNumber <= document.page_count
      ? requestedNumber
      : 1
  useEffect(() => {
    if (
      document &&
      (requestedNumber < 1 || requestedNumber > document.page_count)
    ) {
      const url = new URL(window.location.href)
      url.searchParams.set("page", "1")
      window.history.replaceState(null, "", url)
      toast.error("ไม่พบหน้าที่ระบุ")
    }
  }, [document, requestedNumber])
  const validPage = number >= 1 && document && number <= document.page_count
  return (
    <div className="min-h-dvh bg-background text-foreground">
      <a
        href="#document-content"
        className="sr-only z-50 bg-background p-3 focus:not-sr-only focus:fixed"
      >
        ข้ามไปเนื้อหา
      </a>
      <AppSidebar active="documents" />
      <main
        id="document-content"
        className="min-w-0 space-y-5 px-5 py-6 md:ml-62 md:px-8"
      >
        <a
          href="/documents"
          className="text-sm text-muted-foreground hover:underline"
        >
          ← กลับไปเอกสารทั้งหมด
        </a>
        {current?.error ? (
          <section role="alert" className="space-y-4 rounded-xl border p-6">
            <h1 className="text-xl font-semibold">{current.error}</h1>
            {current.error !== "ไม่พบเอกสาร" && (
              <Button
                variant="outline"
                onClick={() => {
                  setState(null)
                  setRevision((n) => n + 1)
                }}
              >
                ลองอีกครั้ง
              </Button>
            )}
          </section>
        ) : !document ? (
          <div role="status" aria-label="กำลังโหลดเอกสาร">
            <Skeleton className="h-48 w-full" />
          </div>
        ) : (
          <>
            <header className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs font-medium text-red-600">
                  PDF
                </span>
                <div className="min-w-0">
                  <h1 className="text-xl font-semibold break-all">
                    {document.filename}
                  </h1>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {document.page_count} หน้า ·{" "}
                    {formatSize(document.size_bytes)} · อัปโหลด{" "}
                    {formatDate(document.uploaded_at)}
                  </p>
                </div>
              </div>
              <a
                href={`${apiBase}/documents/${document.id}/original`}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({ variant: "outline", size: "sm" })}
              >
                เปิด PDF ต้นฉบับ
              </a>
            </header>
            {validPage && (
              <div className="grid min-w-0 gap-5 xl:grid-cols-2">
                <PdfViewer
                  key={id}
                  id={id}
                  count={document.page_count}
                  pages={document.pages}
                  number={number}
                  onPage={changePage}
                />
                {document.quality_status === "checked" ? (
                  <Results
                    id={id}
                    number={number}
                    onMissing={missingPage}
                    onMissingDocument={missingDocument}
                    onOcrSaved={ocrSaved}
                  />
                ) : (
                  <section className="rounded-xl border p-5">
                    <h2 className="font-semibold">ยังไม่ได้ตรวจคุณภาพ</h2>
                    <p className="mt-2 text-sm text-muted-foreground">
                      เอกสารนี้บันทึกไว้ก่อนมีการสกัดข้อความและตรวจคุณภาพรายหน้า
                      กรุณาอัปโหลดไฟล์อีกครั้งเพื่อดูผลตรวจ
                    </p>
                  </section>
                )}
              </div>
            )}
          </>
        )}
      </main>
      <Toaster theme="light" position="bottom-right" />
    </div>
  )
}
