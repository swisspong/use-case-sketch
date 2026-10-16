export type DocumentSummary = {
  id: string
  filename: string
  size_bytes: number
  page_count: number
  uploaded_at: string
  quality_status: "not_checked" | "checked"
  ocr_suggested_count: number | null
}
export type DocumentList = { items: DocumentSummary[]; total: number }
export type UploadResult = { document: DocumentSummary; duration_ms: number }
export const apiBase = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(
  /\/$/,
  ""
)

export class DocumentError extends Error {
  errorCode: string
  constructor(errorCode = "SYS_002") {
    super(errorCode)
    this.errorCode = errorCode
  }
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}
export function summary(value: unknown): DocumentSummary {
  if (
    !object(value) ||
    typeof value.id !== "string" ||
    !/^[0-9a-f-]{36}$/i.test(value.id) ||
    typeof value.filename !== "string" ||
    typeof value.uploaded_at !== "string" ||
    Number.isNaN(Date.parse(value.uploaded_at)) ||
    !Number.isSafeInteger(value.size_bytes) ||
    Number(value.size_bytes) <= 0 ||
    !Number.isSafeInteger(value.page_count) ||
    Number(value.page_count) <= 0 ||
    !(
      (value.quality_status === "not_checked" &&
        value.ocr_suggested_count === null) ||
      (value.quality_status === "checked" &&
        Number.isSafeInteger(value.ocr_suggested_count) &&
        Number(value.ocr_suggested_count) >= 0 &&
        Number(value.ocr_suggested_count) <= Number(value.page_count))
    )
  )
    throw new DocumentError()
  return value as DocumentSummary
}
async function get(path: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(apiBase + path, {
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(25000)])
      : AbortSignal.timeout(25000),
  })
  const data: unknown = await response.json()
  if (!response.ok)
    throw new DocumentError(
      object(data) && typeof data.error_code === "string"
        ? data.error_code
        : undefined
    )
  return data
}
export async function listDocuments(
  page: number,
  signal?: AbortSignal
): Promise<DocumentList> {
  const data = await get(`/documents?page=${page}&page_size=20`, signal)
  if (
    !object(data) ||
    !Array.isArray(data.items) ||
    !Number.isSafeInteger(data.total) ||
    Number(data.total) < data.items.length
  )
    throw new DocumentError()
  return { items: data.items.map(summary), total: Number(data.total) }
}
export async function getDocument(id: string, signal?: AbortSignal) {
  const data = await get(`/documents/${encodeURIComponent(id)}`, signal)
  const doc = summary(data)
  if (
    !object(data) ||
    !Array.isArray(data.pages) ||
    data.pages.length !==
      (doc.quality_status === "checked" ? doc.page_count : 0) ||
    !data.pages.every(
      (p, i) =>
        object(p) &&
        p.number === i + 1 &&
        typeof p.ocr_suggested === "boolean" &&
        typeof p.has_ocr === "boolean" &&
        typeof p.text_passed === "boolean"
    )
  )
    throw new DocumentError()
  return { ...doc, pages: data.pages as PageSummary[] }
}
export function uploadDocument(
  file: File,
  progress: (percent: number) => void
) {
  const xhr = new XMLHttpRequest()
  const promise = new Promise<UploadResult>((resolve, reject) => {
    xhr.open("POST", apiBase + "/documents")
    xhr.timeout = 60000
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable)
        progress(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onerror =
      xhr.ontimeout =
      xhr.onabort =
        () => reject(new DocumentError())
    xhr.onload = () => {
      try {
        if (xhr.status === 413) throw new DocumentError("DOC_002")
        const data: unknown = JSON.parse(xhr.responseText)
        if (xhr.status !== 201)
          throw new DocumentError(
            object(data) && typeof data.error_code === "string"
              ? data.error_code
              : undefined
          )
        if (
          !object(data) ||
          !Number.isSafeInteger(data.duration_ms) ||
          Number(data.duration_ms) < 0
        )
          throw new DocumentError()
        resolve({
          document: summary(data.document),
          duration_ms: Number(data.duration_ms),
        })
      } catch (error) {
        reject(error instanceof DocumentError ? error : new DocumentError())
      }
    }
    const body = new FormData()
    body.append("file", file)
    xhr.send(body)
  })
  return { promise, abort: () => xhr.abort() }
}
export function formatSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.round(bytes / 1024)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
export function formatDate(value: string) {
  const date = new Date(value)
  return `${new Intl.DateTimeFormat("th-TH", { timeZone: "Asia/Bangkok", day: "numeric", month: "short", year: "numeric" }).format(date)} · ${new Intl.DateTimeFormat("th-TH", { timeZone: "Asia/Bangkok", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(date)}`
}

export type PageSummary = {
  number: number
  ocr_suggested: boolean
  has_ocr: boolean
  text_passed: boolean
}
export type DocumentDetail = DocumentSummary & { pages: PageSummary[] }
export type Thresholds = {
  max_garbled_thai_percent: number
  min_text_chars: number
  max_image_percent: number
} & (
  | { max_thai_percent: number; min_thai_percent?: never }
  | { min_thai_percent: number; max_thai_percent?: never }
)
export type Quality = {
  thai_percent: number
  garbled_thai_percent: number
  text_chars: number
  image_percent: number
  failed: (keyof Thresholds)[]
  passed: boolean
}
export type OcrOutput = {
  preset_name: string
  model_id: string
  created_at: string
  text: string
  quality: Quality
}
export type PageResult = {
  number: number
  thresholds: Thresholds
  parser: { text: string; quality: Quality }
  ocr: OcrOutput | null
}
export type OcrFailureReason =
  "provider_timeout" | "provider_error" | "invalid_output"
