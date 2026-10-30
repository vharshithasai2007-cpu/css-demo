import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router-dom'
import { z } from 'zod'
import portalApi, {
  type PortalMeta,
  type PortalRequestCreated,
} from '../api'
import Button from '../components/Button'
import DefinitionTable from '../components/DefinitionTable'
import FormField from '../components/FormField'
import InfoPanel from '../components/InfoPanel'
import PageHeading from '../components/PageHeading'
import StatusBadge from '../components/StatusBadge'
import { formatPortalDate } from '../format'

const REQUEST_TYPE_VALUES = [
  'SUGGESTION',
  'ENQUIRY',
  'GRIEVANCE',
  'COMPLAINT',
  'APPRECIATION',
  'REQUIRED_SUPPORT',
  'WILLING_TO_SUPPORT',
] as const

const CATEGORY_REQUIRED_TYPES = new Set<string>(['COMPLAINT', 'GRIEVANCE'])

const submitSchema = z
  .object({
    request_type: z.enum(REQUEST_TYPE_VALUES),
    category: z.string(),
    institution_name: z
      .string()
      .trim()
      .min(3, 'Enter the institution name (at least 3 characters).')
      .max(200, 'Institution name must be 200 characters or fewer.'),
    state: z
      .string()
      .trim()
      .max(80, 'State must be 80 characters or fewer.'),
    subject: z
      .string()
      .trim()
      .min(5, 'Enter a subject of at least 5 characters.')
      .max(150, 'Subject must be 150 characters or fewer.'),
    description: z
      .string()
      .trim()
      .min(20, 'Enter a description of at least 20 characters.')
      .max(4000, 'Description must be 4000 characters or fewer.'),
    confirm: z.boolean().refine((value) => value === true, {
      message:
        'You must confirm that this is a demonstration and that you have not entered real personal information.',
    }),
  })
  .superRefine((data, ctx) => {
    const requiresCategory = CATEGORY_REQUIRED_TYPES.has(data.request_type)
    if (requiresCategory && !data.category) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['category'],
        message: 'Select a subject category.',
      })
    }
    if (!requiresCategory && data.category) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['category'],
        message: 'Subject category is not applicable to this request type.',
      })
    }
  })

type SubmitFormValues = z.infer<typeof submitSchema>

