import { SettingsPage } from "@/features/settings/settings-page"
import { DocumentsPage } from "@/features/documents/documents-page"
import { lazy, Suspense } from "react"

const DocumentDetailPage = lazy(() =>
  import("@/features/documents/document-detail-page").then((module) => ({
    default: module.DocumentDetailPage,
  }))
)

export default function App() {
  const path = window.location.pathname.replace(/\/$/, "") || "/"
  if (path === "/documents") return <DocumentsPage />
  const detail = path.match(/^\/documents\/([^/]+)$/)
  if (detail)
    return (
      <Suspense
        fallback={
          <p role="status" className="p-8">
            กำลังโหลดเอกสาร…
          </p>
        }
      >
        <DocumentDetailPage id={detail[1]} />
      </Suspense>
    )
  if (path !== "/" && path !== "/settings")
    return (
      <main className="p-10">
        <h1>ไม่พบหน้า</h1>
        <a href="/documents">กลับไปเอกสารทั้งหมด</a>
      </main>
    )
  return <SettingsPage />
}
