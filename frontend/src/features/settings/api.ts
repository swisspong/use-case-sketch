export const thresholdKeys = ["max_thai_percent", "max_garbled_thai_percent", "min_text_chars", "max_image_percent"] as const
export type ThresholdKey = (typeof thresholdKeys)[number]
export type ThresholdValues = Record<ThresholdKey, number>
export type Thresholds = ThresholdValues & { defaults: ThresholdValues }
export type Preset = { id: string; name: string; model_id: string; base_url: string; is_default: boolean }
export type PresetFields = { name: string; model_id: string; base_url: string; api_key: string }
export type PresetField = keyof PresetFields
export type ConnectionResult =
  | { ok: true; latency_ms: number }
  | { ok: false; field: "api_key" | "model_id" | "base_url" | null; reason: "unauthorized" | "model_not_found" | "unreachable" | "upstream_error"; upstream_status?: number }

export class ApiError extends Error {
  errorCode: string
  field?: string
  constructor(errorCode = "SYS_002", field?: string) {
    super(errorCode)
    this.errorCode = errorCode
    this.field = field
  }
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "")

async function request(path: string, method = "GET", body?: unknown): Promise<unknown> {
  try {
    const response = await fetch(baseUrl + path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(25000),
    })
    if (!response.ok) {
      const data = await response.json().catch(() => null)
      throw new ApiError(typeof data?.error_code === "string" ? data.error_code : "SYS_002",
        typeof data?.field === "string" ? data.field : undefined)
    }
    return response.status === 204 ? undefined : await response.json()
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError()
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}
function isThresholdValues(value: unknown): value is ThresholdValues {
  return isObject(value) && thresholdKeys.every(key => typeof value[key] === "number"
    && Number.isSafeInteger(value[key]) && (value[key] as number) >= 0
    && (key === "min_text_chars" || (value[key] as number) <= 100))
}
function thresholds(value: unknown): Thresholds {
  if (!isObject(value) || !isThresholdValues(value.defaults) || !isThresholdValues(value)) throw new ApiError()
  return value as Thresholds
}
function preset(value: unknown): Preset {
  if (!isObject(value) || !["id", "name", "model_id", "base_url"].every(key => typeof value[key] === "string")
      || typeof value.is_default !== "boolean") throw new ApiError()
  return value as Preset
}
function connectionResult(value: unknown): ConnectionResult {
  if (!isObject(value)) throw new ApiError()
  if (value.ok === true && typeof value.latency_ms === "number") return value as ConnectionResult
  if (value.ok === false && [null, "api_key", "model_id", "base_url"].includes(value.field as string | null)
      && ["unauthorized", "model_not_found", "unreachable", "upstream_error"].includes(value.reason as string)) return value as ConnectionResult
  throw new ApiError()
}

export const api = {
  getThresholds: async () => thresholds(await request("/text-quality/thresholds")),
  updateThresholds: async (data: Partial<ThresholdValues>) => thresholds(await request("/text-quality/thresholds", "PATCH", data)),
  listPresets: async (): Promise<Preset[]> => {
    const data = await request("/llm/presets")
    if (!Array.isArray(data)) throw new ApiError()
    return data.map(preset)
  },
  savePreset: async (id: string | undefined, data: Partial<PresetFields>) => preset(await request(
    id ? `/llm/presets/${id}` : "/llm/presets", id ? "PATCH" : "POST", data)),
  setDefault: async (id: string) => preset(await request(`/llm/presets/${id}/default`, "PUT")),
  deletePreset: async (id: string) => { await request(`/llm/presets/${id}`, "DELETE") },
  testConnection: async (id: string | undefined, data: Partial<Omit<PresetFields, "name">>) => connectionResult(await request(
    id ? `/llm/presets/${id}/test` : "/llm/presets/test", "POST", data)),
}
