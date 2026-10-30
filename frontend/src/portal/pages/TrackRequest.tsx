import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import portalApi, { type PortalRequestDetail } from '../api'
import Button from '../components/Button'
import FormField from '../components/FormField'
import PageHeading from '../components/PageHeading'

const REFERENCE_PATTERN = /^CSSD-\d{4}-\d{6}$/

const trackSchema = z.object({
  reference_id: z
    .string()
    .trim()
    .min(1, 'Enter a reference ID.')
    .refine((value) => REFERENCE_PATTERN.test(value.toUpperCase()), {
      message: 'Enter a reference ID in the format CSSD-YYYY-NNNNNN.',
    }),
})

type TrackFormValues = z.infer<typeof trackSchema>

export default function TrackRequest() {
  const navigate = useNavigate()
  const [serverError, setServerError] = useState('')
  const summaryRef = useRef<HTMLDivElement>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, submitCount },
  } = useForm<TrackFormValues>({
    resolver: zodResolver(trackSchema),
    defaultValues: { reference_id: '' },
  })

  const lookup = useMutation({
    mutationFn: async (reference: string) => {
      const response = await portalApi.get<PortalRequestDetail>(
        `/portal/v2/requests/${encodeURIComponent(reference)}`,
      )
      return response.data
    },
    onSuccess: (request) => {
      navigate(`/css-demo/requests/${request.reference_id}`)
    },
    onError: (error) => {
      if (isAxiosError(error) && error.response?.status === 404) {
        setServerError('Request not found.')
        return
      }
      setServerError(
        'The request could not be looked up. Please try again in a moment.',
      )
    },
  })

  const errorMessages = Object.values(errors)
    .map((error) =>
      typeof error?.message === 'string' ? error.message : undefined,
    )
    .filter((message): message is string => Boolean(message))
  const summaryMessages = serverError
    ? [serverError, ...errorMessages]
    : errorMessages
  const hasErrors = summaryMessages.length > 0

  useEffect(() => {
    if (hasErrors) {
      summaryRef.current?.focus()
    }
  }, [hasErrors, submitCount, serverError])

  const onSubmit = (values: TrackFormValues) => {
    setServerError('')
    lookup.mutate(values.reference_id.trim().toUpperCase())
  }

  return (
    <>
      <PageHeading
        title="Track Request"
        description="Enter a simulated reference ID to open its current status."
      />

      {hasErrors ? (
        <div
          className="portal-error-summary"
          role="alert"
          tabIndex={-1}
          ref={summaryRef}
        >
          <p className="portal-error-summary-title">
            Please correct the following:
          </p>
          <ul>
            {summaryMessages.map((message, index) => (
              <li key={`${message}-${index}`}>{message}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <form className="portal-form" onSubmit={handleSubmit(onSubmit)} noValidate>
        <FormField
          id="reference_id"
          label="Reference ID"
          required
          help="For example, CSSD-2026-100001."
          error={errors.reference_id?.message}
        >
          <input
            className="portal-input"
            type="text"
            autoComplete="off"
            spellCheck={false}
            {...register('reference_id')}
          />
        </FormField>

        <div className="portal-form-actions">
          <Button type="submit" disabled={lookup.isPending}>
            {lookup.isPending ? 'Looking up…' : 'Track request'}
          </Button>
        </div>
      </form>

      <p className="portal-form-footer">
        <Link to="/css-demo/requests">Back to My Requests</Link>
      </p>
    </>
  )
}
