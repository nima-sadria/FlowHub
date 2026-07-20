import type { Source } from '../types'

export interface SourceService {
  getSources(): Promise<Source[]>
}
