import type { PeriodicJob, PeriodicJobs, PeriodicJobsAi } from '../../../services/admin'
import {
  formatAdminDateTime,
  formatAdminNumber,
  formatDuration,
  formatRelativeTime,
} from '../format'
import { Panel } from './Panel'

const STATUS_DOT: Record<string, string> = {
  ok: 'is-ok',
  failed: 'is-bad',
  running: 'is-run',
  never: 'is-muted',
}

const MAX_FETCHED_CHIPS = 8

export interface PeriodicJobsPanelProps {
  periodic: PeriodicJobs | null
}

export function PeriodicJobsPanel({ periodic }: PeriodicJobsPanelProps) {
  return (
    <Panel title="Periodic Jobs" width="full">
      {periodic ? <AiBanner ai={periodic.ai} /> : null}
      <div className="admin-job-list">
        {(periodic?.jobs ?? []).map((job) => (
          <JobRow key={job.job} job={job} />
        ))}
        {periodic && periodic.jobs.length === 0 ? (
          <p className="admin-empty">No jobs recorded yet.</p>
        ) : null}
      </div>
    </Panel>
  )
}

function AiBanner({ ai }: { ai: PeriodicJobsAi }) {
  const providers = ai.providers ?? [{
    provider: ai.provider,
    model: ai.model,
    configured: ai.configured,
    position: 1,
  }]
  const configured = providers.some((provider) => provider.configured)
  const uses = [
    ['Descriptions', ai.uses.description_audit],
    ['Endless', ai.uses.endless_classification],
    ['Similar games', ai.uses.similar_games_rerank],
  ] as const
  return (
    <div className="admin-ai-banner">
      <div className="admin-ai-head">
        <span
          className={`admin-dot ${configured ? 'is-ok' : 'is-muted'}`}
          aria-hidden="true"
        />
        <strong>AI fallback</strong>
        <small>
          {providers.map((provider) => (
            `${provider.position}. ${provider.provider} (${provider.model})`
          )).join(' → ')}
        </small>
        <em>{configured ? 'configured' : 'not configured'}</em>
      </div>
      <div className="admin-job-chips">
        {uses.map(([label, on]) => (
          <span className={`admin-chip ${on ? 'is-on' : 'is-off'}`} key={label}>
            {label} <strong>{on ? 'on' : 'off'}</strong>
          </span>
        ))}
      </div>
    </div>
  )
}

function JobRow({ job }: { job: PeriodicJob }) {
  const dot = STATUS_DOT[job.status] ?? 'is-muted'
  const fetched = fetchedEntries(job.result)
  return (
    <div className="admin-job">
      <div className="admin-job-head">
        <span className={`admin-dot ${dot}`} aria-hidden="true" />
        <div className="admin-job-title">
          <strong>{job.label}</strong>
          <small>{statusText(job)}</small>
        </div>
        <span className="admin-job-schedule">every {formatDuration(job.interval_seconds)}</span>
      </div>
      <div className="admin-job-meta">
        <span>Last: {lastRunText(job)}</span>
        <span>Next: {job.enabled ? formatRelativeTime(job.next_run_at) : 'disabled'}</span>
      </div>
      <div className="admin-job-chips">
        {fetched.length > 0 ? (
          fetched.map(([key, value]) => (
            <span className="admin-chip" key={key}>
              {prettyKey(key)} <strong>{formatAdminNumber(value)}</strong>
            </span>
          ))
        ) : (
          <span className="admin-empty">
            {job.status === 'never' ? 'not run yet' : 'nothing new last run'}
          </span>
        )}
      </div>
    </div>
  )
}

function statusText(job: PeriodicJob): string {
  if (job.error) return `failed — ${job.error}`
  if (job.status === 'running') return 'running…'
  if (job.finished_at) return formatAdminDateTime(job.finished_at)
  return 'not run yet'
}

function lastRunText(job: PeriodicJob): string {
  if (job.finished_at) return formatRelativeTime(job.finished_at)
  if (job.status === 'running') return 'running…'
  return 'never'
}

function fetchedEntries(result: Record<string, unknown>): [string, number][] {
  const flat: [string, number][] = []
  for (const [key, value] of Object.entries(result)) {
    if (typeof value === 'number') {
      if (value !== 0) flat.push([key, value])
    } else if (value && typeof value === 'object') {
      for (const [childKey, childValue] of Object.entries(value as Record<string, unknown>)) {
        if (typeof childValue === 'number' && childValue !== 0) {
          flat.push([`${key} ${childKey}`, childValue])
        }
      }
    }
  }
  return flat.slice(0, MAX_FETCHED_CHIPS)
}

function prettyKey(key: string): string {
  return key.replace(/[._]/g, ' ')
}