export default function SubmitRequest() {
  const [created, setCreated] = useState<PortalRequestCreated | null>(null)
  const [serverError, setServerError] = useState('')
  const summaryRef = useRef<HTMLDivElement>(null)

  const metaQuery = useQuery({
    queryKey: ['portal', 'meta'],
    queryFn: async () => {
      const response = await portalApi.get<PortalMeta>('/portal/meta')
      return response.data
    },
  })

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors, isSubmitting, submitCount },
  } = useForm<SubmitFormValues>({
    resolver: zodResolver(submitSchema),
    defaultValues: {
      request_type: 'COMPLAINT',
      category: '',
      institution_name: '',
      state: '',
      subject: '',
      description: '',
      confirm: false,
    },
  })

  const requestType = watch('request_type')
  const category = watch('category')
  const description = watch('description') ?? ''
  const requiresCategory = CATEGORY_REQUIRED_TYPES.has(requestType)

  const requestTypes = metaQuery.data?.request_types ?? []
  const categories = metaQuery.data?.categories ?? []
  const institutions = metaQuery.data?.institutions ?? []
  const selectedRequestType = requestTypes.find(
    (item) => item.value === requestType,
  )
  const selectedCategory = categories.find((item) => item.value === category)

  useEffect(() => {
    if (!requiresCategory && category) {
      setValue('category', '')
    }
  }, [requiresCategory, category, setValue])

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
  }, [hasErrors, submitCount])

  const onSubmit = async (values: SubmitFormValues) => {
    setServerError('')
    try {
      const requestTypeRequiresCategory = CATEGORY_REQUIRED_TYPES.has(
        values.request_type,
      )
      const response = await portalApi.post<PortalRequestCreated>(
        '/portal/v2/requests',
        {
          request_type: values.request_type,
          category: requestTypeRequiresCategory ? values.category : null,
          institution_name: values.institution_name,
          state: values.state || null,
          subject: values.subject,
          description: values.description,
        },
      )
      setCreated(response.data)
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 401) {
        setServerError('Your session has expired. Please sign in again.')
        return
      }
      setServerError(
        'The request could not be submitted. Please check the form and try again.',
      )
    }
  }

  if (metaQuery.isLoading) {
    return (
      <>
        <PageHeading title="Submit Request" />
        <p>Loading portal information…</p>
      </>
    )
  }

  if (metaQuery.isError) {
    return (
      <>
        <PageHeading title="Submit Request" />
        <p className="portal-error-text">
          Portal information could not be loaded. The demonstration backend may
          not be running.
        </p>
      </>
    )
  }

  if (created) {
    const createdCategoryLabel = created.category
      ? categories.find((item) => item.value === created.category)?.label ??
        created.category
      : 'Not applicable'
    const createdRequestTypeLabel = created.request_type
      ? requestTypes.find((item) => item.value === created.request_type)
          ?.label ?? created.request_type
      : 'Not recorded (legacy)'

    return (
      <>
        <PageHeading title="Submit Request" />
        <InfoPanel title="Request registered (simulated)">
          <DefinitionTable
            rows={[
              {
                label: 'Reference ID',
                value: (
                  <span className="portal-reference-id">
                    {created.reference_id}
                  </span>
                ),
              },
              { label: 'Request type', value: createdRequestTypeLabel },
              { label: 'Category', value: createdCategoryLabel },
              { label: 'Department', value: created.department },
              {
                label: 'Status',
                value: <StatusBadge status={created.status} />,
              },
              { label: 'Date', value: formatPortalDate(created.created_at) },
            ]}
          />
          <p className="portal-form-footer">
            <Link to={`/css-demo/requests/${created.reference_id}`}>
              View request
            </Link>
            <span aria-hidden="true"> · </span>
            <Link
              to="/css-demo/submit"
              onClick={() => {
                setCreated(null)
                reset()
              }}
            >
              Submit another request
            </Link>
          </p>
        </InfoPanel>
      </>
    )
  }

  return (
    <>
      <PageHeading
        title="Submit Request"
        description="Submit a simulated request to the Centralized Support System."
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

      <div className="portal-form-layout">
        <form
          className="portal-form"
          onSubmit={handleSubmit(onSubmit)}
          noValidate
        >
          <FormField
            id="request_type"
            label="Request type"
            required
            help={
              selectedRequestType?.description ??
              'Choose the reason for contacting the Centralized Support System.'
            }
            error={errors.request_type?.message}
          >
            <select className="portal-select" {...register('request_type')}>
              {requestTypes.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </FormField>

          {requiresCategory ? (
            <FormField
              id="category"
              label="Subject category"
              required
              help={
                selectedCategory?.description ??
                'Select the subject category that best matches your request.'
              }
              error={errors.category?.message}
            >
              <select className="portal-select" {...register('category')}>
                <option value="">Select a subject category</option>
                {categories.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </FormField>
          ) : (
            <p className="portal-field-help portal-category-note">
              This request type is handled by the Centralized Support System
              Desk (SIMULATED) and does not require a subject category.
            </p>
          )}

          <FormField
            id="institution_name"
            label="Institution name"
            required
            help="Start typing to choose a listed institution, or enter another name."
            error={errors.institution_name?.message}
          >
            <input
              className="portal-input"
              type="text"
              list="portal-institution-options"
              autoComplete="organization"
              {...register('institution_name')}
            />
          </FormField>
          <datalist id="portal-institution-options">
            {institutions.map((institution) => (
              <option key={institution.name} value={institution.name} />
            ))}
          </datalist>

          <FormField
            id="state"
            label="State"
            help="Optional."
            error={errors.state?.message}
          >
            <input
              className="portal-input"
              type="text"
              autoComplete="address-level1"
              {...register('state')}
            />
          </FormField>

          <FormField
            id="subject"
            label="Subject"
            required
            help="Between 5 and 150 characters."
            error={errors.subject?.message}
          >
            <input
              className="portal-input"
              type="text"
              {...register('subject')}
            />
          </FormField>

          <FormField
            id="description"
            label="Description"
            required
            help="Describe the matter in 20 to 4000 characters."
            error={errors.description?.message}
          >
            <textarea
              className="portal-textarea"
              rows={8}
              {...register('description')}
            />
          </FormField>
          <p className="portal-character-count" aria-live="polite">
            {description.length} / 4000 characters
          </p>

          <FormField
            id="confirm"
            label="I confirm this is a demonstration and I have not entered real personal information."
            required
            error={errors.confirm?.message}
          >
            <input
              className="portal-checkbox"
              type="checkbox"
              {...register('confirm')}
            />
          </FormField>

          <div className="portal-form-actions">
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Submitting…' : 'Submit request'}
            </Button>
          </div>
        </form>

        <aside className="portal-form-aside">
          <InfoPanel title="Before you submit">
            <ul className="portal-plain-list">
              <li>
                This is a simulation. No request reaches AICTE or any
                institution.
              </li>
              <li>
                Do not enter real personal information, including names, phone
                numbers, or identity documents.
              </li>
              <li>
                Complaint and grievance requests require one of the seven
                subject categories. Other request types go to the generic
                simulated desk.
              </li>
              <li>
                Simulated replies and status changes appear after a short delay,
                and the reference ID tracks the request.
              </li>
            </ul>
          </InfoPanel>
        </aside>
      </div>
    </>
  )
}
