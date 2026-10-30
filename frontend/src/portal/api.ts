import axios from 'axios'

/**
 * The portal keeps its own token and HTTP client. Nothing outside this project
 * shares the token key or the axios instance.
 */
export const PORTAL_TOKEN_KEY = 'css_portal_token'
export const PORTAL_LOGIN_PATH = '/css-demo/login'

export type PortalCategory = {
  value: string
  label: string
  description: string
  department: string
}

export type PortalRequestType = {
  value: string
  label: string
  description: string
  requires_category: boolean
}

export type PortalInstitution = {
  name: string
  state: string
}

export type PortalMeta = {
  categories: PortalCategory[]
  request_types: PortalRequestType[]
  user_types: string[]
  institutions: PortalInstitution[]
}

export type PortalUser = {
  id: number
  full_name: string
  email: string
  user_type: string
  institution_name: string | null
}

export type PortalTokenResponse = {
  access_token: string
  token_type: string
}

export type PortalRequestCreated = {
  reference_id: string
  request_type: string | null
  category: string | null
  department: string
  status: string
  created_at: string
}

export type PortalRequestSummary = {
  reference_id: string
  request_type: string | null
  category: string | null
  subject: string
  department: string
  status: string
  created_at: string
  updated_at: string
}

export type PortalRequestList = {
  items: PortalRequestSummary[]
  total: number
  counts: Record<string, number>
  page: number
  page_size: number
}

export type PortalStatusEvent = {
  status: string
  remarks: string | null
  actor: string | null
  created_at: string
}

export type PortalReply = {
  department: string
  message: string
  is_simulated: boolean
  created_at: string
}

export type PortalRequestDetail = {
  reference_id: string
  request_type: string | null
  category: string | null
  subject: string
  description: string
  institution_name: string
  state: string | null
  status: string
  department: string
  created_at: string
  updated_at: string
  next_step_at: string | null
  status_events: PortalStatusEvent[]
  replies: PortalReply[]
}

const portalApi = axios.create({
  baseURL: '/css-api',
})

portalApi.interceptors.request.use((config) => {
  const token = localStorage.getItem(PORTAL_TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

portalApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear only the portal token; no other local storage keys are touched.
      localStorage.removeItem(PORTAL_TOKEN_KEY)
      if (window.location.pathname !== PORTAL_LOGIN_PATH) {
        window.location.href = PORTAL_LOGIN_PATH
      }
    }
    return Promise.reject(error)
  },
)

export default portalApi
