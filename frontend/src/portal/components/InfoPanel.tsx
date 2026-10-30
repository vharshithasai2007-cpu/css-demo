import type { ReactNode } from 'react'

type InfoPanelProps = {
  title: string
  children: ReactNode
  className?: string
}

export default function InfoPanel({ title, children, className }: InfoPanelProps) {
  return (
    <section className={`portal-panel${className ? ` ${className}` : ''}`}>
      <h2 className="portal-panel-title">{title}</h2>
      <div className="portal-panel-body">{children}</div>
    </section>
  )
}
