import type { FullConfig } from '@playwright/test'
import { createServer, preview, type PreviewServer, type ViteDevServer } from 'vite'

let server: ViteDevServer | PreviewServer | null = null

export default async function globalSetup(_config: FullConfig) {
  if (process.env.FLOWHUB_E2E_PRODUCTION === '1') {
    server = await preview({
      root: process.cwd(),
      logLevel: 'error',
      preview: {
        host: '127.0.0.1',
        port: 4188,
        strictPort: true,
      },
    })
  } else {
    server = await createServer({
      root: process.cwd(),
      logLevel: 'error',
      server: {
        host: '127.0.0.1',
        port: 4188,
        strictPort: true,
      },
    })
    await server.listen()
  }

  return async () => {
    await server?.close()
    server = null
  }
}
