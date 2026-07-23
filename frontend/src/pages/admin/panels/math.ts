import { formatAdminNumber } from '../format'

export function percent(value: number, total: number): number {
  return total > 0 ? (value / total) * 100 : 0
}

export function ratio(value: number, total: number): string {
  return `${formatAdminNumber(value)}/${formatAdminNumber(total)}`
}
