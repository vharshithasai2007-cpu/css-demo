const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: 'Submitted',
  UNDER_REVIEW: 'Under review',
  REPLY_SENT: 'Reply sent',
  RESOLVED: 'Resolved',
}

type StatusBadgeProps = {
  status: string
  label?: string
}

export default function StatusBadge({ status, label }: StatusBadgeProps) {
  return (
    <span className="portal-status-badge">{label ?? STATUS_LABELS[status] ?? status}</span>
  )
}
