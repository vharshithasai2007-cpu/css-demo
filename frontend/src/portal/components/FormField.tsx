import { cloneElement, type ReactElement, type ReactNode } from 'react'

type FormFieldProps = {
  id: string
  label: string
  required?: boolean
  help?: ReactNode
  error?: string
  children: ReactElement<any>
  className?: string
}

/**
 * Renders a visible label, optional help text and inline error, and wires the
 * control to both descriptions with `aria-describedby`.
 */
export default function FormField({
  id,
  label,
  required = false,
  help,
  error,
  children,
  className,
}: FormFieldProps) {
  const helpId = help ? `${id}-help` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [helpId, errorId].filter(Boolean).join(' ') || undefined

  const control = cloneElement(children, {
    id,
    'aria-describedby': describedBy,
    'aria-invalid': error ? true : undefined,
  })

  return (
    <div className={`portal-field${className ? ` ${className}` : ''}`}>
      <label className="portal-field-label" htmlFor={id}>
        {label}
        {required ? (
          <>
            <span className="portal-required" aria-hidden="true">
              {' '}
              *
            </span>
            <span className="portal-visually-hidden"> (required)</span>
          </>
        ) : null}
      </label>
      {help ? (
        <p className="portal-field-help" id={helpId}>
          {help}
        </p>
      ) : null}
      {control}
      {error ? (
        <p className="portal-field-error" id={errorId}>
          {error}
        </p>
      ) : null}
    </div>
  )
}
