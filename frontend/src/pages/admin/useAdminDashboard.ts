import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from 'react'
import {
  AdminApiError,
  getAdminApiHealth,
  getAdminAuditLogs,
  getAdminDashboard,
  getApiSources,
  getDataFillStatus,
  getPeriodicJobs,
  loginAdmin,
  runDataFill,
  runPrimaryScores,
  type AdminApiHealth,
  type AdminAuditLog,
  type AdminDashboard,
  type ApiSources,
  type DataFillStatus,
  type PeriodicJobs,
} from '../../services/admin'
import { setInternalAnalyticsTraffic } from '../../services/analyticsConsent'

const AUDIT_LOG_LIMIT = 100
const DATA_FILL_TARGET = 10_000
const PRIMARY_SCORE_LIMIT = 10_000

export const TRAFFIC_DAY_OPTIONS = [7, 14, 30] as const

export function useAdminDashboard() {
  const [auditOnlyFailures, setAuditOnlyFailures] = useState(false)
  const [trafficDays, setTrafficDays] = useState<number>(TRAFFIC_DAY_OPTIONS[0])
  const [error, setError] = useState<string | null>(null)
  const session = useAdminSession(setError)
  const resources = useAdminResources({
    auditOnlyFailures,
    onSessionExpired: session.expire,
    setError,
    token: session.token,
    trafficDays,
  })
  const jobs = useAdminJobs(session.token, resources.setDataFill, setError)
  const metrics = useAdminMetrics(resources.dashboard, resources.dataFill)

  const handleLogout = useCallback(() => {
    session.clear()
    resources.clear()
  }, [resources, session])

  return {
    auditLogs: resources.auditLogs,
    auditOnlyFailures,
    dashboard: resources.dashboard,
    dataFill: resources.dataFill,
    dataGaps: metrics.dataGaps,
    periodic: resources.periodic,
    apiSources: resources.apiSources,
    error,
    handleLogin: session.login,
    handleLogout,
    handleStartDataFill: jobs.startDataFill,
    handleStartPrimaryScores: jobs.startPrimaryScores,
    health: resources.health,
    isLoading: resources.isLoading,
    isSigningIn: session.isSigningIn,
    isStartingDataFill: jobs.isStartingDataFill,
    isStartingPrimaryScores: jobs.isStartingPrimaryScores,
    loadDashboard: resources.load,
    maxDailyVisits: metrics.maxDailyVisits,
    password: session.password,
    primaryScoreRows: metrics.primaryScoreRows,
    rateLimitRows: metrics.rateLimitRows,
    setAuditOnlyFailures,
    setPassword: session.setPassword,
    setTrafficDays,
    setUsername: session.setUsername,
    token: session.token,
    trafficDays,
    username: session.username,
  }
}

type ErrorSetter = (message: string | null) => void

function useAdminSession(setError: ErrorSetter) {
  const [token, setToken] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [isSigningIn, setIsSigningIn] = useState(false)

  const clear = useCallback(() => setToken(''), [])
  const expire = useCallback(() => {
    clear()
    setError('Session expired. Please sign in again.')
  }, [clear, setError])
  const login = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setIsSigningIn(true)
    setError(null)
    try {
      const response = await loginAdmin(username.trim(), password)
      setInternalAnalyticsTraffic(true)
      setToken(response.access_token)
      setPassword('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Login failed.')
    } finally {
      setIsSigningIn(false)
    }
  }, [password, setError, username])

  return {
    clear,
    expire,
    isSigningIn,
    login,
    password,
    setPassword,
    setUsername,
    token,
    username,
  }
}

interface AdminResourcesProps {
  auditOnlyFailures: boolean
  onSessionExpired: () => void
  setError: ErrorSetter
  token: string
  trafficDays: number
}

function useAdminResources({
  auditOnlyFailures,
  onSessionExpired,
  setError,
  token,
  trafficDays,
}: AdminResourcesProps) {
  const [dashboard, setDashboard] = useState<AdminDashboard | null>(null)
  const [health, setHealth] = useState<AdminApiHealth>({})
  const [dataFill, setDataFill] = useState<DataFillStatus | null>(null)
  const [periodic, setPeriodic] = useState<PeriodicJobs | null>(null)
  const [apiSources, setApiSources] = useState<ApiSources | null>(null)
  const [auditLogs, setAuditLogs] = useState<AdminAuditLog[]>([])
  const [isLoading, setIsLoading] = useState(false)

  const clear = useCallback(() => {
    setDashboard(null)
    setHealth({})
    setDataFill(null)
    setPeriodic(null)
    setApiSources(null)
    setAuditLogs([])
  }, [])

  const load = useCallback(async () => {
    if (!token) return
    setIsLoading(true)
    setError(null)
    const results = await loadAdminResources(token, trafficDays, auditOnlyFailures)
    setIsLoading(false)
    if (results.some(isUnauthorizedResult)) {
      clear()
      onSessionExpired()
      return
    }
    applyAdminResources(results, {
      setApiSources,
      setAuditLogs,
      setDashboard,
      setDataFill,
      setHealth,
      setPeriodic,
    })
    setError(failureMessage(results))
  }, [
    auditOnlyFailures,
    clear,
    onSessionExpired,
    setError,
    token,
    trafficDays,
  ])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timer)
  }, [load])

  return {
    apiSources,
    auditLogs,
    clear,
    dashboard,
    dataFill,
    health,
    isLoading,
    load,
    periodic,
    setDataFill,
  }
}

