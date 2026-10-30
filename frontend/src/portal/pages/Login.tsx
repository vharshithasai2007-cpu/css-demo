import { zodResolver } from '@hookform/resolvers/zod'
import { isAxiosError } from 'axios'
import { useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import portalApi, { type PortalTokenResponse } from '../api'
import { usePortalAuth } from '../auth'
import Button from '../components/Button'
import FormField from '../components/FormField'
import PageHeading from '../components/PageHeading'

const loginSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, 'Enter your email address.')
    .email('Enter a valid email address.'),
  password: z.string().min(1, 'Enter your password.'),
})

type LoginFormValues = z.infer<typeof loginSchema>

type LoginLocationState = {
  registered?: boolean
}

export default function Login() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login } = usePortalAuth()
  const [serverError, setServerError] = useState('')
  const summaryRef = useRef<HTMLDivElement>(null)

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting, submitCount },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: '',
      password: '',
    },
  })

  const registered = Boolean(
    (location.state as LoginLocationState | null)?.registered,
  )

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

  const onSubmit = async (values: LoginFormValues) => {
    setServerError('')
    try {
      const response = await portalApi.post<PortalTokenResponse>(
        '/portal/auth/login',
        {
          email: values.email,
          password: values.password,
        },
      )
      login(response.data.access_token)
      navigate('/css-demo/requests')
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 401) {
        setServerError('Incorrect email or password.')
        return
      }
      if (isAxiosError(error) && error.response?.status === 429) {
        setServerError('Too many attempts. Please wait a minute and try again.')
        return
      }
      setServerError('Login failed. Please try again.')
    }
  }

  return (
    <>
      <PageHeading
        title="Login"
        description="Sign in to submit and track simulated requests."
      />

      {registered ? (
        <p className="portal-success-text">
          Account created. You can now sign in.
        </p>
      ) : null}

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
          id="login_email"
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
          id="login_password"
          label="Password"
          required
          error={errors.password?.message}
        >
          <input
            className="portal-input"
            type="password"
            autoComplete="current-password"
            {...register('password')}
          />
        </FormField>

        <div className="portal-form-actions">
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Signing in…' : 'Sign in'}
          </Button>
        </div>
      </form>

      <p className="portal-form-footer">
        Need an account? <Link to="/css-demo/register">Register</Link>.
      </p>
    </>
  )
}
