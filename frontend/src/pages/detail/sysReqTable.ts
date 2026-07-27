export interface SysReqRow {
  label: string
  value: string
}

export interface ParsedRequirements {
  rows: SysReqRow[]
  notes: string[]
}

const TIER_LABEL_RE = /^\s*(minimum|recommended)\s*:?\s*\r?\n?/i
const BLOCK_TAG_RE = /<\s*(br|\/li|\/p|\/div|\/ul|\/tr)[^>]*>/gi
const TAG_RE = /<[^>]*>/g

// Real component labels are short ("OS", "Processor", "Additional Notes"). Anything
// longer is prose that merely happens to contain a colon, so it stays a plain line.
const MAX_LABEL_LENGTH = 32
const MAX_LABEL_WORDS = 4

const ENTITIES: Record<string, string> = {
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
  '&apos;': "'",
  '&nbsp;': ' ',
}

// Steam requirements arrive already flattened by the backend, but the RAWG
// import path stores the provider's markup verbatim — so tags can still reach us.
function toPlainText(raw: string): string {
  return raw
    .replace(BLOCK_TAG_RE, '\n')
    .replace(TAG_RE, '')
    .replace(/&[a-z]+;|&#\d+;/gi, (entity) => ENTITIES[entity.toLowerCase()] ?? entity)
    .replace(TIER_LABEL_RE, '')
}

function cleanLabel(raw: string): string {
  const label = raw.replace(/[*\s]+$/, '').replace(/^[-•\s]+/, '').trim()
  if (label.length > MAX_LABEL_LENGTH || label.split(/\s+/).length > MAX_LABEL_WORDS) return ''
  return label
}

export function parseRequirements(raw: string): ParsedRequirements {
  const rows: SysReqRow[] = []
  const notes: string[] = []

  for (const line of toPlainText(raw).split('\n')) {
    const text = line.replace(/^[-•\s]+/, '').trim()
    if (!text) continue

    const separator = text.indexOf(':')
    const label = separator > 0 ? cleanLabel(text.slice(0, separator)) : ''
    const value = separator > 0 ? text.slice(separator + 1).trim() : text

    if (!label || !value) {
      const previous = rows[rows.length - 1]
      if (previous) previous.value = `${previous.value} ${text}`.trim()
      else notes.push(text)
      continue
    }
    rows.push({ label, value })
  }

  return { notes, rows }
}
