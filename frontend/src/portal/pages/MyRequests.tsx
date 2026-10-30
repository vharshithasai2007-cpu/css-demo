import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import portalApi, {
  type PortalMeta,
  type PortalRequestList,
  type PortalRequestSummary,
} from '../api'
import DataTable, { type DataTableColumn } from '../components/DataTable'
import FormField from '../components/FormField'
import PageHeading from '../components/PageHeading'
import StatusBadge from '../components/StatusBadge'
import { formatPortalDate, formatPortalDateTime } from '../format'

const PAGE_SIZE = 10

const STATUS_OPTIONS = [
  { value: 'SUBMITTED', label: 'Submitted' },
  { value: 'UNDER_REVIEW', label: 'Under review' },
  { value: 'REPLY_SENT', label: 'Reply sent' },
  { value: 'RESOLVED', label: 'Resolved' },
]

function pageHref(searchParams: URLSearchParams, target: number): string {
  const next = new URLSearchParams(searchParams)
  if (target <= 1) {
    next.delete('page')
  } else {
    next.set('page', String(target))
  }
  const query = next.toString()
  return `/css-demo/requests${query ? `?${query}` : ''}`
}

export default function MyRequests() {
  const [searchParams, setSearchParams] = useSearchParams()
  const status = searchParams.get('status') ?? ''
  const category = searchParams.get('category') ?? ''
  const parsedPage = Number.parseInt(searchParams.get('page') ?? '1', 10)
  const page = Number.isNaN(parsedPage) || parsedPage < 1 ? 1 : parsedPage

  const metaQuery = useQuery({
    queryKey: ['portal', 'meta'],
    queryFn: async () => {
      const response = await portalApi.get<PortalMeta>('/portal/meta')
      return response.data
    },
  })

  const listQuery = useQuery({
    queryKey: ['portal', 'requests', status, category, page],
    queryFn: async () => {
      const response = await portalApi.get<PortalRequestList>(
        '/portal/v2/requests',
        {
          params: {
            status: status || undefined,
            category: category || undefined,
            page,
            page_size: PAGE_SIZE,
          },
        },
      )
      return response.data
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

  const counts = listQuery.data?.counts ?? {}
  const totalCount = Object.values(counts).reduce((sum, value) => sum + value, 0)
  const submittedCount = counts.SUBMITTED ?? 0
  const inProgressCount = (counts.UNDER_REVIEW ?? 0) + (counts.REPLY_SENT ?? 0)
  const resolvedCount = counts.RESOLVED ?? 0

  const total = listQuery.data?.total ?? 0
  const firstRow = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1
  const lastRow = Math.min(page * PAGE_SIZE, total)
  const hasPrevious = page > 1
  const hasNext = page * PAGE_SIZE < total
  const filtersActive = Boolean(status || category)

  const updateFilter = (key: 'status' | 'category', value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value) {
      next.set(key, value)
    } else {
      next.delete(key)
    }
    next.delete('page')
    setSearchParams(next)
  }

  const columns: DataTableColumn<PortalRequestSummary>[] = [
    {
      key: 'reference_id',
      header: 'Reference ID',
      render: (request) => (
        <Link to={`/css-demo/requests/${request.reference_id}`}>
          {request.reference_id}
        </Link>
      ),
    },
    {
      key: 'request_type',
      header: 'Request type',
      render: (request) => requestTypeLabel(request.request_type),
    },
    {
      key: 'created_at',
      header: 'Date',
      render: (request) => formatPortalDate(request.created_at),
    },
    {
      key: 'category',
      header: 'Category',
      render: (request) => categoryLabel(request.category),
    },
    {
      key: 'subject',
      header: 'Subject',
      render: (request) => request.subject,
    },
    {
      key: 'department',
      header: 'Department',
      render: (request) => request.department,
    },
    {
      key: 'status',
      header: 'Status',
      render: (request) => <StatusBadge status={request.status} />,
    },
    {
      key: 'updated_at',
      header: 'Last updated',
      render: (request) => formatPortalDateTime(request.updated_at),
    },
  ]

  return (
    <>
      <PageHeading
        title="My Requests"
        description="Review the simulated requests submitted from this account."
      />

      <div className="portal-table-scroll">
        <table className="portal-summary-table">
          <caption className="portal-visually-hidden">Request summary</caption>
          <tbody>
            <tr>
              <td>
                <span className="portal-summary-label">Total</span>
                <span className="portal-summary-value">{totalCount}</span>
              </td>
              <td>
                <span className="portal-summary-label">Submitted</span>
                <span className="portal-summary-value">{submittedCount}</span>
              </td>
              <td>
                <span className="portal-summary-label">
                  Under review or reply sent
                </span>
                <span className="portal-summary-value">{inProgressCount}</span>
              </td>
              <td>
                <span className="portal-summary-label">Resolved</span>
                <span className="portal-summary-value">{resolvedCount}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="portal-filter-bar">
        <FormField
          id="filter-status"
          label="Status"
          className="portal-filter-field"
        >
          <select
            className="portal-select"
            value={status}
            onChange={(event) => updateFilter('status', event.target.value)}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FormField>

        <FormField
          id="filter-category"
          label="Category"
          className="portal-filter-field"
        >
          <select
            className="portal-select"
            value={category}
            onChange={(event) => updateFilter('category', event.target.value)}
          >
            <option value="">All categories</option>
            {(metaQuery.data?.categories ?? []).map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </FormField>

        <p className="portal-filter-reset">
          <Link to="/css-demo/requests">Reset</Link>
        </p>
      </div>

      {listQuery.isError ? (
        <p className="portal-error-text">
          Your requests could not be loaded. The demonstration backend may not be
          running.
        </p>
      ) : null}

      {!listQuery.isError && !listQuery.isLoading && total === 0 ? (
        <div className="portal-empty-state">
          <p>
            {filtersActive
              ? 'No requests match the selected filters.'
              : 'You have not submitted any requests yet.'}
          </p>
          <p>
            <Link to="/css-demo/submit">Submit a request</Link>.
          </p>
        </div>
      ) : (
        <DataTable
          columns={columns}
          rows={listQuery.data?.items ?? []}
          getRowKey={(request) => request.reference_id}
          emptyMessage="Loading your requests…"
        />
      )}

      {!listQuery.isLoading && !listQuery.isError && total > 0 ? (
        <div className="portal-pagination">
          <p className="portal-pagination-info">
            Showing {firstRow}-{lastRow} of {total}
          </p>
          <p className="portal-pagination-links">
            {hasPrevious ? (
              <Link to={pageHref(searchParams, page - 1)}>Previous</Link>
            ) : (
              <span aria-disabled="true" className="portal-pagination-disabled">
                Previous
              </span>
            )}
            {hasNext ? (
              <Link to={pageHref(searchParams, page + 1)}>Next</Link>
            ) : (
              <span aria-disabled="true" className="portal-pagination-disabled">
                Next
              </span>
            )}
          </p>
        </div>
      ) : null}
    </>
  )
}
