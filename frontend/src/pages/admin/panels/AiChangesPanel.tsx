import { Bot } from 'lucide-react'
import { Link } from 'react-router'

import type { AiCatalogChange } from '../../../services/admin'
import { formatAdminDateTime } from '../format'
import { ListOrEmpty, Panel } from './Panel'

const CHANGE_LABELS: Record<string, string> = {
  catalog_quality_repair: 'Metadata repair',
  endless_classification: 'Playtime classification',
  summary_audit: 'Description audit',
}

export function AiChangesPanel({ changes }: { changes: AiCatalogChange[] }) {
  return (
    <Panel
      title="AI Catalog Changes"
      width="full"
      action={<span><Bot size={15} aria-hidden="true" /> Last {changes.length}</span>}
    >
      <div className="admin-ai-change-list">
        <ListOrEmpty
          isEmpty={changes.length === 0}
          emptyText="No AI-driven catalog changes recorded yet."
        >
          {changes.map((change) => (
            <article className="admin-ai-change" key={change.id}>
              <div className="admin-ai-change-head">
                <Link to={`/game/${change.game_slug}`} target="_blank">
                  {change.game_title}
                </Link>
                <span>{CHANGE_LABELS[change.change_type] ?? change.change_type}</span>
                <time dateTime={change.created_at}>
                  {formatAdminDateTime(change.created_at)}
                </time>
              </div>
              <div className="admin-ai-fields">
                {change.fields.map((field) => (
                  <div key={field}>
                    <strong>{field.replaceAll('_', ' ')}</strong>
                    <span title={formatValue(change.before[field])}>
                      {formatValue(change.before[field])}
                    </span>
                    <i aria-hidden="true">→</i>
                    <span title={formatValue(change.after[field])}>
                      {formatValue(change.after[field])}
                    </span>
                  </div>
                ))}
              </div>
              {change.reason ? <p>{change.reason}</p> : null}
            </article>
          ))}
        </ListOrEmpty>
      </div>
    </Panel>
  )
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'empty'
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