function useAdminJobs(
  token: string,
  setDataFill: (status: DataFillStatus) => void,
  setError: ErrorSetter,
) {
  const [isStartingDataFill, setIsStartingDataFill] = useState(false)
  const [isStartingPrimaryScores, setIsStartingPrimaryScores] = useState(false)

  const startDataFill = useCallback(async () => {
    if (!token) return
    setIsStartingDataFill(true)
    setError(null)
    try {
      await runDataFill(token, { targetTotal: DATA_FILL_TARGET })
      setDataFill(await getDataFillStatus(token))
    } catch (caught) {
      setError(errorMessage(caught, 'Data fill could not be started.'))
    } finally {
      setIsStartingDataFill(false)
    }
  }, [setDataFill, setError, token])

  const startPrimaryScores = useCallback(async () => {
    if (!token) return
    setIsStartingPrimaryScores(true)
    setError(null)
    try {
      await runPrimaryScores(token, { limit: PRIMARY_SCORE_LIMIT })
      setDataFill(await getDataFillStatus(token))
    } catch (caught) {
      setError(errorMessage(caught, 'Primary scores could not be started.'))
    } finally {
      setIsStartingPrimaryScores(false)
    }
  }, [setDataFill, setError, token])

  return {
    isStartingDataFill,
    isStartingPrimaryScores,
    startDataFill,
    startPrimaryScores,
  }
}

function useAdminMetrics(
  dashboard: AdminDashboard | null,
  dataFill: DataFillStatus | null,
) {
  const maxDailyVisits = useMemo(() => {
    const visits = dashboard?.traffic.daily.map((row) => row.visits) ?? []
    return Math.max(1, ...visits)
  }, [dashboard])
  const dataGaps = useMemo(() => catalogDataGaps(dataFill), [dataFill])
  const rateLimitRows = useMemo(() => (
    Object.entries(dataFill?.rate_limits ?? {})
      .filter(([source]) => DISPLAYED_RATE_LIMITS.has(source))
      .sort(([left], [right]) => left.localeCompare(right))
  ), [dataFill])
  const primaryScoreRows = useMemo(() => (
    Object.entries(dataFill?.primary_scores.sources ?? {})
      .sort(([left], [right]) => left.localeCompare(right))
  ), [dataFill])
  return { dataGaps, maxDailyVisits, primaryScoreRows, rateLimitRows }
}

function catalogDataGaps(dataFill: DataFillStatus | null) {
  const catalog = dataFill?.catalog
  return [
    ['Missing ratings', catalog?.missing_ratings ?? 0],
    ['Missing 4-source score slots', catalog?.missing_primary_scores ?? 0],
    ['Missing metadata', catalog?.missing_metadata ?? 0],
    ['Missing HLTB', catalog?.missing_hltb ?? 0],
    ['Missing prices', catalog?.missing_prices ?? 0],
    ['Missing external IDs', catalog?.missing_external_ids ?? 0],
  ] as const
}

function errorMessage(caught: unknown, fallback: string): string {
  return caught instanceof Error ? caught.message : fallback
}

const DISPLAYED_RATE_LIMITS = new Set([
  'Metacritic',
  'RAWG',
  'IGDB',
  'Steam',
  'SteamSpy',
  'CheapShark',
  'FreeToGame',
  'ITAD',
  'OpenCritic',
])

function loadAdminResources(
  token: string,
  trafficDays: number,
  auditOnlyFailures: boolean,
) {
  return Promise.allSettled([
    getAdminDashboard(token, trafficDays),
    getAdminApiHealth(token),
    getDataFillStatus(token),
    getAdminAuditLogs(token, {
      limit: AUDIT_LOG_LIMIT,
      onlyFailures: auditOnlyFailures,
    }),
    getPeriodicJobs(token),
    getApiSources(token),
  ] as const)
}

type AdminResourceResults = Awaited<ReturnType<typeof loadAdminResources>>

function applyAdminResources(
  results: AdminResourceResults,
  setters: {
    setApiSources: (apiSources: ApiSources) => void
    setAuditLogs: (logs: AdminAuditLog[]) => void
    setDashboard: (dashboard: AdminDashboard) => void
    setDataFill: (status: DataFillStatus) => void
    setHealth: (health: AdminApiHealth) => void
    setPeriodic: (periodic: PeriodicJobs) => void
  },
) {
  const [
    dashboardResult,
    healthResult,
    dataFillResult,
    auditResult,
    periodicResult,
    apiSourcesResult,
  ] = results
  if (dashboardResult.status === 'fulfilled') {
    setters.setDashboard(dashboardResult.value)
  }
  if (healthResult.status === 'fulfilled') setters.setHealth(healthResult.value)
  if (dataFillResult.status === 'fulfilled') {
    setters.setDataFill(dataFillResult.value)
  }
  if (auditResult.status === 'fulfilled') setters.setAuditLogs(auditResult.value)
  if (periodicResult.status === 'fulfilled') setters.setPeriodic(periodicResult.value)
  if (apiSourcesResult.status === 'fulfilled') setters.setApiSources(apiSourcesResult.value)
}

function isUnauthorizedResult(
  result: AdminResourceResults[number],
): boolean {
  return (
    result.status === 'rejected'
    && result.reason instanceof AdminApiError
    && result.reason.status === 401
  )
}

function failureMessage(results: AdminResourceResults): string | null {
  const labels = [
    'Dashboard',
    'API health',
    'Data fill',
    'Audit log',
    'Periodic jobs',
    'API sources',
  ]
  const messages = results.flatMap((result, index) => {
    if (result.status === 'fulfilled') return []
    const reason: unknown = result.reason
    const detail = reason instanceof Error ? reason.message : 'request failed'
    return [`${labels[index]}: ${detail}`]
  })
  return messages.length > 0 ? messages.join(' · ') : null
}
