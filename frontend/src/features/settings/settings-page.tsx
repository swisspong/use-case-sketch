import { useEffect, useState } from "react"
import { AppSidebar } from "@/components/app-sidebar"
import { Toaster } from "@/components/ui/sonner"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "@/components/ui/alert-dialog"
import { useThresholds } from "./use-thresholds"
import { ThresholdPanel } from "./threshold-panel"
import { PresetsPanel } from "./presets-panel"

export function SettingsPage() {
  // Deep link from the OCR action: /settings?tab=llm
  const [tab, setTab] = useState(() =>
    new URLSearchParams(window.location.search).get("tab") === "llm" ? "llm" : "thresholds")
  const [destination, setDestination] = useState<string | null>(null)
  const state = useThresholds(tab === "thresholds")
  useEffect(() => {
    if (!state.dirty) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = "" }
    window.addEventListener("beforeunload", warn)
    return () => window.removeEventListener("beforeunload", warn)
  }, [state.dirty])
  const navigate = (next: string) => {
    if (next === tab) return
    if (state.dirty && !state.saving) setDestination(next)
    else setTab(next)
  }
  return <div className="min-h-dvh bg-background text-foreground">
    <a href="#settings-content" className="sr-only z-50 bg-background p-3 focus:not-sr-only focus:fixed">ข้ามไปเนื้อหา</a>
    <AppSidebar active="settings" />
    <main id="settings-content" className="px-5 py-8 sm:px-8 md:ml-62 md:px-12 md:py-10">
      <header className="mb-6">
        <h1 className="text-2xl leading-[29px] font-semibold">ตั้งค่า</h1>
        <p className="mt-1 text-sm leading-[17px] text-muted-foreground">ปรับเกณฑ์ตรวจคุณภาพข้อความ และโมเดล LLM ที่ใช้ประมวลผลเอกสาร</p>
      </header>
      <Tabs value={tab} onValueChange={navigate} className="gap-6">
        <TabsList className="h-9 group-data-horizontal/tabs:h-9" aria-label="หมวดการตั้งค่า">
          <TabsTrigger className="px-3" value="thresholds">เกณฑ์คุณภาพข้อความ</TabsTrigger>
          <TabsTrigger className="px-3" value="llm">LLM Model</TabsTrigger>
        </TabsList>
        <TabsContent value="thresholds" forceMount className="data-[state=inactive]:hidden"><ThresholdPanel state={state} /></TabsContent>
        <TabsContent value="llm" forceMount className="data-[state=inactive]:hidden"><PresetsPanel active={tab === "llm"} /></TabsContent>
      </Tabs>
    </main>
    <AlertDialog open={destination !== null} onOpenChange={open => { if (!open) setDestination(null) }}>
      <AlertDialogContent className="sm:max-w-120">
        <AlertDialogHeader>
          <AlertDialogTitle>ยังไม่ได้บันทึกการเปลี่ยนแปลง</AlertDialogTitle>
          <AlertDialogDescription>ค่าเกณฑ์ที่แก้ไว้จะหายถ้าออกจากหน้านี้ · กด “อยู่ต่อ” เพื่อกลับไปบันทึก หรือทิ้งการแก้ไข</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>อยู่ต่อ</AlertDialogCancel>
          <AlertDialogAction onClick={() => { state.reset(); if (destination) setTab(destination); setDestination(null) }}>ทิ้งการแก้ไข</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
    <Toaster theme="light" position="bottom-right" />
  </div>
}
