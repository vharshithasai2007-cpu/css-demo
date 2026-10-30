const DATE_FORMATTER = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeZone: 'Asia/Kolkata',
})

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat('en-IN', {
  dateStyle: 'medium',
  timeStyle: 'short',
  timeZone: 'Asia/Kolkata',
})

function parsePortalDate(value: string | Date): Date {
  if (value instanceof Date) return value
  // Portal timestamps are stored as naive UTC. Treat a missing zone as UTC so
  // the displayed Asia/Kolkata time is correct.
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value)
  return new Date(hasZone ? value : `${value}Z`)
}

export function formatPortalDate(value: string | Date | null | undefined): string {
  if (!value) return '—'
  const date = parsePortalDate(value)
  return Number.isNaN(date.getTime()) ? '—' : DATE_FORMATTER.format(date)
}

export function formatPortalDateTime(
  value: string | Date | null | undefined,
): string {
  if (!value) return '—'
  const date = parsePortalDate(value)
  return Number.isNaN(date.getTime()) ? '—' : DATE_TIME_FORMATTER.format(date)
}
