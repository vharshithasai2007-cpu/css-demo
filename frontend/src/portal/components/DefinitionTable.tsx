import type { ReactNode } from 'react'

export type DefinitionRow = {
  label: ReactNode
  value: ReactNode
}

type DefinitionTableProps = {
  rows: DefinitionRow[]
  caption?: string
  className?: string
}

export default function DefinitionTable({ rows, caption, className }: DefinitionTableProps) {
  return (
    <table className={`portal-definition${className ? ` ${className}` : ''}`}>
      {caption ? <caption>{caption}</caption> : null}
      <tbody>
        {rows.map((row, index) => (
          <tr key={index}>
            <th scope="row">{row.label}</th>
            <td>{row.value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
