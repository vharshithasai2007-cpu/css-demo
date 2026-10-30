export const PORTAL_NOTICE_TEXT =
  'EDUCATIONAL DEMO — UNOFFICIAL CSS REPLICA. NOT CONNECTED TO THE LIVE AICTE PORTAL. SUBMISSIONS ARE SIMULATED.'

export default function NoticeBar() {
  return (
    <div className="portal-notice" role="note" aria-label="Demonstration notice">
      {PORTAL_NOTICE_TEXT}
    </div>
  )
}
