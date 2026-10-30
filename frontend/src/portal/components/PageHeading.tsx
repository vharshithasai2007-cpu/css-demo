import type { ReactNode } from 'react'

type PageHeadingProps = {
  title: string
  description?: ReactNode
}

export default function PageHeading({ title, description }: PageHeadingProps) {
  return (
    <div className="portal-page-heading">
      <h1>{title}</h1>
      {description ? <p className="portal-page-description">{description}</p> : null}
    </div>
  )
}
