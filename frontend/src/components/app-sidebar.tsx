import { File, Settings } from "lucide-react"
import { buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function AppSidebar({ active }: { active: "documents" | "settings" }) {
  return (
    <aside
      className="border-b bg-sidebar md:fixed md:inset-y-0 md:left-0 md:w-62 md:border-r md:border-b-0"
      aria-label="เมนูหลัก"
    >
      <div className="flex h-16 items-center gap-2.5 px-5">
        <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-base font-semibold text-primary-foreground">
          D
        </span>
        <span className="text-lg font-semibold tracking-tight">DocFlow</span>
      </div>
      <nav className="flex gap-1 p-3 md:flex-col">
        {(
          [
            {
              key: "documents",
              href: "/documents",
              label: "เอกสาร",
              Icon: File,
            },
            {
              key: "settings",
              href: "/settings",
              label: "ตั้งค่า",
              Icon: Settings,
            },
          ] as const
        ).map(({ key, href, label, Icon }) => (
          <a
            key={key}
            href={href}
            aria-current={active === key ? "page" : undefined}
            className={cn(
              buttonVariants({
                variant: active === key ? "secondary" : "ghost",
              }),
              "h-9 justify-start gap-2 px-2",
              active !== key && "text-muted-foreground"
            )}
          >
            <Icon className="size-4" />
            {label}
          </a>
        ))}
      </nav>
    </aside>
  )
}
