import { zodResolver } from '@hookform/resolvers/zod'
import { isAxiosError } from 'axios'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import portalApi from '../api'
import Button from '../components/Button'
import FormField from '../components/FormField'
import PageHeading from '../components/PageHeading'

const USER_TYPE_OPTIONS = [
  { value: 'STUDENT', label: 'Student' },
  { value: 'FACULTY', label: 'Faculty' },
  { value: 'INSTITUTION_ADMIN', label: 'Institution administrator' },
  { value: 'OTHER', label: 'Other' },
] as const

const registerSchema = z
  .object({
    full_name: z
      .string()
      .trim()
      .min(2, 'Enter your full name (at least 2 characters).')
      .max(100, 'Full name must be 100 characters or fewer.'),
    email: z
      .string()
      .trim()
      .min(1, 'Enter your email address.')
      .email('Enter a valid email address.'),
    user_type: z.enum(['STUDENT', 'FACULTY', 'INSTITUTION_ADMIN', 'OTHER']),
    institution_name: z
      .string()
      .trim()
      .max(200, 'Institution name must be 200 characters or fewer.'),
    password: z.string().min(8, 'Password must be at least 8 characters.'),
    confirm_password: z.string().min(1, 'Confirm your password.'),
  })
  .refine(
    (data) =>
      data.password.trim().toLowerCase() !== data.email.trim().toLowerCase(),
    {
      message: 'Password must not be the same as your email.',
      path: ['password'],
    },
  )
  .refine((data) => data.password === data.confirm_password, {
    message: 'Passwords do not match.',
    path: ['confirm_password'],
  })

type RegisterFormValues = z.infer<typeof registerSchema>

export default function Register() {
  const navigate = useNavigate()
  const [serverError, setServerError] = useState('')
  const summaryRef = useRef<HTMLDivElement>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, submitCount },
  } = useForm<RegisterFormValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      full_name: '',
      email: '',
      user_type: 'STUDENT',
      institution_name: '',
      password: '',
      confirm_password: '',
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
  }, [hasErrors, submitCount])

  const onSubmit = async (values: RegisterFormValues) => {
    setServerError('')
    try {
      await portalApi.post('/portal/auth/register', {
        full_name: values.full_name,
        email: values.email,
        user_type: values.user_type,
        institution_name: values.institution_name || null,
        password: values.password,
      })
      navigate('/css-demo/login', { state: { registered: true } })
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 409) {
        setServerError('An account with this email already exists.')
        return
      }
      if (isAxiosError(error) && error.response?.status === 429) {
        setServerError('Too many attempts. Please wait a minute and try again.')
        return
      }
      setServerError('Registration failed. Please try again.')
    }
  }

  return (
    <>
      <PageHeading
        title="Register"
        description="Create a demonstration account to submit and track simulated requests."
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
          id="full_name"
          label="Full name"
          required
          error={errors.full_name?.message}
        >
          <input
            className="portal-input"
            type="text"
            autoComplete="name"
            {...register('full_name')}
          />
        </FormField>

        <FormField
          id="email"
          label="Email"
          required
          error={errors.email?.message}
        >
          <input
            className="portal-input"
            type="email"
            autoComplete="email"
            {...register('email')}
          />
        </FormField>

        <FormField
          id="user_type"
          label="User type"
          required
          error={errors.user_type?.message}
        >
          <select className="portal-select" {...register('user_type')}>
            {USER_TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </FormField>

        <FormField
          id="institution_name"
          label="Institution"
          help="Optional. Enter the name of your institution if applicable."
          error={errors.institution_name?.message}
        >
          <input
            className="portal-input"
            type="text"
            autoComplete="organization"
            {...register('institution_name')}
          />
        </FormField>

        <FormField
          id="password"
          label="Password"
          required
          help="At least 8 characters. It must not be the same as your email."
          error={errors.password?.message}
        >
          <input
            className="portal-input"
            type="password"
            autoComplete="new-password"
            {...register('password')}
          />
        </FormField>

        <FormField
          id="confirm_password"
          label="Confirm password"
          required
          error={errors.confirm_password?.message}
        >
          <input
            className="portal-input"
            type="password"
            autoComplete="new-password"
            {...register('confirm_password')}
          />
        </FormField>

        <div className="portal-form-actions">
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Creating account…' : 'Create account'}
          </Button>
        </div>
      </form>

      <p className="portal-form-footer">
        Already have an account? <Link to="/css-demo/login">Login</Link>.
      </p>
    </>
  )
}
