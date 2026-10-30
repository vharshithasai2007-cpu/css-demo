import { useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { Link, useParams } from 'react-router-dom'
import portalApi, {
  type PortalMeta,
  type PortalRequestDetail,
  type PortalReply,
  type PortalStatusEvent,
} from '../api'
import DataTable, { type DataTableColumn } from '../components/DataTable'
import DefinitionTable from '../components/DefinitionTable'
import InfoPanel from '../components/InfoPanel'
import PageHeading from '../components/PageHeading'
import StatusBadge from '../components/StatusBadge'
import { formatPortalDateTime } from '../format'

const REFETCH_INTERVAL_MS = 10000

const statusEventColumns: DataTableColumn<PortalStatusEvent>[] = [
  {
    key: 'created_at',
    header: 'Date and time',
    render: (event) => formatPortalDateTime(event.created_at),
  },
  {
    key: 'status',
    header: 'Status',
    render: (event) => <StatusBadge status={event.status} />,
  },
  {
    key: 'remarks',
    header: 'Remarks',
    render: (event) => event.remarks ?? '—',
  },
  {
    key: 'actor',
    header: 'Updated by',
    render: (event) => event.actor ?? '—',
  },
]

export default function RequestDetail() {
  const { ref } = useParams<{ ref: string }>()
  const reference = (ref ?? '').trim().toUpperCase()

  const metaQuery = useQuery({
    queryKey: ['portal', 'meta'],
    queryFn: async () => {
      const response = await portalApi.get<PortalMeta>('/portal/meta')
      return response.data
    },
  })

  const detailQuery = useQuery({
    queryKey: ['portal', 'request', reference],
    queryFn: async () => {
      const response = await portalApi.get<PortalRequestDetail>(
        `/portal/v2/requests/${encodeURIComponent(reference)}`,
      )
      return response.data
    },
    enabled: Boolean(reference),
    refetchInterval: (query) => {
      const request = query.state.data
      if (!request) return false
      return request.status === 'RESOLVED' ? false : REFETCH_INTERVAL_MS
    },
  })

  const categoryLabels = new Map(
    (metaQuery.data?.categories ?? []).map((item) => [item.value, item.label]),
  )
  const requestTypeLabels = new Map(
    (metaQuery.data?.request_types ?? []).map((item) => [item.value, item.label]),
  )

  const categoryLabel = (value: string | null) =>
    value ? (categoryLabels.get(value) ?? value) : 'Not applicable'
  const requestTypeLabel = (value: string | null) =>
    value ? (requestTypeLabels.get(value) ?? value) : 'Not recorded (legacy)'

  const notFound =
    isAxiosError(detailQuery.error) &&
    detailQuery.error.response?.status === 404

  if (detailQuery.isLoading) {
    return (
      <>
        <PageHeading title="Request details" />
        <p>Loading request…</p>
      </>
    )
  }

  if (notFound) {
    return (
      <>
        <PageHeading title="Request not found." />
        <p>
          <Link to="/css-demo/requests">Back to My Requests</Link>
        </p>
      </>
    )
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <>
        <PageHeading title="Request details" />
        <p className="portal-error-text">
          The request could not be loaded. The demonstration backend may not be
          running.
        </p>
        <p>
          <Link to="/css-demo/requests">Back to My Requests</Link>
        </p>
      </>
    )
  }

  const request = detailQuery.data

  return (
    <>
      <PageHeading
        title={request.reference_id}
        description="Simulated request record."
      />

      <InfoPanel title="Request details">
        <DefinitionTable
          rows={[
            {
              label: 'Reference ID',
              value: (
                <span className="portal-reference-id">
                  {request.reference_id}
                </span>
              ),
            },
            {
              label: 'Request type',
              value: requestTypeLabel(request.request_type),
            },
            { label: 'Category', value: categoryLabel(request.category) },
            { label: 'Institution', value: request.institution_name },
            { label: 'State', value: request.state ?? '—' },
            { label: 'Subject', value: request.subject },
            {
              label: 'Submitted on',
              value: formatPortalDateTime(request.created_at),
            },
            {
              label: 'Current status',
              value: <StatusBadge status={request.status} />,
            },
            { label: 'Department', value: request.department },
          ]}
        />
      </InfoPanel>

      <InfoPanel title="Description">
        <p className="portal-description-text">{request.description}</p>
      </InfoPanel>

      <section className="portal-section" aria-labelledby="status-history-heading">
        <h2 className="portal-section-title" id="status-history-heading">
          Status history
        </h2>
        <DataTable
          columns={statusEventColumns}
          rows={request.status_events}
          getRowKey={(event, index) => `${event.created_at}-${index}`}
          emptyMessage="No status history recorded."
        />
      </section>

      <section className="portal-section" aria-labelledby="replies-heading">
        <h2 className="portal-section-title" id="replies-heading">
          Department replies
        </h2>
        {request.replies.length === 0 ? (
          <p className="portal-section-intro">
            No reply has been recorded yet. A simulated reply is expected after
            the request is reviewed.
          </p>
        ) : (
          <div className="portal-reply-list">
            {request.replies.map((reply: PortalReply, index) => (
              <article
                className="portal-reply"
                key={`${reply.created_at}-${index}`}
              >
                <h3 className="portal-reply-title">
                  Reply from {reply.department} (SIMULATED)
                </h3>
                <p className="portal-reply-date">
                  {formatPortalDateTime(reply.created_at)}
                </p>
                <p className="portal-reply-message">{reply.message}</p>
              </article>
            ))}
          </div>
        )}
      </section>

      <p className="portal-form-footer">
        <Link to="/css-demo/requests">Back to My Requests</Link>
      </p>
    </>
  )
}