export type OcrResult =
  | {
      page: number
      status: "ok"
      ocr: OcrOutput
      text_passed: boolean
      duration_ms: number
    }
  | {
      page: number
      status: "failed"
      reason: OcrFailureReason
      duration_ms: number
    }
export type OcrPreset = { id: string; name: string; is_default: boolean }
export async function getPage(
  id: string,
  number: number,
  signal: AbortSignal
): Promise<PageResult> {
  const data = await get(
    `/documents/${encodeURIComponent(id)}/pages/${number}`,
    signal
  )
  if (
    !object(data) ||
    data.number !== number ||
    !object(data.thresholds) ||
    !object(data.parser) ||
    typeof data.parser.text !== "string" ||
    !object(data.parser.quality)
  )
    throw new DocumentError()
  const thresholds = data.thresholds
  const legacy = Object.hasOwn(thresholds, "min_thai_percent")
  if (legacy === Object.hasOwn(thresholds, "max_thai_percent"))
    throw new DocumentError()
  const keys = [
    legacy ? "min_thai_percent" : "max_thai_percent",
    "max_garbled_thai_percent",
    "min_text_chars",
    "max_image_percent",
  ]
  if (
    !keys.every(
      (k) =>
        Number.isSafeInteger(thresholds[k]) &&
        Number(thresholds[k]) >= 0 &&
        (k === "min_text_chars" || Number(thresholds[k]) <= 100)
    ) ||
    !validQuality(data.parser.quality, keys) ||
    !(data.ocr === null || validOcr(data.ocr, keys))
  )
    throw new DocumentError()
  return data as PageResult
}

function validQuality(q: unknown, keys: string[]) {
  return (
    object(q) &&
    ["thai_percent", "garbled_thai_percent", "image_percent"].every(
      (k) =>
        typeof q[k] === "number" &&
        Number.isFinite(q[k]) &&
        q[k] >= 0 &&
        q[k] <= 100
    ) &&
    Number.isSafeInteger(q.text_chars) &&
    Number(q.text_chars) >= 0 &&
    typeof q.passed === "boolean" &&
    Array.isArray(q.failed) &&
    q.failed.every((k) => keys.includes(k)) &&
    q.passed === (q.failed.length === 0)
  )
}

function validOcr(value: unknown, keys: string[]) {
  return (
    object(value) &&
    typeof value.preset_name === "string" &&
    typeof value.model_id === "string" &&
    typeof value.text === "string" &&
    typeof value.created_at === "string" &&
    !Number.isNaN(Date.parse(value.created_at)) &&
    validQuality(value.quality, keys)
  )
}

const allCriteria = [
  "max_thai_percent",
  "min_thai_percent",
  "max_garbled_thai_percent",
  "min_text_chars",
  "max_image_percent",
]

/** Errors from the OCR action: provider failures are a 200 result, not an error. */
export class OcrError extends DocumentError {
  network: boolean
  constructor(errorCode = "SYS_002", network = false) {
    super(errorCode)
    this.network = network
  }
}

export async function listOcrPresets(): Promise<OcrPreset[]> {
  let response: Response
  try {
    response = await fetch(apiBase + "/llm/presets", {
      signal: AbortSignal.timeout(25000),
    })
  } catch {
    throw new OcrError("SYS_002", true)
  }
  const data: unknown = await response.json().catch(() => null)
  if (
    !response.ok ||
    !Array.isArray(data) ||
    !data.every(
      (p) =>
        object(p) &&
        typeof p.id === "string" &&
        typeof p.name === "string" &&
        typeof p.is_default === "boolean"
    )
  )
    throw new OcrError()
  return data as OcrPreset[]
}

export async function ocrPage(
  id: string,
  page: number,
  presetId: string
): Promise<OcrResult> {
  let response: Response
  try {
    response = await fetch(
      `${apiBase}/documents/${encodeURIComponent(id)}/ocr`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ page, preset_id: presetId }),
        // Provider deadline is 110 s per page (all passes); render can take 30 s more.
        signal: AbortSignal.timeout(150000),
      }
    )
  } catch {
    throw new OcrError("SYS_002", true)
  }
  if ([502, 503, 504].includes(response.status))
    throw new OcrError("SYS_002", true)
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok)
    throw new OcrError(
      object(data) && typeof data.error_code === "string"
        ? data.error_code
        : undefined
    )
  if (
    !object(data) ||
    data.page !== page ||
    !Number.isSafeInteger(data.duration_ms) ||
    !(
      (data.status === "ok" &&
        typeof data.text_passed === "boolean" &&
        validOcr(data.ocr, allCriteria)) ||
      (data.status === "failed" &&
        ["provider_timeout", "provider_error", "invalid_output"].includes(
          data.reason as string
        ))
    )
  )
    throw new OcrError()
  return data as OcrResult
}
