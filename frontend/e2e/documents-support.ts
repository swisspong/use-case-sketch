import type { APIRequestContext } from "@playwright/test"
import { baseline, expect } from "./support"

// Actual two-page PDF, with text on page 1 and a blank second page.
export function twoPagePdf(
  text = "Hello PDF",
  mapping?: Record<string, string>
) {
  const stream = `BT /F1 16 Tf 20 150 Td (${text}) Tj ET`
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << >> >>",
    `<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica ${mapping ? "/ToUnicode 7 0 R" : ""} >>`,
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ]
  if (mapping) {
    const entries = Object.entries(mapping)
      .map(
        ([from, to]) =>
          `<${from.charCodeAt(0).toString(16).padStart(2, "0")}> <${Array.from(
            to
          )
            .map((c) => c.charCodeAt(0).toString(16).padStart(4, "0"))
            .join("")}>`
      )
      .join("\n")
    const cmap = `/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /Thai def /CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange ${Object.keys(mapping).length} beginbfchar\n${entries}\nendbfchar endcmap CMapName currentdict /CMap defineresource pop end end`
    objects.push(`<< /Length ${cmap.length} >>\nstream\n${cmap}\nendstream`)
  }
  let data = "%PDF-1.4\n"
  const offsets = [0]
  objects.forEach((object, index) => {
    offsets.push(Buffer.byteLength(data))
    data += `${index + 1} 0 obj\n${object}\nendobj\n`
  })
  const xref = Buffer.byteLength(data)
  data += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets
    .slice(1)
    .map((n) => `${String(n).padStart(10, "0")} 00000 n \n`)
    .join(
      ""
    )}trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`
  return Buffer.from(data)
}

export async function seed(request: APIRequestContext) {
  await request.patch("/api/text-quality/thresholds", {
    data: { ...baseline, max_thai_percent: 0, min_text_chars: 1 },
  })
  const r = await request.post("/api/documents", {
    multipart: {
      file: {
        name: "รายละเอียด.pdf",
        mimeType: "application/pdf",
        buffer: twoPagePdf(),
      },
    },
  })
  expect(r.status()).toBe(201)
  const result = (await r.json()) as {
    document: { id: string; ocr_suggested_count: number }
  }
  expect(result.document.ocr_suggested_count).toBe(1)
  return result.document.id
}
