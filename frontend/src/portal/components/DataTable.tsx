import type { ReactNode } from 'react'

export type DataTableColumn<T> = {
  key: string
  header: ReactNode
  render: (row: T) => ReactNode
  className?: string
}

type DataTableProps<T> = {
  caption?: string
  columns: DataTableColumn<T>[]
  rows: T[]
  getRowKey: (row: T, index: number) => string | number
  emptyMessage?: string
  className?: string
}

export default function DataTable<T>({
  caption,
  columns,
  rows,
  getRowKey,
  emptyMessage = 'No records to display.',
  className,
}: DataTableProps<T>) {
  return (
    <div className={`portal-table-scroll${className ? ` ${className}` : ''}`}>
      <table className="portal-table">
        {caption ? <caption>{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={column.className}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="portal-table-empty">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr key={getRowKey(row, index)}>
                {columns.map((column) => (
                  <td key={column.key} className={column.className}>
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
